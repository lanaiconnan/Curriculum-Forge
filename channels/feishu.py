"""
Feishu Channel Adapter

飞书开放平台集成：
- Webhook 事件接收（消息、机器人交互）
- 消息发送 API（文本、卡片、图片等）
- Gateway 集成（POST /webhooks/feishu）

参考：
- https://open.feishu.cn/document/ukTMukTMukTM/uYjNwUjL2YDM14iN2ATN
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import httpx

logger = logging.getLogger("feishu")


# ─────────────────────────────────────────────────────────────────────────────
# Feishu Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FeishuConfig:
    """飞书应用配置"""
    
    app_id: str
    app_secret: str
    encrypt_key: str = ""  # 可选：事件加密密钥
    verification_token: str = ""  # 可选：事件验证 token
    
    # API endpoints
    base_url: str = "https://open.feishu.cn/open-apis"
    
    # Cache
    _tenant_access_token: Optional[str] = field(default=None, repr=False)
    _token_expires_at: float = field(default=0.0, repr=False)
    
    @classmethod
    def from_env(cls) -> "FeishuConfig":
        """从环境变量加载配置"""
        import os
        return cls(
            app_id=os.getenv("FEISHU_APP_ID", ""),
            app_secret=os.getenv("FEISHU_APP_SECRET", ""),
            encrypt_key=os.getenv("FEISHU_ENCRYPT_KEY", ""),
            verification_token=os.getenv("FEISHU_VERIFICATION_TOKEN", ""),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Feishu Adapter
# ─────────────────────────────────────────────────────────────────────────────

class FeishuAdapter:
    """
    飞书渠道适配器
    
    功能：
    - 获取 tenant_access_token
    - 发送消息（文本、卡片等）
    - 处理 Webhook 事件
    - 与 Gateway 集成
    """
    
    def __init__(
        self,
        config: FeishuConfig,
        on_message: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.config = config
        self.on_message = on_message
        self._http = httpx.AsyncClient(timeout=30.0)
    
    async def close(self):
        """关闭 HTTP 客户端"""
        await self._http.aclose()
    
    # ── Authentication ────────────────────────────────────────────────────────
    
    async def get_tenant_access_token(self, force_refresh: bool = False) -> str:
        """
        获取 tenant_access_token
        
        文档：https://open.feishu.cn/document/ukTMukTMukTM/ukDNz4SO0MjL5QzM/auth-v3/tenant_access_token/internal
        """
        # Check cache
        if not force_refresh and self.config._tenant_access_token:
            if time.time() < self.config._token_expires_at:
                return self.config._tenant_access_token
        
        url = f"{self.config.base_url}/auth/v3/tenant_access_token/internal"
        resp = await self._http.post(
            url,
            json={
                "app_id": self.config.app_id,
                "app_secret": self.config.app_secret,
            },
        )
        
        if resp.status_code != 200:
            raise FeishuError(f"获取 token 失败: HTTP {resp.status_code}")
        
        data = resp.json()
        if data.get("code") != 0:
            raise FeishuError(f"获取 token 失败: {data}")
        
        token = data["tenant_access_token"]
        expire = data.get("expire", 7200)
        
        # Cache token (提前 5 分钟过期)
        self.config._tenant_access_token = token
        self.config._token_expires_at = time.time() + expire - 300
        
        logger.info(f"获取 tenant_access_token 成功，有效期 {expire}s")
        return token
    
    # ── Message Sending ────────────────────────────────────────────────────────
    
    async def send_message(
        self,
        receive_id: str,
        msg_type: str,
        content: Any,
        receive_id_type: str = "open_id",
    ) -> Dict[str, Any]:
        """
        发送消息
        
        文档：https://open.feishu.cn/document/ukTMukTMukTM/uUjNz4SN2MjL1YzM
        
        Args:
            receive_id: 接收者 ID
            msg_type: 消息类型 (text/post/image/interactive 等)
            content: 消息内容 (JSON string 或 dict)
            receive_id_type: ID 类型 (open_id/user_id/union_id/chat_id)
        
        Returns:
            API 响应
        """
        token = await self.get_tenant_access_token()
        
        # 处理 content
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
        
        url = f"{self.config.base_url}/im/v1/messages"
        params = {"receive_id_type": receive_id_type}
        body = {
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": content,
        }
        
        resp = await self._http.post(
            url,
            params=params,
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )
        
        data = resp.json()
        if data.get("code") != 0:
            logger.error(f"发送消息失败: {data}")
            raise FeishuError(f"发送消息失败: {data.get('msg', data)}")
        
        logger.info(f"消息发送成功 → {receive_id}")
        return data
    
    async def send_text(self, receive_id: str, text: str, receive_id_type: str = "open_id") -> Dict[str, Any]:
        """发送文本消息"""
        return await self.send_message(
            receive_id=receive_id,
            msg_type="text",
            content={"text": text},
            receive_id_type=receive_id_type,
        )
    
    async def send_card(
        self,
        receive_id: str,
        card: Dict[str, Any],
        receive_id_type: str = "open_id",
    ) -> Dict[str, Any]:
        """发送卡片消息"""
        return await self.send_message(
            receive_id=receive_id,
            msg_type="interactive",
            content=card,
            receive_id_type=receive_id_type,
        )
    
    # ── Webhook Event Handling ────────────────────────────────────────────────
    
    def verify_signature(self, timestamp: str, nonce: str, signature: str, body: str) -> bool:
        """
        验证飞书事件签名
        
        文档：https://open.feishu.cn/document/ukTMukTMukTM/uYjNwUjL2YDM14iN2ATN
        """
        if not self.config.verification_token:
            return True  # 未配置 token，跳过验证
        
        token = self.config.verification_token
        sign_base = f"{timestamp}{nonce}{token}{body}"
        expected = hashlib.sha256(sign_base.encode()).hexdigest()
        return hmac.compare_digest(expected, signature)
    
    def handle_url_verification(self, challenge: str) -> Dict[str, str]:
        """
        处理飞书 URL 验证请求
        
        当首次配置 Webhook 时，飞书会发送 challenge 验证 URL 有效性
        """
        logger.info("收到飞书 URL 验证请求")
        return {"challenge": challenge}
    
    async def handle_event(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        处理飞书事件
        
        Args:
            event: 飞书事件体 (已解密)
        
        Returns:
            响应内容（可选）
        """
        event_type = event.get("type") or event.get("header", {}).get("event_type")
        logger.info(f"收到飞书事件: {event_type}")
        
        # ── 消息事件 ────────────────────────────────────────────────────────
        # 新格式: header.event_type == "im.message.receive_v1"
        # 旧格式: type == "event_callback" 且 event.message 存在
        is_message_event = (
            event_type == "im.message.receive_v1" or
            (event_type == "event_callback" and event.get("event", {}).get("message"))
        )
        if is_message_event:
            return await self._handle_message_event(event)
        
        # ── 机器人进群 ────────────────────────────────────────────────────────
        if event_type == "im.chat.member.bot_added_v1":
            return await self._handle_bot_added(event)
        
        # ── 其他事件 ────────────────────────────────────────────────────────
        logger.debug(f"未处理的事件类型: {event_type}")
        return None
    
    async def _handle_message_event(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """处理接收到的消息"""
        event_data = event.get("event", event)
        message = event_data.get("message", {})
        
        sender = event_data.get("sender", {})
        sender_id = sender.get("sender_id", {}).get("open_id", "unknown")
        
        chat_id = message.get("chat_id")
        msg_type = message.get("message_type")
        content = message.get("content", "{}")
        
        # 解析内容
        try:
            content_data = json.loads(content) if isinstance(content, str) else content
        except json.JSONDecodeError:
            content_data = {"raw": content}
        
        logger.info(f"收到消息: sender={sender_id}, chat={chat_id}, type={msg_type}")
        
        # 构建消息对象
        msg_obj = {
            "sender_id": sender_id,
            "chat_id": chat_id,
            "msg_type": msg_type,
            "content": content_data,
            "raw_event": event,
        }
        
        # 调用回调
        if self.on_message:
            try:
                result = self.on_message(msg_obj)
                if result is not None:
                    return result
            except Exception as e:
                logger.exception(f"消息回调处理失败: {e}")
        
        # 默认回复
        return None
    
    async def _handle_bot_added(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理机器人被添加到群聊"""
        event_data = event.get("event", event)
        chat_id = event_data.get("chat_id")
        
        logger.info(f"机器人被添加到群聊: {chat_id}")
        
        # 发送欢迎消息
        try:
            await self.send_text(
                receive_id=chat_id,
                text="👋 你好！我是 Curriculum-Forge 助手。\n发送消息给我来创建任务吧！",
                receive_id_type="chat_id",
            )
        except FeishuError as e:
            logger.error(f"发送欢迎消息失败: {e}")
        
        return {"success": True}


# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────

class FeishuError(Exception):
    """飞书 API 错误"""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Gateway Integration Helper
# ─────────────────────────────────────────────────────────────────────────────

def register_feishu_webhook(app, adapter: FeishuAdapter, path: str = "/webhooks/feishu"):
    """
    在 FastAPI 应用中注册飞书 Webhook 路由
    
    Args:
        app: FastAPI 应用实例
        adapter: FeishuAdapter 实例
        path: Webhook 路径
    """
    from fastapi import Request, Response
    
    @app.post(path, tags=["webhooks"])
    async def feishu_webhook(request: Request):
        """飞书事件推送入口"""
        body = await request.body()
        body_str = body.decode("utf-8")
        
        # ── 签名验证 ────────────────────────────────────────────────────────
        timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
        nonce = request.headers.get("X-Lark-Request-Nonce", "")
        signature = request.headers.get("X-Lark-Signature", "")
        
        if not adapter.verify_signature(timestamp, nonce, signature, body_str):
            logger.warning("飞书签名验证失败")
            return Response(content="Invalid signature", status_code=403)
        
        # ── 解析事件 ────────────────────────────────────────────────────────
        try:
            event = json.loads(body_str)
        except json.JSONDecodeError:
            logger.error("无效的 JSON")
            return Response(content="Invalid JSON", status_code=400)
        
        # ── URL 验证 ────────────────────────────────────────────────────────
        if "challenge" in event:
            return adapter.handle_url_verification(event["challenge"])
        
        # ── 事件处理 ────────────────────────────────────────────────────────
        result = await adapter.handle_event(event)
        
        if result:
            return result
        return {"success": True}
    
    return feishu_webhook
