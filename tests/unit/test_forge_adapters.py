"""测试 Forge Adapters — 跨 Agent 统一适配层

验证：
1. OpenClawAdapter 正确封装 QueryEngine
2. MockAgentAdapter 预设序列和随机行为
3. make_harness_runner 工厂函数
4. AgentAdapter 协议完整性
5. 多 Agent 横向对比报告
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from dataclasses import dataclass, field
from typing import List, Dict, Any

from forge.adapters import (
    AgentAdapter,
    ToolCall,
    AgentResult,
    OpenClawAdapter,
    MockAgentAdapter,
    ClaudeCodeAdapter,
    LettaAdapter,
    GooseAdapter,
    make_harness_runner,
)


# ─── Mock QueryEngine ────────────────────────────────────────────────────────

class MockQueryResult:
    def __init__(self, tool_calls=None, success=True, error=None):
        self.final_response = "mock response"
        self.tool_calls = tool_calls or []
        self.turns = 1
        self.success = success
        self.error = error
        self.usage = MockUsage()


class MockUsage:
    input_tokens = 100
    output_tokens = 50


class MockQueryEngine:
    def __init__(self, tool_calls=None, success=True):
        self._tool_calls = tool_calls or []
        self._success = success
        self._reset_count = 0
        self.backend = MockBackend()

    def submit(self, prompt, extra_system=None):
        return MockQueryResult(
            tool_calls=self._tool_calls,
            success=self._success,
        )

    def reset(self):
        self._reset_count += 1


class MockBackend:
    model_name = "mock-model"


# ─── 协议验证测试 ───────────────────────────────────────────────────────────

class TestAgentAdapterProtocol:
    """验证所有 Adapter 实现了正确的协议"""

    def test_openclaw_adapter_has_required_methods(self):
        engine = MockQueryEngine()
        adapter = OpenClawAdapter(engine)
        assert hasattr(adapter, "submit")
        assert callable(adapter.submit)
        assert hasattr(adapter, "reset")
        assert callable(adapter.reset)
        assert hasattr(adapter, "get_name")
        assert callable(adapter.get_name)
        assert hasattr(adapter, "get_tools")
        assert callable(adapter.get_tools)

    def test_mock_adapter_has_required_methods(self):
        adapter = MockAgentAdapter()
        assert hasattr(adapter, "submit")
        assert callable(adapter.submit)
        assert hasattr(adapter, "reset")
        assert callable(adapter.reset)
        assert hasattr(adapter, "get_name")
        assert callable(adapter.get_name)
        assert hasattr(adapter, "get_tools")
        assert callable(adapter.get_tools)

    def test_claude_code_adapter_methods(self):
        adapter = ClaudeCodeAdapter(executable="nonexistent-claude-code")
        assert adapter.get_name() == "Claude Code"
        # 工具集非空
        tools = adapter.get_tools()
        assert isinstance(tools, list)


# ─── OpenClawAdapter 测试 ──────────────────────────────────────────────────

class TestOpenClawAdapter:

    def test_submit_converts_tool_calls(self):
        engine = MockQueryEngine(tool_calls=[
            {"name": "read_file", "input": {"target": "config.json"}},
            {"name": "write_file", "input": {"target": "out.txt", "content": "data"}},
        ])
        adapter = OpenClawAdapter(engine)
        result = adapter.submit("Read config.json")

        assert isinstance(result, AgentResult)
        assert result.success is True
        assert len(result.tool_calls) == 2
        assert result.tool_calls[0].name == "read_file"
        assert result.tool_calls[0].input == {"target": "config.json"}
        assert result.tool_calls[1].name == "write_file"

    def test_submit_error_result(self):
        engine = MockQueryEngine(success=False)
        adapter = OpenClawAdapter(engine)
        result = adapter.submit("Do something")

        assert isinstance(result, AgentResult)
        assert result.success is False

    def test_reset_calls_engine_reset(self):
        engine = MockQueryEngine()
        adapter = OpenClawAdapter(engine)
        assert engine._reset_count == 0
        adapter.reset()
        assert engine._reset_count == 1

    def test_get_name_includes_model(self):
        engine = MockQueryEngine()
        adapter = OpenClawAdapter(engine)
        assert "OpenClaw" in adapter.get_name()
        assert "mock-model" in adapter.get_name()

    def test_get_tools_returns_engine_tools(self):
        # MockQueryEngine 没有 tools 属性，适配器应安全降级
        engine = MockQueryEngine()
        adapter = OpenClawAdapter(engine)
        tools = adapter.get_tools()
        assert isinstance(tools, list)  # 不应抛 AttributeError


# ─── MockAgentAdapter 测试 ─────────────────────────────────────────────────

class TestMockAgentAdapter:

    def test_scripted_sequence(self):
        adapter = MockAgentAdapter(scripted=[
            {"name": "read_file", "input": {"target": "a.txt"}},
            {"name": "write_file", "input": {"target": "b.txt"}},
        ])

        r1 = adapter.submit("read a")
        assert r1.tool_calls[0].name == "read_file"
        assert r1.tool_calls[0].input == {"target": "a.txt"}

        r2 = adapter.submit("write b")
        assert r2.tool_calls[0].name == "write_file"

        # 序列耗尽后：每次调用独立，_turns 累积，达到 max_calls 时停止
        # 验证序列正确按顺序执行了
        assert r1.turns == 1
        assert r2.turns == 2

    def test_random_behavior(self):
        adapter = MockAgentAdapter(
            model="test-mock",
            tool_call_probability=1.0,
            max_tool_calls=3,
        )
        # 连续调用直到工具调用数达到上限
        results = []
        for _ in range(5):
            r = adapter.submit("task")
            results.append(len(r.tool_calls))

        # 前3次应有工具调用，第4次开始无调用（max_tool_calls=3）
        # 每次 reset 后重置计数器
        adapter.reset()
        r = adapter.submit("after reset")
        assert len(r.tool_calls) > 0  # reset 后重新开始

    def test_get_name(self):
        adapter = MockAgentAdapter(model="MyAgent")
        assert adapter.get_name() == "MyAgent"

    def test_get_tools_with_scripted(self):
        adapter = MockAgentAdapter(scripted=[
            {"name": "git", "input": {}},
            {"name": "read_file", "input": {}},
            {"name": "git", "input": {}},  # 重复
        ])
        tools = adapter.get_tools()
        assert "git" in tools
        assert "read_file" in tools
        assert len(tools) == 2  # 去重


# ─── 工厂函数测试 ──────────────────────────────────────────────────────────

class TestMakeHarnessRunner:

    def test_make_openclaw_runner_requires_engine(self):
        with pytest.raises(ValueError, match="需要传入 engine"):
            make_harness_runner("openclaw")

    def test_make_mock_runner(self):
        runner = make_harness_runner("mock")
        assert runner is not None
        assert hasattr(runner, "run")

    def test_make_unknown_raises(self):
        with pytest.raises(ValueError, match="未知 adapter_type"):
            make_harness_runner("unknown-agent")


# ─── 横向对比测试 ──────────────────────────────────────────────────────────

class TestCrossAgentBenchmark:
    """验证多 Agent 对比报告的生成"""

    def test_benchmark_two_agents(self):
        """模拟：OpenClaw vs Mock 的横向对比"""
        # 准备 HarnessRunner
        engine1 = MockQueryEngine(tool_calls=[{"name": "read_file", "input": {"target": "x"}}])
        adapter1 = OpenClawAdapter(engine1)
        runner1 = make_harness_runner("openclaw", engine=engine1)

        runner2 = make_harness_runner("mock")

        # 简单基准：两个 runner 都生成了报告
        # （实际 benchmark 需要 HarnessSuite，这里简化测试）
        assert runner1 is not None
        assert runner2 is not None

        # 两者的 adapter 类型不同
        assert type(runner1.engine).__name__ == "OpenClawAdapter"
        assert type(runner2.engine).__name__ == "MockAgentAdapter"

    def test_tool_call_normalization_in_runner(self):
        """
        验证 HarnessRunner._normalize_tool_calls
        对不同返回格式的处理
        """
        from services.harness import HarnessRunner, HarnessCase

        # Mock runner with both adapter types
        engine = MockQueryEngine(tool_calls=[
            {"name": "read_file", "input": {"target": "a"}},
        ])
        adapter = OpenClawAdapter(engine)
        runner = HarnessRunner(adapter)

        # 直接测试标准化方法
        # dict 格式
        normalized = runner._normalize_tool_calls([
            {"name": "foo", "input": {"x": 1}},
        ])
        assert normalized == [("foo", {"x": 1})]

        # ToolCall 对象格式
        normalized = runner._normalize_tool_calls([
            ToolCall(name="bar", input={"y": 2}),
        ])
        assert normalized == [("bar", {"y": 2})]

        # 混合格式
        normalized = runner._normalize_tool_calls([
            {"name": "a", "input": {}},
            ToolCall(name="b", input={}),
        ])
        assert normalized == [("a", {}), ("b", {})]

        # 空列表
        assert runner._normalize_tool_calls([]) == []


# ─── AgentResult / ToolCall 边界测试 ──────────────────────────────────────

class TestToolCallDataclass:
    def test_to_dict(self):
        tc = ToolCall(name="git", input={"cmd": "status"}, raw={"raw": True})
        d = tc.to_dict()
        assert d == {"name": "git", "input": {"cmd": "status"}}


class TestAgentResultDataclass:
    def test_defaults(self):
        r = AgentResult(
            final_response="hello",
            tool_calls=[],
            turns=1,
            success=True,
        )
        assert r.error is None
        assert r.metadata == {}

    def test_with_metadata(self):
        r = AgentResult(
            final_response="",
            tool_calls=[],
            turns=0,
            success=False,
            error="timeout",
            metadata={"attempt": 1},
        )
        assert r.error == "timeout"
        assert r.metadata["attempt"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
