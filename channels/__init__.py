"""
Channel Adapters

Feishu (飞书) and Weixin (微信) channel integrations.
Supports webhook-based message exchange for the MoonClaw Gateway.

ChannelJobBridge: 桥接 Channel 消息与 Gateway Job 创建。
"""

from .feishu import (
    FeishuAdapter,
    FeishuConfig,
    FeishuError,
    register_feishu_webhook,
)

from .weixin import (
    WeixinAdapter,
    WeixinConfig,
    WeixinMessage,
    WeixinError,
    register_weixin_webhook,
)

from .bridge import (
    ChannelJobBridge,
    BridgeConfig,
    ParsedCommand,
    parse_command,
    create_bridge,
)

__all__ = [
    # Feishu
    "FeishuAdapter",
    "FeishuConfig",
    "FeishuError",
    "register_feishu_webhook",
    # WeChat
    "WeixinAdapter",
    "WeixinConfig",
    "WeixinMessage",
    "WeixinError",
    "register_weixin_webhook",
    # Bridge
    "ChannelJobBridge",
    "BridgeConfig",
    "ParsedCommand",
    "parse_command",
    "create_bridge",
]
