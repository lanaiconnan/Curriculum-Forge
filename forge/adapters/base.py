"""Forge Adapters — 跨 Agent Harness 统一接口

支持多种 Agent 实现的统一 Harness 测试：
- OpenClaw        (HTTP/WebSocket Gateway)
- Claude Code     (CLI, MCP 协议)
- Letta/MemGPT    (REST API, SSE)
- Goose           (CLI, MCP/subprocess)
- Mock            (开发/测试用)

核心接口：
    from forge.adapters import AgentAdapter, AdapterRegistry, create_adapter

    adapter = create_adapter("claude-code", config={...})
    result = adapter.submit("Read config.json")
    print(result.tool_calls)   # [{"name": "read_file", "input": {...}}, ...]

关键设计原则：
1. Adapter 只需要实现 submit() 和 reset()
2. 所有 Adapter 返回统一的 ToolCall 结构
3. 工具名称自动归一化（不同 Agent 的同名工具映射到统一名）
4. 适配器支持懒加载和连接池
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from enum import Enum
import logging
import time
import os

if TYPE_CHECKING:
    from services.harness import HarnessCase

logger = logging.getLogger(__name__)


# ─── 统一数据类型 ──────────────────────────────────────────────────────────────

@dataclass
class ToolCall:
    """
    统一的工具调用结构。

    所有 Adapter 返回相同格式，无论底层 Agent 用什么协议。
    """
    name: str                     # 工具名称（归一化后）
    input: Dict[str, Any]         # 工具参数
    raw_name: str = ""            # 原始名称（归一化前）
    call_id: str = ""             # 调用 ID（用于追踪）
    result_preview: str = ""       # 执行结果预览（前100字符）


@dataclass
class AdapterResult:
    """
    Adapter.submit() 的返回值。

    与 services.query_engine.QueryResult 接口对齐。
    """
    final_response: str
    tool_calls: List[ToolCall]    # 所有工具调用
    turns: int                    # 总轮次数
    success: bool
    error: Optional[str] = None
    raw_response: Any = None       # Agent 原生响应（用于调试）
    usage: Optional[Dict[str, int]] = None  # token 使用量


# ─── ToolNameNormalizer ─────────────────────────────────────────────────────

class ToolNameNormalizer:
    """
    工具名称归一化器。

    不同 Agent 对同一工具有不同命名：
      OpenClaw: read_file, write_file
      Claude Code: Read, Write
      Letta:  read, write
      Goose:   ReadFile, WriteFile

    统一映射到一个规范名：
      read_file, write_file, search, git_*, ...
    """

    DEFAULT_RULES: Dict[str, List[str]] = {
        # 文件操作
        "read_file":  ["read", "Read", "read_file", "ReadFile", "ReadFileAction"],
        "write_file": ["write", "Write", "write_file", "WriteFile", "WriteFileAction", "Write_to_file"],
        "edit_file":  ["edit", "Edit", "edit_file", "EditFile", "EditFileAction"],
        "delete_file":["delete", "Delete", "delete_file", "DeleteFile"],
        # Git 操作
        "git_status": ["git_status", "git status", "GitStatus", "Git.status"],
        "git_commit": ["git_commit", "git commit", "GitCommit", "Git.commit"],
        "git_log":    ["git_log", "GitLog", "Git.log"],
        # 搜索
        "search":     ["search", "Search", "grep", "Grep", "find"],
        "web_search": ["web_search", "WebSearch", "websearch", "bing_search"],
        # Shell
        "shell":      ["shell", "Shell", "bash", "Bash", "run_command", "RunCommand"],
        "exec":       ["exec", "Exec", "execute", "Execute"],
        # 记忆/知识
        "memory_read":   ["memory_read", "MemoryRead", "recall", "Recall"],
        "memory_write":  ["memory_write", "MemoryWrite", "remember", "Remember"],
        # 浏览
        "browser_open":  ["browser_open", "BrowserOpen", "navigate", "Navigate", "open_url"],
        "browser_click": ["browser_click", "BrowserClick", "click", "Click"],
        "browser_type":  ["browser_type", "BrowserType", "type", "Type"],
    }

    def __init__(self, custom_rules: Optional[Dict[str, List[str]]] = None):
        """
        Args:
            custom_rules: 额外的归一化规则，会合并到默认规则
        """
        # 构建反向索引：原始名 → 规范名
        self._forward: Dict[str, str] = {}
        rules = {**self.DEFAULT_RULES}
        if custom_rules:
            for canonical, variants in custom_rules.items():
                rules.setdefault(canonical, []).extend(variants)
        for canonical, variants in rules.items():
            for v in variants:
                self._forward[v.lower()] = canonical

    def normalize(self, name: str) -> str:
        """
        将任意工具名归一化到规范名。

        Args:
            name: 原始工具名称

        Returns:
            规范名称（找不到时返回小写原名）
        """
        key = name.strip().lower()
        return self._forward.get(key, key)


# ─── AgentAdapter 协议 ────────────────────────────────────────────────────────

class AgentAdapter(ABC):
    """
    跨 Agent Harness 的统一接口协议。

    所有 Adapter 必须实现：
    - submit(prompt, extra_system?) → AdapterResult
    - reset() → None
    - health_check() → bool

    可选实现：
    - get_available_tools() → List[str]
    - get_system_prompt() → str

    使用方式：
        from forge.adapters import AgentAdapter

        class MyAdapter(AgentAdapter):
            name = "my-agent"
            description = "My custom agent"

            def submit(self, prompt, extra_system=None):
                ...  # 返回 AdapterResult
    """

    name: str = "abstract"
    description: str = ""
    supports_streaming: bool = False

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        normalizer: Optional[ToolNameNormalizer] = None,
    ):
        """
        Args:
            config: 适配器配置（如 API 密钥、端点等）
            normalizer: 工具名归一化器（默认用内置的）
        """
        self.config = config or {}
        self.normalizer = normalizer or ToolNameNormalizer()
        self._connected: bool = False

    # ── 必须实现 ──────────────────────────────────────────────────────────

    @abstractmethod
    def submit(
        self,
        prompt: str,
        extra_system: Optional[str] = None,
    ) -> AdapterResult:
        """
        向 Agent 发送提示并获取结果。

        Args:
            prompt: 用户提示
            extra_system: 额外的系统上下文

        Returns:
            AdapterResult：包含 final_response 和 tool_calls
        """
        ...

    @abstractmethod
    def reset(self) -> None:
        """重置 Agent 状态（开始新会话）"""
        ...

    # ── 健康检查 ──────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        """检查 Adapter 是否可用。子类可重写。"""
        return self._connected

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} '{self.name}' connected={self._connected}>"


# ─── 便捷基类 ────────────────────────────────────────────────────────────────

class HTTPAdapter(AgentAdapter):
    """
    HTTP/REST 协议 Adapter 的基类。

    提供：
    - session 管理
    - 重试逻辑
    - 请求/响应日志
    """

    base_url: str = ""
    timeout: float = 30.0
    max_retries: int = 3

    def __init__(self, config: Optional[Dict[str, Any]] = None,
                 normalizer: Optional[ToolNameNormalizer] = None):
        super().__init__(config, normalizer)
        self._session = None

    def _get_session(self):
        """获取或创建 HTTP session（子类实现）"""
        raise NotImplementedError

    def _request(
        self,
        method: str,
        path: str,
        json: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """发送 HTTP 请求（带重试）"""
        import urllib.request
        import urllib.error
        import json as _json

        url = f"{self.base_url}{path}"
        body = _json.dumps(json).encode() if json else None
        headers = {"Content-Type": "application/json"}

        for attempt in range(self.max_retries):
            try:
                req = urllib.request.Request(
                    url, data=body, headers=headers, method=method
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return _json.loads(resp.read())
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < self.max_retries - 1:
                    import time
                    time.sleep(2 ** attempt)
                    continue
                raise
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                import time
                time.sleep(1)

        return {}


class CLIAdapter(AgentAdapter):
    """
    CLI 协议 Adapter 的基类。

    通过 subprocess 与 Agent CLI 交互。
    """

    cmd: List[str] = []
    prompt_prefix: str = ""
    prompt_suffix: str = "\n"

    def __init__(self, config: Optional[Dict[str, Any]] = None,
                 normalizer: Optional[ToolNameNormalizer] = None):
        super().__init__(config, normalizer)
        self._process = None

    def _run_cli(self, prompt: str, timeout: float = 60.0) -> str:
        """执行 CLI 命令并返回输出"""
        import subprocess
        full_prompt = self.prompt_prefix + prompt + self.prompt_suffix
        try:
            result = subprocess.run(
                self.cmd,
                input=full_prompt.encode(),
                capture_output=True,
                timeout=timeout,
            )
            return result.stdout.decode(errors="replace")
        except subprocess.TimeoutExpired:
            return "[TIMEOUT]"
        except Exception as e:
            return f"[ERROR] {e}"


# ─── Mock Adapter（开发/测试用）──────────────────────────────────────────────

class MockAdapter(AgentAdapter):
    """
    Mock Adapter：用于开发测试，无需真实 API。

    特性：
    - 随机工具调用模拟
    - 可配置调用概率
    - deterministic 模式（固定 seed）
    - 真实工具执行（fallback 到本地）
    """

    name = "mock"
    description = "Mock adapter for development and testing"

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        normalizer: Optional[ToolNameNormalizer] = None,
        tool_call_probability: float = 0.7,
        seed: Optional[int] = None,
        fallback_to_real: bool = False,
    ):
        super().__init__(config, normalizer)
        self.probability = tool_call_probability
        self.fallback = fallback_to_real

        # 可配置的"已知"工具
        self.available_tools: List[str] = config.get(
            "available_tools",
            ["read_file", "write_file", "search", "shell"]
        ) if config else ["read_file", "write_file", "search", "shell"]

        # 预设的 case → 结果映射（用于精确测试）
        self._case_fixtures: Dict[str, AdapterResult] = {}

        import random
        if seed is not None:
            random.seed(seed)
        self._rng = random

    def submit(self, prompt: str, extra_system: Optional[str] = None) -> AdapterResult:
        # 精确匹配优先
        for case_id, result in self._case_fixtures.items():
            if case_id in prompt:
                return result

        # 随机决定是否调用工具
        if self._rng.random() < self.probability:
            # 选择一个工具
            tool_name = self._rng.choice(self.available_tools)
            tool_call = self._normalize_tool_call(
                name=tool_name,
                input={"prompt": prompt[:100], "generated": True},
            )
            tool_calls = [tool_call]
            response = f"[Mock] I called {tool_name} to handle this."
        else:
            tool_calls = []
            response = "[Mock] I completed this task without tools."

        return AdapterResult(
            final_response=response,
            tool_calls=tool_calls,
            turns=1,
            success=True,
        )

    def reset(self) -> None:
        pass

    def health_check(self) -> bool:
        return True

    def add_fixture(self, case_id: str, result: AdapterResult) -> None:
        """添加精确匹配 fixture"""
        self._case_fixtures[case_id] = result

    def _normalize_tool_call(self, name: str, input: Dict) -> ToolCall:
        """工具调用归一化"""
        raw = name
        canonical = self.normalizer.normalize(name)
        return ToolCall(
            name=canonical,
            input=input,
            raw_name=raw,
            call_id=f"mock_{int(time.time()*1000) % 100000}",
        )
