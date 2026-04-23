"""Forge Adapters — 注册表与工厂函数

使用方式：
    from forge.adapters import (
        create_adapter,
        AdapterRegistry,
        ClaudeCodeAdapter,
        LettaAdapter,
        GooseAdapter,
        OpenClawAdapter,
        MockAdapter,
    )

    # 方式1：工厂函数（推荐）
    adapter = create_adapter("claude-code", config={...})

    # 方式2：直接实例化
    adapter = ClaudeCodeAdapter(config={...})

    # 方式3：注册自定义 Adapter
    registry = AdapterRegistry()
    registry.register("my-agent", MyAdapter)
"""

from typing import Dict, Type, Optional, Any, List
import logging
import os

from .base import AgentAdapter, MockAdapter

logger = logging.getLogger(__name__)


# ─── AdapterRegistry ───────────────────────────────────────────────────────────

class AdapterRegistry:
    """
    适配器注册表。

    所有内置和第三方 Adapter 都注册到这里。
    """

    def __init__(self):
        self._adapters: Dict[str, Type[AgentAdapter]] = {}

    def register(self, name: str, cls: Type[AgentAdapter]) -> 'AdapterRegistry':
        """注册一个 Adapter 类型"""
        self._adapters[name.lower()] = cls
        logger.debug(f"Registered adapter: {name} → {cls.__name__}")
        return self

    def get(self, name: str) -> Optional[Type[AgentAdapter]]:
        """获取 Adapter 类型"""
        return self._adapters.get(name.lower())

    def list(self) -> List[str]:
        """列出所有已注册的 Adapter"""
        return list(self._adapters.keys())

    def create(self, name: str, config: Optional[Dict[str, Any]] = None) -> AgentAdapter:
        """创建 Adapter 实例"""
        cls = self.get(name)
        if cls is None:
            raise ValueError(
                f"Unknown adapter: {name!r}. "
                f"Available: {', '.join(self.list())}"
            )
        return cls(config=config)


# ─── 全局注册表（预加载内置 Adapter）───────────────────────────────────────────

_registry = AdapterRegistry()


def _lazy_register():
    """延迟注册，避免循环导入"""
    # 延迟导入
    try:
        from .claude_code import ClaudeCodeAdapter
        _registry.register("claude-code", ClaudeCodeAdapter)
        _registry.register("claudecode", ClaudeCodeAdapter)
    except ImportError:
        pass

    try:
        from .letta import LettaAdapter
        _registry.register("letta", LettaAdapter)
        _registry.register("memgpt", LettaAdapter)
    except ImportError:
        pass

    try:
        from .goose import GooseAdapter
        _registry.register("goose", GooseAdapter)
    except ImportError:
        pass

    try:
        from .openclaw import OpenClawAdapter
        _registry.register("openclaw", OpenClawAdapter)
    except ImportError:
        pass

    # Mock 始终可用
    _registry.register("mock", MockAdapter)


# ─── 工厂函数 ─────────────────────────────────────────────────────────────────

def create_adapter(
    name: str,
    config: Optional[Dict[str, Any]] = None,
) -> AgentAdapter:
    """
    创建 Adapter 实例。

    Args:
        name: Adapter 名称（不区分大小写）
            - "claude-code" / "claudecode"
            - "letta" / "memgpt"
            - "goose"
            - "openclaw"
            - "mock"（默认，始终可用）
        config: 适配器配置

    Returns:
        AgentAdapter 实例

    Raises:
        ValueError: 未知 adapter 名称

    Example:
        adapter = create_adapter("mock", {"seed": 42})
        adapter = create_adapter("claude-code", {"cli_path": "/usr/local/bin/claude-code"})
    """
    _lazy_register()
    return _registry.create(name.lower(), config)


def register_adapter(name: str, cls: Type[AgentAdapter]) -> None:
    """注册自定义 Adapter 到全局注册表"""
    _lazy_register()
    _registry.register(name, cls)


def list_adapters() -> List[str]:
    """列出所有可用 Adapter"""
    _lazy_register()
    return _registry.list()


# ─── Adapter 包装器（HarnessRunner 用）────────────────────────────────────────

def wrap_for_harness(adapter: AgentAdapter):
    """
    将 AgentAdapter 包装成 HarnessRunner 兼容的格式。

    HarnessRunner.run_case() 期望：
        engine.submit(prompt, extra_system?) → QueryResult

    返回一个对象：
        submit(prompt, extra_system?) → QueryResult
    """
    from services.harness import QueryResult
    from services.query_engine import TokenUsage

    class HarnessWrapper:
        """把 AgentAdapter 适配为 HarnessRunner 期望的接口"""

        def __init__(self, adap: AgentAdapter):
            self._adapter = adap
            self._usage = TokenUsage()

        def reset(self):
            self._adapter.reset()
            self._usage = TokenUsage()

        def submit(self, prompt, extra_system=None):
            result = self._adapter.submit(prompt, extra_system)
            self._usage.input_tokens += len(prompt) // 4
            self._usage.output_tokens += len(result.final_response) // 4

            return QueryResult(
                final_response=result.final_response,
                turns=result.turns,
                tool_calls=[
                    {
                        "name": tc.name,
                        "input": tc.input,
                        "result": tc.result_preview,
                    }
                    for tc in result.tool_calls
                ],
                usage=self._usage,
                success=result.success,
                error=result.error,
            )

    return HarnessWrapper(adapter)
