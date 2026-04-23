"""Forge Adapter — OpenClaw

通过 OpenClaw Gateway HTTP API 与 OpenClaw Agent 交互。

API 端点（Gateway）：
    POST /api/agent/submit   - 提交消息
    GET  /api/agent/reset    - 重置会话
    GET  /api/health         - 健康检查

配置：
    config = {
        "gateway_url": "http://localhost:18789",  # 默认
        "session_id": "optional-session-id",
        "api_key": "optional-api-key",
        "model": "claude-sonnet",
        "timeout": 60,
    }

Usage:
    from forge.adapters import OpenClawAdapter
    adapter = OpenClawAdapter(config={"gateway_url": "http://localhost:18789"})
    result = adapter.submit("Read the file config.json")
    print(result.tool_calls)
"""

import os
import json
import time
import logging
from typing import Any, Dict, List, Optional

from .base import (
    AgentAdapter,
    HTTPAdapter,
    AdapterResult,
    ToolCall,
    ToolNameNormalizer,
)

logger = logging.getLogger(__name__)


class OpenClawAdapter(HTTPAdapter):
    """
    OpenClaw Gateway HTTP Adapter。

    OpenClaw Gateway 提供：
    - HTTP REST API（/api/agent/submit）
    - 会话管理（session_id）
    - 工具调用流（tool_use → tool_result）

    已知 OpenClaw Gateway 工具名称（需要归一化）：
        read_file → read_file
        write_file → write_file
        BrowserAutomation → browser_*
        ...
    """

    name = "openclaw"
    description = "OpenClaw Gateway HTTP API"
    base_url = os.environ.get("OPENCLAW_GATEWAY_URL", "http://localhost:18789")
    timeout = 60.0

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        normalizer: Optional[ToolNameNormalizer] = None,
    ):
        super().__init__(config, normalizer)

        self.gateway_url = self.config.get(
            "gateway_url",
            os.environ.get("OPENCLAW_GATEWAY_URL", "http://localhost:18789")
        )
        self.session_id = self.config.get("session_id", "")
        self.api_key = self.config.get(
            "api_key",
            os.environ.get("OPENCLAW_API_KEY", "")
        )
        self.model = self.config.get("model", "claude-sonnet")
        self.timeout = self.config.get("timeout", 60)

        # 自定义工具名归一化规则（OpenClaw 特定）
        openclaw_rules = {
            "read_file": ["read_file", "Read", "ReadFile", "fs_read"],
            "write_file": ["write_file", "Write", "WriteFile", "fs_write"],
            "browser_open": ["open_url", "navigate", "browser_navigate"],
            "browser_click": ["click", "browser_click"],
        }
        if normalizer is None:
            self.normalizer = ToolNameNormalizer(custom_rules=openclaw_rules)

        self._session_id: Optional[str] = self.session_id or None
        self._connected = False

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    # ── 核心 API ─────────────────────────────────────────────────────────

    def submit(
        self,
        prompt: str,
        extra_system: Optional[str] = None,
    ) -> AdapterResult:
        """
        通过 Gateway API 提交消息。

        OpenClaw Gateway API:
            POST /api/agent/submit
            Body: {
                "message": prompt,
                "session_id": "...",
                "model": "claude-sonnet",
                "system": "optional extra system prompt",
                "tools": [...],
            }
            Response: {
                "content": "...",
                "tool_calls": [{"name": "...", "input": {...}}],
                "session_id": "...",
            }
        """
        if not self.gateway_url:
            return AdapterResult(
                final_response="",
                tool_calls=[],
                turns=0,
                success=False,
                error="OPENCLAW_GATEWAY_URL not configured",
            )

        url = f"{self.gateway_url}/api/agent/submit"
        payload: Dict[str, Any] = {
            "message": prompt,
            "model": self.model,
        }
        if self._session_id:
            payload["session_id"] = self._session_id
        if extra_system:
            payload["system"] = extra_system

        try:
            import urllib.request
            import urllib.error

            body = json.dumps(payload).encode()
            req = urllib.request.Request(
                url,
                data=body,
                headers=self._headers(),
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read())

            self._session_id = data.get("session_id", self._session_id)
            self._connected = True

            # 解析工具调用
            raw_tool_calls = data.get("tool_calls", [])
            tool_calls = [self._parse_tool_call(tc) for tc in raw_tool_calls]

            return AdapterResult(
                final_response=data.get("content", data.get("text", "")),
                tool_calls=tool_calls,
                turns=data.get("turns", 1),
                success=True,
                raw_response=data,
                usage=data.get("usage"),
            )

        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            return AdapterResult(
                final_response="",
                tool_calls=[],
                turns=0,
                success=False,
                error=f"HTTP {e.code}: {body[:200]}",
            )
        except Exception as e:
            logger.error(f"OpenClaw submit error: {e}")
            return AdapterResult(
                final_response="",
                tool_calls=[],
                turns=0,
                success=False,
                error=str(e),
            )

    def reset(self) -> None:
        """重置 OpenClaw 会话"""
        if not self.gateway_url or not self._session_id:
            return

        try:
            import urllib.request

            url = f"{self.gateway_url}/api/agent/reset"
            payload = {"session_id": self._session_id}
            body = json.dumps(payload).encode()
            req = urllib.request.Request(
                url, data=body,
                headers=self._headers(),
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10)
            logger.info(f"OpenClaw session reset: {self._session_id}")
        except Exception as e:
            logger.warning(f"OpenClaw reset error: {e}")

    def health_check(self) -> bool:
        """检查 Gateway 是否可用"""
        if not self.gateway_url:
            return False
        try:
            import urllib.request
            url = f"{self.gateway_url}/api/health"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    # ── 辅助 ─────────────────────────────────────────────────────────────

    def _parse_tool_call(self, raw: Dict[str, Any]) -> ToolCall:
        """解析 Gateway 返回的工具调用"""
        raw_name = raw.get("name", "")
        return ToolCall(
            name=self.normalizer.normalize(raw_name),
            input=raw.get("input", {}),
            raw_name=raw_name,
            call_id=raw.get("id", ""),
            result_preview=raw.get("result", "")[:100] if isinstance(raw.get("result"), str) else "",
        )

    def get_session_id(self) -> Optional[str]:
        return self._session_id
