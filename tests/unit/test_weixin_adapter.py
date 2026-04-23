"""
WeChat Channel Adapter 单元测试

覆盖：Config、URL 验证、消息解析、被动回复、access_token、事件处理
"""

import pytest
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch
import time
import hashlib
import hmac

# Python 3.7 兼容的 AsyncMock
# ─────────────────────────────────────────────────────────────────────────────

def make_async_return(value):
    """创建一个返回指定值的协程函数"""
    async def _coro(*args, **kwargs):
        return value
    return _coro


from channels.weixin import (
    WeixinAdapter,
    WeixinConfig,
    WeixinMessage,
    WeixinError,
    setup_weixin_webhook,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def config():
    """测试配置"""
    return WeixinConfig(
        app_id="test_app_id",
        app_secret="test_app_secret",
        token="test_token_123",
        encoding_aes_key="test_aes_key_123456789012345678901234",
    )


@pytest.fixture
def adapter(config):
    """测试适配器实例"""
    return WeixinAdapter(config=config)


# ─────────────────────────────────────────────────────────────────────────────
# WeixinConfig Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestWeixinConfig:
    
    def test_basic_config(self, config):
        """基本配置"""
        assert config.app_id == "test_app_id"
        assert config.app_secret == "test_app_secret"
        assert config.token == "test_token_123"
        assert config.encoding_aes_key == "test_aes_key_123456789012345678901234"
        assert config.base_url == "https://api.weixin.qq.com"
    
    def test_default_values(self):
        """默认值"""
        config = WeixinConfig(
            app_id="id",
            app_secret="secret",
            token="token",
        )
        assert config.encoding_aes_key == ""
        assert config.base_url == "https://api.weixin.qq.com"
        assert config._access_token is None
        assert config._token_expires_at == 0.0
    
    def test_from_env_not_throw(self):
        """from_env 在无环境变量时不抛异常"""
        config = WeixinConfig.from_env()
        assert config.app_id == ""
        assert config.app_secret == ""


# ─────────────────────────────────────────────────────────────────────────────
# WeixinMessage Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestWeixinMessage:
    
    TEXT_XML = """<xml>
<ToUserName><![CDATA[to_user_123]]></ToUserName>
<FromUserName><![CDATA[from_user_456]]></FromUserName>
<CreateTime>1234567890</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[Hello World]]></Content>
<MsgId>9876543210</MsgId>
</xml>"""
    
    def test_parse_text_message(self):
        """解析文本消息"""
        msg = WeixinMessage.from_xml(self.TEXT_XML)
        
        assert msg.to_user == "to_user_123"
        assert msg.from_user == "from_user_456"
        assert msg.create_time == 1234567890
        assert msg.msg_type == "text"
        assert msg.content == "Hello World"
        assert msg.msg_id == 9876543210
        assert msg.raw_xml == self.TEXT_XML
    
    def test_parse_image_message(self):
        """解析图片消息"""
        xml = """<xml>
<ToUserName><![CDATA[to_user]]></ToUserName>
<FromUserName><![CDATA[from_user]]></FromUserName>
<CreateTime>1234567890</CreateTime>
<MsgType><![CDATA[image]]></MsgType>
<PicUrl><![CDATA[http://example.com/pic.jpg]]></PicUrl>
<MediaId><![CDATA[media_123]]></MediaId>
<MsgId>123</MsgId>
</xml>"""
        msg = WeixinMessage.from_xml(xml)
        
        assert msg.msg_type == "image"
        assert msg.pic_url == "http://example.com/pic.jpg"
        assert msg.media_id == "media_123"
    
    def test_parse_location_message(self):
        """解析位置消息"""
        xml = """<xml>
<ToUserName><![CDATA[to_user]]></ToUserName>
<FromUserName><![CDATA[from_user]]></FromUserName>
<CreateTime>1234567890</CreateTime>
<MsgType><![CDATA[location]]></MsgType>
<Location_X>23.123456</Location_X>
<Location_Y>113.654321</Location_Y>
<Scale>15</Scale>
<Label><![CDATA[广州市天河区]]></Label>
<MsgId>123</MsgId>
</xml>"""
        msg = WeixinMessage.from_xml(xml)
        
        assert msg.msg_type == "location"
        assert msg.location_x == 23.123456
        assert msg.location_y == 113.654321
        assert msg.scale == 15
        assert msg.label == "广州市天河区"
    
    def test_parse_link_message(self):
        """解析链接消息"""
        xml = """<xml>
<ToUserName><![CDATA[to_user]]></ToUserName>
<FromUserName><![CDATA[from_user]]></FromUserName>
<CreateTime>1234567890</CreateTime>
<MsgType><![CDATA[link]]></MsgType>
<Title><![CDATA[文章标题]]></Title>
<Description><![CDATA[文章描述]]></Description>
<Url><![CDATA[http://example.com/article]]></Url>
<MsgId>123</MsgId>
</xml>"""
        msg = WeixinMessage.from_xml(xml)
        
        assert msg.msg_type == "link"
        assert msg.title == "文章标题"
        assert msg.description == "文章描述"
        assert msg.url == "http://example.com/article"
    
    def test_parse_minimal_xml(self):
        """解析最小 XML（缺少可选字段）"""
        xml = """<xml>
<ToUserName><![CDATA[to]]></ToUserName>
<FromUserName><![CDATA[from]]></FromUserName>
<CreateTime>1234567890</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[Hi]]></Content>
<MsgId>1</MsgId>
</xml>"""
        msg = WeixinMessage.from_xml(xml)
        
        assert msg.media_id is None
        assert msg.pic_url is None
        assert msg.location_x is None
        assert msg.title is None


# ─────────────────────────────────────────────────────────────────────────────
# WeixinAdapter URL Verification Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestWeixinAdapterVerify:
    
    def test_verify_url_success(self, adapter):
        """URL 验证成功"""
        timestamp = "1609459200"
        nonce = "random_nonce"
        
        # 生成正确的签名
        parts = sorted([adapter.config.token, timestamp, nonce])
        sign_base = "".join(parts)
        signature = hashlib.sha1(sign_base.encode("utf-8")).hexdigest()
        
        result = adapter.verify_url(signature, timestamp, nonce, "echostr_value")
        assert result is True
    
    def test_verify_url_invalid_signature(self, adapter):
        """URL 验证失败（错误签名）"""
        result = adapter.verify_url("invalid_signature", "1609459200", "nonce", "echostr")
        assert result is False
    
    def test_verify_url_no_token(self):
        """URL 验证（未配置 token）"""
        config = WeixinConfig(app_id="id", app_secret="secret", token="")
        adapter = WeixinAdapter(config)
        
        # 未配置 token 时返回 True
        result = adapter.verify_url("any_sig", "ts", "nonce", "echostr")
        assert result is True


# ─────────────────────────────────────────────────────────────────────────────
# WeixinAdapter Reply Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestWeixinAdapterReply:
    
    def test_build_text_reply(self, adapter):
        """构建文本回复"""
        xml = adapter.build_text_reply(
            to_user="user_openid",
            from_user="app_id",
            content="Hello, World!",
        )
        
        assert "<![CDATA[user_openid]]>" in xml
        assert "<![CDATA[app_id]]>" in xml
        assert "<![CDATA[Hello, World!]]>" in xml
        assert "<![CDATA[text]]>" in xml
        assert "<CreateTime>" in xml
    
    def test_build_text_reply_cdata_escaping(self, adapter):
        """CDATA 转义"""
        xml = adapter.build_text_reply(
            to_user="user",
            from_user="app",
            content="<script>alert('xss')</script>",
        )
        
        assert "<![CDATA[<script>alert('xss')</script>]]>" in xml
        assert "<Content>" in xml
    
    def test_reply_xml_structure(self, adapter):
        """回复 XML 结构"""
        xml = adapter.build_text_reply("u", "a", "hi")
        root = ET.fromstring(xml)
        
        assert root.tag == "xml"
        assert root.find("ToUserName").text == "u"
        assert root.find("FromUserName").text == "a"
        assert root.find("MsgType").text == "text"
        assert root.find("Content").text == "hi"
        assert root.find("CreateTime") is not None


# ─────────────────────────────────────────────────────────────────────────────
# WeixinAdapter Token Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestWeixinAdapterToken:
    
    async def test_get_access_token_success(self, adapter):
        """获取 access_token 成功"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "mock_token_12345",
            "expires_in": 7200,
        }
        
        # 直接赋值（feishu 模式）
        adapter._http.get = make_async_return(mock_response)
        
        token = await adapter.get_access_token()
        
        assert token == "mock_token_12345"
        assert adapter.config._access_token == "mock_token_12345"
    
    async def test_get_access_token_cached(self, adapter):
        """Token 缓存"""
        # 先设置一个已缓存的 token
        adapter.config._access_token = "cached_token"
        adapter.config._token_expires_at = time.time() + 3600  # 还有 1 小时
        
        # 不需要 mock，因为不会发请求
        token = await adapter.get_access_token()
        
        assert token == "cached_token"
    
    async def test_get_access_token_force_refresh(self, adapter):
        """强制刷新 Token"""
        adapter.config._access_token = "old_token"
        adapter.config._token_expires_at = time.time() + 3600
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_token",
            "expires_in": 7200,
        }
        
        adapter._http.get = make_async_return(mock_response)
        
        token = await adapter.get_access_token(force_refresh=True)
        
        assert token == "new_token"
        assert adapter.config._access_token == "new_token"
    
    async def test_get_access_token_api_error(self, adapter):
        """API 错误"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "errcode": 40001,
            "errmsg": "invalid credential",
        }
        
        adapter._http.get = make_async_return(mock_response)
        
        with pytest.raises(WeixinError) as exc_info:
            await adapter.get_access_token()
        
        assert "invalid credential" in str(exc_info.value)
    
    async def test_get_access_token_http_error(self, adapter):
        """HTTP 网络错误"""
        # WeixinError 包装原始异常
        async def http_error(*args, **kwargs):
            raise WeixinError("Network error: connection refused")
        
        adapter._http.get = http_error
        
        with pytest.raises(WeixinError) as exc_info:
            await adapter.get_access_token()
        assert "Network error" in str(exc_info.value)


# ─────────────────────────────────────────────────────────────────────────────
# WeixinAdapter Event Handling Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestWeixinAdapterEvent:
    
    async def test_handle_event_text_message(self, adapter):
        """处理文本消息（默认回复）"""
        xml_body = """<xml>
<ToUserName><![CDATA[gh_123456]]></ToUserName>
<FromUserName><![CDATA[user_openid]]></FromUserName>
<CreateTime>1234567890</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[test message]]></Content>
<MsgId>1234567890123456</MsgId>
</xml>"""
        
        mock_request = MagicMock()
        mock_request.body = make_async_return(xml_body.encode("utf-8"))
        
        reply = await adapter.handle_event(mock_request)
        
        # 默认回复：收到消息
        assert "<![CDATA[text]]>" in reply
        assert "<![CDATA[收到消息]]>" in reply
        # ToUserName = 公众号（gh_123456 = ToUserName of incoming）
        assert "<![CDATA[gh_123456]]>" in reply
        # FromUserName = 用户（user_openid = FromUserName of incoming）
        assert "<![CDATA[user_openid]]>" in reply
    
    async def test_handle_event_with_callback(self, adapter):
        """处理消息（带回调）"""
        callback_response = "callback response"
        adapter.on_message = MagicMock(return_value=callback_response)
        
        xml_body = """<xml>
<ToUserName><![CDATA[gh_123]]></ToUserName>
<FromUserName><![CDATA[user_id]]></FromUserName>
<CreateTime>1234567890</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[hello]]></Content>
<MsgId>1</MsgId>
</xml>"""
        
        mock_request = MagicMock()
        mock_request.body = make_async_return(xml_body.encode("utf-8"))
        
        reply = await adapter.handle_event(mock_request)
        
        assert reply == callback_response
        adapter.on_message.assert_called_once()
        
        # 验证传递给回调的 WeixinMessage
        call_arg = adapter.on_message.call_args[0][0]
        assert isinstance(call_arg, WeixinMessage)
        assert call_arg.content == "hello"
    
    async def test_handle_event_xml_parse_error(self, adapter):
        """XML 解析错误"""
        mock_request = MagicMock()
        mock_request.body = make_async_return(b"invalid xml")
        
        reply = await adapter.handle_event(mock_request)
        
        # 应该返回错误回复
        assert "<![CDATA[消息解析失败]]>" in reply


# ─────────────────────────────────────────────────────────────────────────────
# WeixinAdapter Template Message Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestWeixinAdapterTemplate:
    
    async def test_send_template_message_success(self, adapter):
        """发送模板消息成功"""
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "access_token": "token_123",
            "expires_in": 7200,
        }
        
        send_response = MagicMock()
        send_response.json.return_value = {"errcode": 0, "msgid": 123456}
        
        # 先设置 token 响应，再设置发送响应
        adapter._http.get = make_async_return(token_response)
        adapter._http.post = make_async_return(send_response)
        
        result = await adapter.send_template_message(
            to_user="user_openid",
            template_id="template_123",
            data={"first": {"value": "标题", "color": "#173177"}},
            url="https://example.com",
        )
        
        assert result["errcode"] == 0
        assert result["msgid"] == 123456
    
    async def test_send_template_message_api_error(self, adapter):
        """模板消息 API 错误"""
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "access_token": "token_123",
            "expires_in": 7200,
        }
        
        send_response = MagicMock()
        send_response.json.return_value = {
            "errcode": 40003,
            "errmsg": "invalid openid",
        }
        
        adapter._http.get = make_async_return(token_response)
        adapter._http.post = make_async_return(send_response)
        
        with pytest.raises(WeixinError) as exc_info:
            await adapter.send_template_message(
                to_user="invalid_user",
                template_id="template_123",
                data={},
            )
        
        assert "invalid openid" in str(exc_info.value)


# ─────────────────────────────────────────────────────────────────────────────
# register_weixin_webhook / setup_weixin_webhook Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_setup_weixin_webhook():
    """测试 setup_weixin_webhook 工厂函数"""
    from fastapi import FastAPI, Request
    
    app = FastAPI()
    
    adapter = setup_weixin_webhook(
        app,
        app_id="app_id_123",
        app_secret="app_secret_456",
        token="token_789",
        encoding_aes_key="aes_key_123456789012345678901234",
        webhook_path="/webhooks/weixin",
    )
    
    assert isinstance(adapter, WeixinAdapter)
    assert adapter.config.app_id == "app_id_123"
    assert adapter.config.app_secret == "app_secret_456"
    assert adapter.config.token == "token_789"
    
    # 验证路由已注册（检查 path）
    paths = [r.path for r in app.routes]
    assert "/webhooks/weixin" in paths


def test_setup_weixin_webhook_with_callback():
    """测试带回调的 setup_weixin_webhook"""
    from fastapi import FastAPI
    
    app = FastAPI()
    callback = MagicMock()
    
    adapter = setup_weixin_webhook(
        app,
        app_id="id",
        app_secret="secret",
        token="token",
        on_message=callback,
    )
    
    assert adapter.on_message is callback
