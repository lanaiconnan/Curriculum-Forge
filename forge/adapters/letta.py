"""Forge Adapter — Letta / MemGPT

通过 Letta REST API 进行 Harness 测试。

Letta API：
    POST /v1/agents/{id}/messages  - 发送消息
    GET  /v1/agents/{id}           - 获取 Agent 信息
    POST /v1/agents                - 创建 Agent
    GET  /v1/tools                 - 获取可用工具

Letta 工具名称（需要归一化）：
    send_message → memory_write
    retrieve    → memory_read
    core_memory → memory_read
    archival    → memory_search
    ...

配置：
    config = {
        "base_url": "http://localhost:8283",
        "agent_id": "agent-xxx",       # 或 "agent_name": "my-agent"
        "api_key": "letta-api-key",    # 环境变量 LETTA_API_KEY
    }

Usage:
    from forge.adapters import LettaAdapter
    adapter = LettaAdapter(config={"base_url": "http://localhost:8283"})
    result = adapter.submit("Remember that the config is at /etc/app.yaml")
"""

import os
import json
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


class LettaAdapter(HTTPAdapter):
    """
    Letta REST API Adapter。

    Letta 工具名称（需要归一化）：
      send_to_user      → response
      recall_memory     → memory_read
      edit_core_memory  → memory_write
      search_archival   → memory_search
      ...

    Letta 消息 API：
      POST /v1/agents/{id}/messages
      Body: {"messages": [{"role": "user", "content": "..."}]}
      Response: {"messages": [...], "tool_calls": [...], "agent_id": "..."}
    """

    name = "letta"
    description = "Letta REST API (MemGPT backend)"
    base_url = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
    timeout = 60.0

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        normalizer: Optional[ToolNameNormalizer] = None,
    ):
        super().__init__(config, normalizer)

        self.base_url = self.config.get(
            "base_url",
            os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
        )
        self.api_key = self.config.get(
            "api_key",
            os.environ.get("LETTA_API_KEY", "")
        )
        self.agent_id = self.config.get("agent_id", "")
        self.agent_name = self.config.get("agent_name", "")

        # Letta 工具名归一化规则
        letta_rules = {
            "memory_read":   ["recall_memory", "read_memory", "CoreMemory"],
            "memory_write":  ["edit_core_memory", "write_memory", "update_memory"],
            "memory_search": ["search_memory", "search_archival", "archival_search"],
            "send_message":  ["send_to_user", "message_user"],
            "file_read":     ["read_file", "ReadFile"],
            "file_write":    ["write_file", "WriteFile"],
        }
        if normalizer is None:
            self.normalizer = ToolNameNormalizer(custom_rules=letta_rules)

        self._message_history: List[Dict] = []
        self._connected = False

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _get_or_create_agent_id(self) -> Optional[str]:
        """获取或创建 Letta Agent"""
        if self.agent_id:
            return self.agent_id

        # 尝试通过名称查找或创建
        try:
            # 列出 agents
            resp = self._request("GET", "/v1/agents", params={"limit": 50})
            agents = resp.get("data", [])
            for agent in agents:
                if agent.get("name") == self.agent_name:
                    self.agent_id = agent["id"]
                    return self.agent_id

            # 创建新 agent
            if self.agent_name:
                create_resp = self._request("POST", "/v1/agents", json={
                    "name": self.agent_name,
                    "embedding_provider": "openai",
                    "llm_provider": "openai",
                })
                self.agent_id = create_resp.get("id", "")
                return self.agent_id
        except Exception as e:
            logger.warning(f"Letta agent lookup failed: {e}")

        return None

    def submit(
        self,
        prompt: str,
        extra_system: Optional[str] = None,
    ) -> AdapterResult:
        """
        通过 Letta API 发送消息。

        POST /v1/agents/{id}/messages
        """
        agent_id = self._get_or_create_agent_id()
        if not agent_id:
            return AdapterResult(
                final_response="",
                tool_calls=[],
                turns=0,
                success=False,
                error="Letta agent_id not configured and creation failed",
            )

        # 构建消息
        user_message = {"role": "user", "content": prompt}
        if extra_system:
            user_message["content"] = f"[System context]\n{extra_system}\n\n{user_message['content']}"

        messages = self._message_history + [user_message]

        try:
            resp = self._request(
                "POST",
                f"/v1/agents/{agent_id}/messages",
                json={"messages": messages},
            )

            self._connected = True

            # 解析 Letta 响应
            return self._parse_response(resp)

        except Exception as e:
            logger.error(f"Letta submit error: {e}")
            return AdapterResult(
                final_response="",
                tool_calls=[],
                turns=0,
                success=False,
                error=str(e),
            )

    def reset(self) -> None:
        """清空 Letta 消息历史"""
        self._message_history = []

    def health_check(self) -> bool:
        """检查 Letta API 是否可用"""
        try:
            resp = self._request("GET", "/v1/health")
            return resp.get("status") == "ok"
        except Exception:
            return False

    # ── 辅助 ─────────────────────────────────────────────────────────

    def _parse_response(self, resp: Dict) -> AdapterResult:
        """解析 Letta API 响应"""
        messages = resp.get("messages", [])
        tool_calls_raw = resp.get("tool_calls", [])

        # 从 messages 中提取工具调用
        tool_calls: List[ToolCall] = []
        final_response = ""

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "assistant":
                # Letta assistant 消息可能包含 tool_calls
                assistant_tool_calls = msg.get("tool_calls", [])
                for tc in assistant_tool_calls:
                    raw_name = tc.get("name", "")
                    tool_calls.append(ToolCall(
                        name=self.normalizer.normalize(raw_name),
                        input=tc.get("input", {}),
                        raw_name=raw_name,
                        call_id=tc.get("id", ""),
                    ))

                # 文本内容
                if isinstance(content, str):
                    final_response += content
                elif isinstance(content, list):
                    for block in content:
                        if block.get("type") == "text":
                            final_response += block.get("text", "")

            elif role == "tool":
                # 工具返回结果（不计入 tool_calls）
                pass

            elif role == "user":
                # 用户消息（跳过）
                pass

        # 直接从 tool_calls 字段读取（Letta 也有这个字段）
        for tc in tool_calls_raw:
            raw_name = tc.get("name", "")
            tool_calls.append(ToolCall(
                name=self.normalizer.normalize(raw_name),
                input=tc.get("arguments", tc.get("input", {})),
                raw_name=raw_name,
                call_id=tc.get("id", ""),
            ))

        return AdapterResult(
            final_response=final_response.strip(),
            tool_calls=tool_calls,
            turns=len(tool_calls) + (1 if final_response else 0),
            success=True,
            raw_response=resp,
            usage=resp.get("usage"),
        )
