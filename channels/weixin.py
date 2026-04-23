"""
WeChat Channel Adapter

微信公众号/企业微信集成：
- Webhook 事件接收（消息推送）
- 被动回复消息（XML 格式）
- 模板消息发送（主动通知）
- Gateway 集成（POST /webhooks/weixin）

微信公众号接入文档：
https://developers.weixin.qq.com/doc/offiaccount/Getting_Started/Overview.html
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import httpx
from fastapi import Request, Response

logger = logging.getLogger("weixin")


# ─────────────────────────────────────────────────────────────────────────────
# WeChat Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WeixinConfig:
    """微信公众号配置"""
    
    app_id: str          # AppID
    app_secret: str      # AppSecret
    token: str          # 用于签名验证（公众平台配置的 Token）
    encoding_aes_key: str = ""  # 可选：消息加解密密钥
    
    # API endpoints
    base_url: str = "https://api.weixin.qq.com"
    
    # Cache
    _access_token: Optional[str] = field(default=None, repr=False)
    _token_expires_at: float = field(default=0.0, repr=False)
    
    @classmethod
    def from_env(cls) -> "WeixinConfig":
        """从环境变量加载配置"""
        import os
        return cls(
            app_id=os.getenv("WEIXIN_APP_ID", ""),
            app_secret=os.getenv("WEIXIN_APP_SECRET", ""),
            token=os.getenv("WEIXIN_TOKEN", ""),
            encoding_aes_key=os.getenv("WEIXIN_ENCODING_AES_KEY", ""),
        )


# ─────────────────────────────────────────────────────────────────────────────
# WeChat Message
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WeixinMessage:
    """微信消息"""
    
    to_user: str        # 发送者的 OpenID
    from_user: str      # 开发者微信号（公众号号）
    msg_type: str       # text/image/voice/video/location/link
    content: str        # 消息内容（文本消息）
    msg_id: int        # 消息 ID
    create_time: int   # 创建时间戳
    
    # 可选字段（根据消息类型）
    media_id: Optional[str] = None       # 图片/语音/视频
    pic_url: Optional[str] = None       # 图片链接
    location_x: Optional[float] = None   # 位置纬度
    location_y: Optional[float] = None   # 位置经度
    scale: Optional[int] = None          # 地图缩放大小
    label: Optional[str] = None          # 位置信息
    title: Optional[str] = None          # 链接/视频标题
    description: Optional[str] = None    # 链接描述
    url: Optional[str] = None            # 链接 URL
    
    # 原始 XML
    raw_xml: str = ""
    
    @classmethod
    def from_xml(cls, xml_str: str) -> "WeixinMessage":
        """
        从 XML 解析微信消息
        
        Args:
            xml_str: 原始 XML 字符串
        
        Returns:
            WeixinMessage 实例
        """
        root = ET.fromstring(xml_str)
        
        def get_text(tag: str) -> Optional[str]:
            el = root.find(tag)
            return el.text if el is not None else None
        
        def get_float(tag: str) -> Optional[float]:
            val = get_text(tag)
            return float(val) if val else None
        
        def get_int(tag: str) -> Optional[int]:
            val = get_text(tag)
            return int(val) if val else None
        
        return cls(
            to_user=get_text("ToUserName") or "",
            from_user=get_text("FromUserName") or "",
            msg_type=get_text("MsgType") or "text",
            content=get_text("Content") or "",
            msg_id=get_int("MsgId") or 0,
            create_time=get_int("CreateTime") or 0,
            media_id=get_text("MediaId"),
            pic_url=get_text("PicUrl"),
            location_x=get_float("Location_X"),
            location_y=get_float("Location_Y"),
            scale=get_int("Scale"),
            label=get_text("Label"),
            title=get_text("Title"),
            description=get_text("Description"),
            url=get_text("Url"),
            raw_xml=xml_str,
        )


# ─────────────────────────────────────────────────────────────────────────────
# WeChat Adapter
# ─────────────────────────────────────────────────────────────────────────────

class WeixinAdapter:
    """
    微信渠道适配器
    
    功能：
    - URL 验证（GET /webhooks/weixin）
    - 接收消息事件（POST /webhooks/weixin）
    - 被动回复消息
    - 模板消息发送（主动通知）
    - 与 Gateway 集成
    """
    
    def __init__(
        self,
        config: WeixinConfig,
        on_message: Optional[callable] = None,
    ):
        self.config = config
        self.on_message = on_message
        self._http = httpx.AsyncClient(timeout=30.0)
    
    async def close(self):
        """关闭 HTTP 客户端"""
        await self._http.aclose()
    
    # ── Authentication ────────────────────────────────────────────────────────
    
    async def get_access_token(self, force_refresh: bool = False) -> str:
        """
        获取 access_token
        
        文档：https://developers.weixin.qq.com/doc/offiaccount/Basic_Information/Get_access_token.html
        """
        # Check cache
        if not force_refresh and self.config._access_token:
            if time.time() < self.config._token_expires_at:
                return self.config._access_token
        
        url = f"{self.config.base_url}/cgi-bin/token"
        params = {
            "grant_type": "client_credential",
            "appid": self.config.app_id,
            "secret": self.config.app_secret,
        }
        
        resp = await self._http.get(url, params=params)
        
        if resp.status_code != 200:
            raise WeixinError(f"获取 access_token 失败: HTTP {resp.status_code}")
        
        data = resp.json()
        if "errcode" in data and data["errcode"] != 0:
            raise WeixinError(f"获取 access_token 失败: {data.get('errmsg', data)}")
        
        token = data["access_token"]
        expires_in = data.get("expires_in", 7200)
        
        # Cache token (提前 5 分钟过期)
        self.config._access_token = token
        self.config._token_expires_at = time.time() + expires_in - 300
        
        logger.info(f"获取 access_token 成功，有效期 {expires_in}s")
        return token
    
    # ── URL Verification ──────────────────────────────────────────────────────
    
    def verify_url(self, signature: str, timestamp: str, nonce: str, echostr: str) -> bool:
        """
        验证微信服务器 URL
        
        微信服务器会发送 GET 请求验证 URL 是否可用
        验证方式：sha1(token, timestamp, nonce) == signature
        
        Args:
            signature: 微信签名
            timestamp: 时间戳
            nonce: 随机数
            echostr: 随机字符串（验证成功时需原样返回）
        
        Returns:
            True 表示验证通过
        """
        if not self.config.token:
            logger.warning("未配置 WEIXIN_TOKEN，跳过 URL 验证")
            return True
        
        # 排序 + 拼接
        parts = sorted([self.config.token, timestamp, nonce])
        sign_base = "".join(parts)
        
        # SHA1
        expected = hashlib.sha1(sign_base.encode("utf-8")).hexdigest()
        result = hmac.compare_digest(expected, signature)
        
        if not result:
            logger.warning(f"URL 验证失败: expected={expected}, got={signature}")
        
        return result
    
    # ── Message Parsing ───────────────────────────────────────────────────────
    
    def parse_message(self, xml_body: str) -> WeixinMessage:
        """
        解析微信消息 XML
        
        Args:
            xml_body: 原始 XML 字符串
        
        Returns:
            WeixinMessage 实例
        """
        return WeixinMessage.from_xml(xml_body)
    
    # ── Passive Reply ─────────────────────────────────────────────────────────
    
    def build_text_reply(
        self,
        to_user: str,
        from_user: str,
        content: str,
    ) -> str:
        """
        构建文本消息被动回复 XML
        
        文档：https://developers.weixin.qq.com/doc/offiaccount/Message_Management/Passive_user_reply_message.html
        """
        return self._build_reply(
            to_user=to_user,
            from_user=from_user,
            msg_type="text",
            content=content,
        )
    
    def _build_reply(
        self,
        to_user: str,
        from_user: str,
        msg_type: str,
        content: str = "",
        media_id: str = "",
        title: str = "",
        description: str = "",
        music_url: str = "",
        hq_music_url: str = "",
        thumb_media_id: str = "",
    ) -> str:
        """
        构建被动回复 XML（通用方法）
        """
        now = int(time.time())
        
        if msg_type == "text":
            content_xml = f"<Content><![CDATA[{content}]]></Content>"
        elif msg_type == "image":
            content_xml = f"<Image><MediaId><![CDATA[{media_id}]]></MediaId></Image>"
        elif msg_type == "voice":
            content_xml = f"<Voice><MediaId><![CDATA[{media_id}]]></MediaId></Voice>"
        elif msg_type == "video":
            content_xml = (
                f"<Video>"
                f"<MediaId><![CDATA[{media_id}]]></MediaId>"
                f"<Title><![CDATA[{title}]]></Title>"
                f"<Description><![CDATA[{description}]]></Description>"
                f"</Video>"
            )
        elif msg_type == "music":
            content_xml = (
                f"<Music>"
                f"<Title><![CDATA[{title}]]></Title>"
                f"<Description><![CDATA[{description}]]></Description>"
                f"<MusicUrl><![CDATA[{music_url}]]></MusicUrl>"
                f"<HQMusicUrl><![CDATA[{hq_music_url}]]></HQMusicUrl>"
                f"<ThumbMediaId><![CDATA[{thumb_media_id}]]></ThumbMediaId>"
                f"</Music>"
            )
        elif msg_type == "news":
            # 图文消息（单条）
            content_xml = (
                f"<ArticleCount>1</ArticleCount>"
                f"<Articles>"
                f"<item>"
                f"<Title><![CDATA[{title}]]></Title>"
                f"<Description><![CDATA[{description}]]></Description>"
                f"<PicUrl><![CDATA[{content}]]></PicUrl>"  # content 作为图片 URL
                f"<Url><![CDATA[{url}]]></Url>"
                f"</item>"
                f"</Articles>"
            )
        else:
            content_xml = ""
        
        return (
            f"<xml>"
            f"<ToUserName><![CDATA[{to_user}]]></ToUserName>"
            f"<FromUserName><![CDATA[{from_user}]]></FromUserName>"
            f"<CreateTime>{now}</CreateTime>"
            f"<MsgType><![CDATA[{msg_type}]]></MsgType>"
            f"{content_xml}"
            f"</xml>"
        )
    
    # ── Template Message ──────────────────────────────────────────────────────
    
    async def send_template_message(
        self,
        to_user: str,
        template_id: str,
        data: Dict[str, Any],
        url: str = "",
    ) -> Dict[str, Any]:
        """
        发送模板消息（主动通知）
        
        文档：https://developers.weixin.qq.com/doc/offiaccount/Message_Operations/Template_Message_Operation.html
        
        Args:
            to_user: 接收者 OpenID
            template_id: 模板 ID
            data: 模板数据，格式：{"key": {"value": "xxx", "color": "#xxx"}}
            url: 点击模板消息跳转的链接（可选）
        
        Returns:
            API 响应
        """
        token = await self.get_access_token()
        
        api_url = f"{self.config.base_url}/cgi-bin/message/template/send"
        params = {"access_token": token}
        
        body = {
            "touser": to_user,
            "template_id": template_id,
            "data": data,
        }
        if url:
            body["url"] = url
        
        resp = await self._http.post(api_url, params=params, json=body)
        result = resp.json()
        
        if result.get("errcode") != 0:
            logger.error(f"模板消息发送失败: {result}")
            raise WeixinError(f"模板消息发送失败: {result.get('errmsg', result)}")
        
        logger.info(f"模板消息发送成功 → {to_user}, msgid={result.get('msgid')}")
        return result
    
    async def send_text(self, to_user: str, text: str) -> str:
        """
        发送文本消息（被动回复）
        
        Args:
            to_user: 接收者 OpenID
            text: 消息内容
        
        Returns:
            回复 XML 字符串
        """
        return self.build_text_reply(
            to_user=to_user,
            from_user=self.config.app_id,  # 公众号 ID 作为发送者
            content=text,
        )
    
    # ── Event Handling ────────────────────────────────────────────────────────
    
    async def handle_event(self, request) -> str:
        """
        处理微信事件（Webhook POST 请求）
        
        Args:
            request: FastAPI Request 对象
        
        Returns:
            回复 XML 字符串
        """
        body = await request.body()
        xml_str = body.decode("utf-8")
        
        logger.debug(f"收到微信消息: {xml_str[:200]}...")
        
        # 解析消息
        try:
            msg = self.parse_message(xml_str)
        except ET.ParseError:
            logger.error(f"XML 解析失败: {xml_str}")
            return self.build_text_reply(
                to_user="unknown",
                from_user=self.config.app_id,
                content="消息解析失败",
            )
        
        # 记录消息
        logger.info(
            f"收到微信消息: type={msg.msg_type}, from={msg.to_user}, "
            f"content={msg.content[:50] if msg.content else ''}"
        )
        
        # 调用回调
        if self.on_message:
            try:
                result = self.on_message(msg)
                if result is not None:
                    return result
            except Exception as e:
                logger.exception(f"消息回调处理失败: {e}")
                return self.build_text_reply(
                    to_user=msg.to_user,
                    from_user=self.config.app_id,
                    content=f"处理失败: {str(e)[:50]}",
                )
        
        # 默认回复（echo）
        return self.build_text_reply(
            to_user=msg.to_user,
            from_user=msg.from_user,
            content="收到消息",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────

class WeixinError(Exception):
    """微信 API 错误"""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Gateway Integration Helper
# ─────────────────────────────────────────────────────────────────────────────

def register_weixin_webhook(
    app,
    adapter: WeixinAdapter,
    path: str = "/webhooks/weixin",
):
    """
    在 FastAPI 应用中注册微信 Webhook 路由
    
    Args:
        app: FastAPI 应用实例
        adapter: WeixinAdapter 实例
        path: Webhook 路径
    """
    
    @app.get(path, tags=["webhooks"])
    async def weixin_verify(
        signature: str,
        timestamp: str,
        nonce: str,
        echostr: str = "",
    ):
        """
        微信 URL 验证（GET 请求）
        
        首次配置服务器 URL 时，微信会发送 GET 请求验证
        """
        if adapter.verify_url(signature, timestamp, nonce, echostr):
            return Response(content=echostr, media_type="text/plain")
        return Response(content="Invalid signature", status_code=403)
    
    @app.post(path, tags=["webhooks"])
    async def weixin_webhook(request: Request):
        """微信事件推送入口（POST 请求）"""
        reply_xml = await adapter.handle_event(request)
        return Response(content=reply_xml, media_type="application/xml")
    
    return weixin_webhook


# ─────────────────────────────────────────────────────────────────────────────
# Convenience Factory
# ─────────────────────────────────────────────────────────────────────────────

def setup_weixin_webhook(
    app,
    app_id: str,
    app_secret: str,
    token: str,
    encoding_aes_key: str = "",
    webhook_path: str = "/webhooks/weixin",
    on_message: Optional[callable] = None,
) -> WeixinAdapter:
    """
    创建并注册微信 Webhook
    
    Args:
        app: FastAPI 应用实例
        app_id: 微信公众号 AppID
        app_secret: 微信公众号 AppSecret
        token: 微信公众平台配置的 Token
        encoding_aes_key: 可选，消息加解密密钥
        webhook_path: Webhook 路径
        on_message: 消息回调函数
    
    Returns:
        WeixinAdapter 实例
    """
    config = WeixinConfig(
        app_id=app_id,
        app_secret=app_secret,
        token=token,
        encoding_aes_key=encoding_aes_key,
    )
    adapter = WeixinAdapter(config=config, on_message=on_message)
    register_weixin_webhook(app, adapter, path=webhook_path)
    return adapter
