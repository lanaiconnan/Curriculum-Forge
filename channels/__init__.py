"""
Channel Adapters

Feishu (飞书) and Weixin (微信) channel integrations.
Supports webhook-based message exchange for the MoonClaw Gateway.
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
]
