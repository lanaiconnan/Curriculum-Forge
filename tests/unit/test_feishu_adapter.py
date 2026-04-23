"""
Feishu Adapter 单元测试
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from channels.feishu import (
    FeishuConfig,
    FeishuAdapter,
    FeishuError,
    register_feishu_webhook,
)


# ─────────────────────────────────────────────────────────────────────────────
# Python 3.7 兼容的 AsyncMock
# ─────────────────────────────────────────────────────────────────────────────

def make_async_return(value):
    """创建一个返回指定值的协程函数"""
    async def _coro(*args, **kwargs):
        return value
    return _coro


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def config():
    return FeishuConfig(
        app_id="cli_test123",
        app_secret="secret_test456",
        encrypt_key="",
        verification_token="",
    )


@pytest.fixture
def adapter(config):
    return FeishuAdapter(config=config)


# ─────────────────────────────────────────────────────────────────────────────
# Config Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_config_basic():
    """基本配置"""
    cfg = FeishuConfig(app_id="id123", app_secret="sec456")
    assert cfg.app_id == "id123"
    assert cfg.app_secret == "sec456"
    assert cfg.base_url == "https://open.feishu.cn/open-apis"


def test_config_from_env(monkeypatch):
    """从环境变量加载"""
    monkeypatch.setenv("FEISHU_APP_ID", "env_app_id")
    monkeypatch.setenv("FEISHU_APP_SECRET", "env_secret")
    
    cfg = FeishuConfig.from_env()
    assert cfg.app_id == "env_app_id"
    assert cfg.app_secret == "env_secret"


# ─────────────────────────────────────────────────────────────────────────────
# Token Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_tenant_access_token_success(adapter):
    """获取 token 成功"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "code": 0,
        "tenant_access_token": "t-xxx",
        "expire": 7200,
    }
    
    adapter._http.post = make_async_return(mock_response)
    
    token = await adapter.get_tenant_access_token()
    
    assert token == "t-xxx"
    assert adapter.config._tenant_access_token == "t-xxx"


@pytest.mark.asyncio
async def test_get_token_uses_cache(adapter):
    """使用缓存的 token"""
    adapter.config._tenant_access_token = "cached-token"
    adapter.config._token_expires_at = 9999999999  # far future
    
    token = await adapter.get_tenant_access_token()
    
    assert token == "cached-token"


@pytest.mark.asyncio
async def test_get_token_force_refresh(adapter):
    """强制刷新 token"""
    adapter.config._tenant_access_token = "old-token"
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "code": 0,
        "tenant_access_token": "new-token",
        "expire": 7200,
    }
    
    adapter._http.post = make_async_return(mock_response)
    
    token = await adapter.get_tenant_access_token(force_refresh=True)
    
    assert token == "new-token"


@pytest.mark.asyncio
async def test_get_token_api_error(adapter):
    """API 返回错误"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "code": 10003,
        "msg": "invalid app_id",
    }
    
    adapter._http.post = make_async_return(mock_response)
    
    with pytest.raises(FeishuError):
        await adapter.get_tenant_access_token()


@pytest.mark.asyncio
async def test_get_token_http_error(adapter):
    """HTTP 请求失败"""
    mock_response = MagicMock()
    mock_response.status_code = 500
    
    adapter._http.post = make_async_return(mock_response)
    
    with pytest.raises(FeishuError):
        await adapter.get_tenant_access_token()


# ─────────────────────────────────────────────────────────────────────────────
# Message Sending Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_text_message(adapter):
    """发送文本消息"""
    # Token 响应
    token_response = MagicMock()
    token_response.status_code = 200
    token_response.json.return_value = {
        "code": 0,
        "tenant_access_token": "t-xxx",
        "expire": 7200,
    }
    
    # 发送响应
    send_response = MagicMock()
    send_response.status_code = 200
    send_response.json.return_value = {
        "code": 0,
        "data": {"message_id": "m-xxx"},
    }
    
    call_count = [0]
    async def mock_post(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return token_response
        return send_response
    
    adapter._http.post = mock_post
    
    result = await adapter.send_text("ou_xxx", "Hello!")
    
    assert result["code"] == 0
    assert call_count[0] == 2


@pytest.mark.asyncio
async def test_send_card_message(adapter):
    """发送卡片消息"""
    token_response = MagicMock()
    token_response.status_code = 200
    token_response.json.return_value = {
        "code": 0,
        "tenant_access_token": "t-xxx",
        "expire": 7200,
    }
    
    send_response = MagicMock()
    send_response.status_code = 200
    send_response.json.return_value = {
        "code": 0,
        "data": {"message_id": "m-xxx"},
    }
    
    call_count = [0]
    async def mock_post(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return token_response
        return send_response
    
    adapter._http.post = mock_post
    
    card = {
        "type": "template",
        "data": {
            "template_id": "AAqk*****",
            "template_variable": {"title": "Test Card"},
        },
    }
    
    result = await adapter.send_card("ou_xxx", card)
    
    assert result["code"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Webhook Event Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_url_verification(adapter):
    """URL 验证请求"""
    result = adapter.handle_url_verification("challenge-123")
    assert result == {"challenge": "challenge-123"}


@pytest.mark.asyncio
async def test_handle_message_event(adapter):
    """处理消息事件"""
    received = []
    
    def on_msg(msg):
        received.append(msg)
        return {"replied": True}
    
    adapter.on_message = on_msg
    
    event = {
        "type": "event_callback",
        "event": {
            "sender": {
                "sender_id": {"open_id": "ou_sender"},
            },
            "message": {
                "chat_id": "oc_xxx",
                "message_type": "text",
                "content": '{"text": "Hello"}',
            },
        },
    }
    
    result = await adapter.handle_event(event)
    
    assert result == {"replied": True}
    assert len(received) == 1
    assert received[0]["sender_id"] == "ou_sender"
    assert received[0]["content"]["text"] == "Hello"


@pytest.mark.asyncio
async def test_handle_message_event_no_callback(adapter):
    """处理消息事件但无回调"""
    event = {
        "event": {
            "sender": {"sender_id": {"open_id": "ou_xxx"}},
            "message": {
                "chat_id": "oc_xxx",
                "message_type": "text",
                "content": "{}",
            },
        },
    }
    
    result = await adapter.handle_event(event)
    
    assert result is None


@pytest.mark.asyncio
async def test_handle_bot_added(adapter):
    """机器人被添加到群聊"""
    token_response = MagicMock()
    token_response.status_code = 200
    token_response.json.return_value = {
        "code": 0,
        "tenant_access_token": "t-xxx",
        "expire": 7200,
    }
    
    send_response = MagicMock()
    send_response.status_code = 200
    send_response.json.return_value = {"code": 0}
    
    call_count = [0]
    async def mock_post(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return token_response
        return send_response
    
    adapter._http.post = mock_post
    
    event = {
        "event": {
            "chat_id": "oc_group123",
        },
    }
    
    result = await adapter._handle_bot_added(event)
    
    assert result == {"success": True}


# ─────────────────────────────────────────────────────────────────────────────
# Signature Verification Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_verify_signature_disabled(config):
    """签名验证禁用时跳过"""
    adapter = FeishuAdapter(config=config)
    # 无 encrypt_key 时总是返回 True
    assert adapter.verify_signature("ts", "nonce", "sig", "body")


def test_verify_signature_enabled():
    """签名验证启用"""
    config = FeishuConfig(
        app_id="id",
        app_secret="secret",
        encrypt_key="key",
        verification_token="test_token",
    )
    adapter = FeishuAdapter(config=config)
    
    # 验证返回值类型
    result = adapter.verify_signature("ts", "nonce", "sig", "body")
    assert isinstance(result, bool)
    # 实际签名验证结果（这个测试的签名是假的）
    assert result == False  # 签名不匹配


# ─────────────────────────────────────────────────────────────────────────────
# Cleanup Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_adapter_close(adapter):
    """关闭 HTTP 客户端"""
    await adapter.close()
    # 客户端已关闭，后续操作应报错
    with pytest.raises(RuntimeError):
        await adapter._http.get("https://example.com")
