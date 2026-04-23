"""
ChannelJobBridge 单元测试

测试 Channel → Job 闭环：
- 命令解析
- Bridge on_message 回调
- Gateway 集成
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass

from channels.bridge import (
    ChannelJobBridge,
    BridgeConfig,
    ParsedCommand,
    parse_command,
    create_bridge,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def bridge():
    """创建 ChannelJobBridge 实例"""
    config = BridgeConfig(
        gateway_url="http://localhost:9999",  # 非真实端口
        default_profile="rl_controller",
    )
    b = ChannelJobBridge(config=config)
    # 替换内部 HTTP 客户端为 mock
    b._http_sync = MagicMock()
    yield b


def _mock_response(status_code=200, json_data=None):
    """创建 mock HTTP 响应"""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Command Parsing Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_help_command():
    """测试 help 命令解析"""
    for text in ["help", "帮助", "?", "？"]:
        cmd = parse_command(text)
        assert cmd.action == "help", f"Expected help, got {cmd.action} for '{text}'"


def test_parse_run_command():
    """测试 run 命令解析"""
    cmd = parse_command("run 机器学习")
    assert cmd.action == "run"
    assert cmd.topic == "机器学习"
    assert cmd.profile is None

    cmd2 = parse_command("run Python入门 with pure_harness")
    assert cmd2.action == "run"
    assert cmd2.topic == "python入门"
    assert cmd2.profile == "pure_harness"


def test_parse_status_command():
    """测试 status 命令解析"""
    cmd = parse_command("status")
    assert cmd.action == "status"
    assert cmd.job_id is None

    cmd2 = parse_command("status abc123-def456")
    assert cmd2.action == "status"
    assert cmd2.job_id == "abc123-def456"


def test_parse_list_command():
    """测试 list 命令解析"""
    cmd = parse_command("list")
    assert cmd.action == "list"
    assert cmd.extra.get("limit") == 5

    cmd2 = parse_command("list 10")
    assert cmd2.action == "list"
    assert cmd2.extra.get("limit") == 10


def test_parse_log_command():
    """测试 log 命令解析"""
    cmd = parse_command("log abc123")
    assert cmd.action == "log"
    assert cmd.job_id == "abc123"


def test_parse_unknown_command():
    """测试未知命令解析"""
    cmd = parse_command("随便说说")
    assert cmd.action == "unknown"
    assert cmd.extra.get("raw_text") == "随便说说"


# ─────────────────────────────────────────────────────────────────────────────
# Bridge on_message Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_bridge_help_reply(bridge):
    """测试 help 命令返回帮助文本"""
    reply = bridge.on_message({"content": {"text": "help"}})
    assert reply is not None
    assert "可用命令" in reply or "run" in reply.lower()


def test_bridge_unknown_command_returns_none(bridge):
    """测试未知命令返回 None（不回复）"""
    reply = bridge.on_message({"content": {"text": "随便聊聊"}})
    assert reply is None


def test_bridge_empty_message_returns_none(bridge):
    """测试空消息返回 None"""
    reply = bridge.on_message({})
    assert reply is None

    reply2 = bridge.on_message({"content": {}})
    assert reply2 is None


def test_bridge_create_job_sync(bridge):
    """测试同步创建 Job"""
    bridge._http_sync.post.return_value = _mock_response(201, {
        "job": {"id": "job-123", "state": "pending"},
        "created": True,
    })

    reply = bridge.on_message({"content": {"text": "run 测试主题"}, "sender_id": "user-001"})

    assert reply is not None
    assert "任务已创建" in reply
    assert "job-123" in reply

    # 验证 HTTP 调用
    bridge._http_sync.post.assert_called_once()
    call_args = bridge._http_sync.post.call_args
    # Python 3.7: call_args[0] 是 args tuple, call_args[1] 是 kwargs dict
    url = call_args[0][0] if call_args[0] else call_args[1].get('url', '')
    assert "jobs" in url


def test_bridge_list_jobs_sync(bridge):
    """测试列出 Jobs"""
    bridge._http_sync.get.return_value = _mock_response(200, {
        "jobs": [
            {"id": "job-1", "state": "completed", "phase": "REVIEW", "description": "测试任务"},
            {"id": "job-2", "state": "running", "phase": "HARNESS", "description": "另一个任务"},
        ],
        "total": 2,
    })

    reply = bridge.on_message({"content": {"text": "list"}})

    assert reply is not None
    assert "任务" in reply
    assert "completed" in reply.lower() or "job-1" in reply


def test_bridge_list_jobs_empty(bridge):
    """测试空 Job 列表"""
    bridge._http_sync.get.return_value = _mock_response(200, {
        "jobs": [],
        "total": 0,
    })

    reply = bridge.on_message({"content": {"text": "list"}})

    assert reply is not None
    assert "暂无" in reply


def test_bridge_get_status_sync(bridge):
    """测试查询 Job 状态"""
    bridge._http_sync.get.return_value = _mock_response(200, {
        "id": "job-123",
        "state": "running",
        "phase": "HARNESS",
        "description": "测试任务描述",
        "metrics": {"progress": 50},
    })

    reply = bridge.on_message({"content": {"text": "status job-123"}, "sender_id": "u1"})

    assert reply is not None
    # 状态可能是 running 或 emoji 形式
    assert "running" in reply.lower() or "🔄" in reply


def test_bridge_status_latest_job(bridge):
    """测试不带 job_id 的 status 命令"""
    bridge._http_sync.get.return_value = _mock_response(200, {
        "jobs": [{"id": "latest-job", "state": "completed", "phase": "REVIEW", "description": "最新任务"}],
        "total": 1,
    })

    # 第二次 get 调用（查具体 job）
    bridge._http_sync.get.side_effect = [
        _mock_response(200, {
            "jobs": [{"id": "latest-job"}],
            "total": 1,
        }),
        _mock_response(200, {
            "id": "latest-job",
            "state": "completed",
            "phase": "REVIEW",
            "description": "最新任务",
        }),
    ]

    reply = bridge.on_message({"content": {"text": "status"}})

    assert reply is not None
    assert "completed" in reply.lower()


def test_bridge_weixin_message(bridge):
    """测试处理微信消息（WeixinMessage 对象）"""
    @dataclass
    class MockWeixinMessage:
        content: str
        to_user: str = "user-001"
        from_user: str = "gh_xxx"
        msg_type: str = "text"

    bridge._http_sync.post.return_value = _mock_response(201, {
        "job": {"id": "job-456", "state": "pending"},
        "created": True,
    })

    msg = MockWeixinMessage(content="run 测试")
    reply = bridge.on_message(msg)

    assert reply is not None
    assert "任务已创建" in reply


def test_bridge_run_with_profile(bridge):
    """测试带 profile 的 run 命令"""
    bridge._http_sync.post.return_value = _mock_response(201, {
        "job": {"id": "job-789", "state": "pending"},
        "created": True,
    })

    reply = bridge.on_message({"content": {"text": "run 测试 with pure_harness"}, "sender_id": "u1"})

    assert reply is not None
    assert "任务已创建" in reply

    # 验证传了正确的 profile
    call_args = bridge._http_sync.post.call_args
    # Python 3.7: call_args[1] 是 kwargs dict
    body = call_args[1].get("json", {})
    assert body.get("profile") == "pure_harness"


def test_bridge_gateway_connect_error(bridge):
    """测试 Gateway 连接失败"""
    import httpx
    bridge._http_sync.post.side_effect = httpx.ConnectError("Connection refused")

    reply = bridge.on_message({"content": {"text": "run 测试"}, "sender_id": "user-001"})

    assert reply is not None
    assert "Gateway 未启动" in reply


def test_bridge_profile_not_found(bridge):
    """测试 Profile 不存在"""
    import httpx
    mock_resp = _mock_response(404, {"detail": "Profile not found"})
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404", request=MagicMock(), response=mock_resp
    )
    bridge._http_sync.post.side_effect = mock_resp.raise_for_status

    # Actually, we need the post to return the response and then raise_for_status to fail
    # Let's use a different approach
    bridge._http_sync.post.return_value = mock_resp
    bridge._http_sync.post.side_effect = None

    # Override raise_for_status to raise
    def raise_404():
        raise httpx.HTTPStatusError("404", request=MagicMock(), response=mock_resp)
    mock_resp.raise_for_status = raise_404

    reply = bridge.on_message({"content": {"text": "run 测试"}, "sender_id": "user-001"})

    assert reply is not None
    assert "Profile 不存在" in reply or "创建失败" in reply


def test_bridge_on_job_created_callback():
    """测试 on_job_created 回调"""
    callback = Mock()
    config = BridgeConfig(gateway_url="http://localhost:9999")
    b = ChannelJobBridge(config=config, on_job_created=callback)
    b._http_sync = MagicMock()
    b._http_sync.post.return_value = _mock_response(201, {
        "job": {"id": "job-cb", "state": "pending"},
        "created": True,
    })

    b.on_message({"content": {"text": "run 测试"}, "sender_id": "u1"})

    callback.assert_called_once()
    call_args = callback.call_args
    assert call_args[0][0] == "job-cb"  # job_id


def test_bridge_string_message(bridge):
    """测试纯字符串消息"""
    bridge._http_sync.post.return_value = _mock_response(201, {
        "job": {"id": "job-str", "state": "pending"},
        "created": True,
    })

    reply = bridge.on_message("run 测试")

    assert reply is not None
    assert "任务已创建" in reply


# ─────────────────────────────────────────────────────────────────────────────
# Gateway Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_gateway_creates_bridge():
    """测试 Gateway create_app 自动创建 bridge"""
    from runtimes.gateway import create_app

    app = create_app()
    assert hasattr(app.state, "bridge")
    assert app.state.bridge is not None
    assert isinstance(app.state.bridge, ChannelJobBridge)


def test_setup_feishu_webhook_uses_bridge():
    """测试 setup_feishu_webhook 默认使用 bridge"""
    from runtimes.gateway import create_app
    import runtimes.gateway as gw

    app = create_app()

    # 验证 bridge 存在
    assert hasattr(app.state, "bridge")

    # Mock register_feishu_webhook 为空操作
    def mock_register(app, adapter, path="/webhooks/feishu"):
        pass

    # 直接调用 setup_feishu_webhook 并验证 on_message 设置
    from channels.feishu import FeishuAdapter, FeishuConfig

    with patch.object(gw, "_get_feishu_adapter") as mock_get:
        mock_get.return_value = (FeishuAdapter, FeishuConfig, mock_register)
        adapter = gw.setup_feishu_webhook(
            app=app,
            app_id="test_app_id",
            app_secret="test_secret",
        )

    # 验证 adapter.on_message 是 bridge 的方法
    assert adapter.on_message is not None
    assert adapter.on_message.__name__ == "on_message"


def test_setup_weixin_webhook_uses_bridge():
    """测试 setup_weixin_webhook 默认使用 bridge"""
    from runtimes.gateway import create_app, setup_weixin_webhook

    app = create_app()

    with patch("channels.weixin.register_weixin_webhook"):
        adapter = setup_weixin_webhook(
            app=app,
            app_id="test_app_id",
            app_secret="test_secret",
            token="test_token",
        )

    assert adapter.on_message is not None
    # 验证 adapter.on_message 是 bridge 的方法（函数对象相同）
    assert adapter.on_message.__name__ == "on_message"


def test_custom_on_message_overrides_bridge():
    """测试自定义 on_message 覆盖 bridge"""
    from runtimes.gateway import create_app
    import runtimes.gateway as gw

    app = create_app()
    custom_handler = Mock()

    # Mock register_feishu_webhook 为空操作
    def mock_register(app, adapter, path="/webhooks/feishu"):
        pass

    from channels.feishu import FeishuAdapter, FeishuConfig

    with patch.object(gw, "_get_feishu_adapter") as mock_get:
        mock_get.return_value = (FeishuAdapter, FeishuConfig, mock_register)
        adapter = gw.setup_feishu_webhook(
            app=app,
            app_id="test_app_id",
            app_secret="test_secret",
            on_message=custom_handler,
        )

    # 自定义 handler 覆盖了 bridge
    assert adapter.on_message is custom_handler


def test_create_bridge_factory():
    """测试 create_bridge 工厂函数"""
    bridge = create_bridge(
        gateway_url="http://localhost:8080",
        default_profile="pure_harness",
    )

    assert isinstance(bridge, ChannelJobBridge)
    assert bridge.config.gateway_url == "http://localhost:8080"
    assert bridge.config.default_profile == "pure_harness"
