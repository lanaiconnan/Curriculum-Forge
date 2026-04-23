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

__all__ = [
    "FeishuAdapter",
    "FeishuConfig",
    "FeishuError",
    "register_feishu_webhook",
]
