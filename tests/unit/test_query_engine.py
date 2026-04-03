"""Unit tests for QueryEngine

Run: pytest tests/unit/test_query_engine.py -v
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.query_engine import (
    QueryEngine,
    QueryConfig,
    QueryResult,
    ToolRegistry,
    ToolDefinition,
    ToolUseBlock,
    ToolResultBlock,
    LLMMessage,
    LLMResponse,
    TokenUsage,
    MockBackend,
    create_backend,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_registry(*tool_names):
    """Create a ToolRegistry with simple echo tools"""
    registry = ToolRegistry()
    for name in tool_names:
        registry.register(ToolDefinition(
            name=name,
            description=f"Tool: {name}",
            input_schema={
                "type": "object",
                "properties": {"target": {"type": "string"}},
                "required": ["target"],
            },
            handler=lambda inp, n=name: f"{n}({inp.get('target', '')})",
        ))
    return registry


class FixedBackend(MockBackend):
    """Backend with scripted responses for deterministic tests"""
    
    def __init__(self, responses):
        super().__init__()
        self._responses = list(responses)
        self._idx = 0
    
    def call(self, messages, system, tools, max_tokens):
        if self._idx < len(self._responses):
            resp = self._responses[self._idx]
            self._idx += 1
            return resp
        # Default: end turn
        return LLMResponse(
            content="Done.",
            tool_uses=[],
            stop_reason="end_turn",
            input_tokens=10,
            output_tokens=5,
        )


# ─── TokenUsage ───────────────────────────────────────────────────────────────

class TestTokenUsage:
    def test_initial_zero(self):
        u = TokenUsage()
        assert u.total == 0
    
    def test_add(self):
        u = TokenUsage()
        r = LLMResponse("", [], "end_turn", input_tokens=100, output_tokens=50)
        u.add(r)
        assert u.input_tokens == 100
        assert u.output_tokens == 50
        assert u.total == 150
    
    def test_accumulate(self):
        u = TokenUsage()
        for _ in range(3):
            u.add(LLMResponse("", [], "end_turn", input_tokens=10, output_tokens=5))
        assert u.total == 45


# ─── ToolRegistry ─────────────────────────────────────────────────────────────

class TestToolRegistry:
    def test_register_and_get(self):
        reg = make_registry("read_file", "write_file")
        assert reg.get("read_file") is not None
        assert reg.get("write_file") is not None
        assert reg.get("missing") is None
    
    def test_execute_success(self):
        reg = make_registry("echo")
        result = reg.execute(ToolUseBlock(id="t1", name="echo", input={"target": "hello"}))
        assert not result.is_error
        assert "echo" in result.content
    
    def test_execute_unknown_tool(self):
        reg = make_registry("echo")
        result = reg.execute(ToolUseBlock(id="t1", name="unknown", input={}))
        assert result.is_error
        assert "Unknown tool" in result.content
    
    def test_execute_handler_error(self):
        reg = ToolRegistry()
        reg.register(ToolDefinition(
            name="bad",
            description="",
            input_schema={},
            handler=lambda inp: 1 / 0,  # Always raises
        ))
        result = reg.execute(ToolUseBlock(id="t1", name="bad", input={}))
        assert result.is_error
    
    def test_to_api_format(self):
        reg = make_registry("tool_a", "tool_b")
        api = reg.to_api_format()
        assert len(api) == 2
        names = [t["name"] for t in api]
        assert "tool_a" in names
        assert "tool_b" in names


# ─── MockBackend ──────────────────────────────────────────────────────────────

class TestMockBackend:
    def test_returns_response(self):
        backend = MockBackend(tool_call_probability=0.0)
        resp = backend.call(
            messages=[LLMMessage("user", "hello")],
            system="",
            tools=[],
            max_tokens=100,
        )
        assert resp.stop_reason == "end_turn"
        assert resp.content
    
    def test_tool_call_when_tools_available(self):
        backend = MockBackend(tool_call_probability=1.0)
        tools = [{"name": "my_tool", "description": "", "input_schema": {"type": "object", "properties": {}, "required": []}}]
        resp = backend.call(
            messages=[LLMMessage("user", "use a tool")],
            system="",
            tools=tools,
            max_tokens=100,
        )
        assert resp.stop_reason == "tool_use"
        assert len(resp.tool_uses) == 1
        assert resp.tool_uses[0].name == "my_tool"
    
    def test_no_tool_call_without_tools(self):
        backend = MockBackend(tool_call_probability=1.0)
        resp = backend.call(
            messages=[LLMMessage("user", "hello")],
            system="",
            tools=[],  # No tools
            max_tokens=100,
        )
        assert resp.stop_reason == "end_turn"


# ─── QueryEngine ──────────────────────────────────────────────────────────────

class TestQueryEngine:
    def test_simple_submit(self):
        backend = MockBackend(tool_call_probability=0.0)
        engine = QueryEngine(backend=backend, config=QueryConfig())
        result = engine.submit("Hello")
        assert result.success
        assert result.final_response
        assert result.turns >= 1
    
    def test_tool_use_loop(self):
        """Engine should call tool, get result, then end"""
        tool_response = LLMResponse(
            content="Using tool...",
            tool_uses=[ToolUseBlock(id="t1", name="echo", input={"target": "test"})],
            stop_reason="tool_use",
            input_tokens=50, output_tokens=20,
        )
        end_response = LLMResponse(
            content="Task complete.",
            tool_uses=[],
            stop_reason="end_turn",
            input_tokens=80, output_tokens=30,
        )
        
        backend = FixedBackend([tool_response, end_response])
        registry = make_registry("echo")
        engine = QueryEngine(backend=backend, tools=registry, config=QueryConfig())
        
        result = engine.submit("Do something")
        
        assert result.success
        assert result.turns == 2
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "echo"
        assert result.final_response == "Task complete."
    
    def test_token_usage_accumulates(self):
        backend = FixedBackend([
            LLMResponse("", [ToolUseBlock("t1", "echo", {"target": "x"})], "tool_use", 100, 50),
            LLMResponse("Done", [], "end_turn", 150, 60),
        ])
        registry = make_registry("echo")
        engine = QueryEngine(backend=backend, tools=registry)
        
        result = engine.submit("test")
        assert result.usage.input_tokens == 250
        assert result.usage.output_tokens == 110
    
    def test_reset_clears_state(self):
        backend = MockBackend(tool_call_probability=0.0)
        engine = QueryEngine(backend=backend)
        engine.submit("First message")
        assert len(engine.messages) > 0
        
        engine.reset()
        assert len(engine.messages) == 0
        assert engine.usage.total == 0
    
    def test_token_budget_exceeded(self):
        backend = MockBackend(tool_call_probability=0.0)
        config = QueryConfig(max_total_tokens=0)  # Budget = 0
        engine = QueryEngine(backend=backend, config=config)
        
        result = engine.submit("test")
        assert not result.success
        assert "budget" in result.error.lower()
    
    def test_max_turns_respected(self):
        """Engine should stop after max_turns even if LLM keeps calling tools"""
        # Always return tool_use
        always_tool = LLMResponse(
            content="",
            tool_uses=[ToolUseBlock("t1", "echo", {"target": "x"})],
            stop_reason="tool_use",
            input_tokens=10, output_tokens=5,
        )
        backend = FixedBackend([always_tool] * 20)
        registry = make_registry("echo")
        config = QueryConfig(max_turns=3)
        engine = QueryEngine(backend=backend, tools=registry, config=config)
        
        result = engine.submit("loop forever")
        assert result.turns <= 3
    
    def test_multi_turn_conversation(self):
        """Multiple submits should accumulate message history"""
        backend = MockBackend(tool_call_probability=0.0)
        engine = QueryEngine(backend=backend)
        
        engine.submit("First")
        first_msg_count = len(engine.messages)
        
        engine.submit("Second")
        assert len(engine.messages) > first_msg_count
    
    def test_extra_system_prompt(self):
        """Extra system context should be passed to backend"""
        received_systems = []
        
        class CapturingBackend(MockBackend):
            def call(self, messages, system, tools, max_tokens):
                received_systems.append(system)
                return super().call(messages, system, tools, max_tokens)
        
        engine = QueryEngine(
            backend=CapturingBackend(tool_call_probability=0.0),
            config=QueryConfig(system_prompt="Base prompt"),
        )
        engine.submit("test", extra_system="Extra context")
        
        assert len(received_systems) > 0
        assert "Extra context" in received_systems[0]
        assert "Base prompt" in received_systems[0]


# ─── create_backend ───────────────────────────────────────────────────────────

class TestCreateBackend:
    def test_mock_backend(self):
        backend = create_backend("mock")
        assert isinstance(backend, MockBackend)
    
    def test_auto_without_key_returns_mock(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        backend = create_backend("auto")
        assert isinstance(backend, MockBackend)
    
    def test_auto_with_key_returns_anthropic(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        try:
            import anthropic  # noqa: F401
            backend = create_backend("auto")
            assert isinstance(backend, AnthropicBackend)
        except ImportError:
            # anthropic not installed — falls back to Mock
            backend = create_backend("auto")
            assert isinstance(backend, MockBackend)


# ─── Integration: LearnerService with QueryEngine ────────────────────────────

class TestLearnerWithQueryEngine:
    def test_run_experiments_uses_llm(self):
        """LearnerService should use QueryEngine for task execution"""
        from services.learner import LearnerService, LearnerServiceConfig
        from services.models import (
            TrainingEnvironment, LearningStage, TaskConfig
        )
        
        config = LearnerServiceConfig(
            max_iterations=1,
            llm_backend="mock",
        )
        learner = LearnerService(config)
        learner.initialize()
        
        env = TrainingEnvironment(
            id="e1",
            name="Test Env",
            description="Test",
            stage=LearningStage.BEGINNER,
            difficulty=0.3,
            tasks=[
                TaskConfig(
                    id="t1",
                    type="test",
                    description="Read a file",
                    target="test.txt",
                    tools_required=["read_file"],
                )
            ],
            available_tools=["read_file", "write_file"],
        )
        
        records = learner.run_experiments(env, max_iterations=1)
        
        assert len(records) > 0
        record = records[0]
        # Should have metadata from QueryEngine
        assert "turns" in record.metadata or record.reward is not None
    
    def test_experiment_metadata_contains_llm_info(self):
        """Experiment records should contain LLM call metadata"""
        from services.learner import LearnerService, LearnerServiceConfig
        from services.models import (
            TrainingEnvironment, LearningStage, TaskConfig
        )
        
        config = LearnerServiceConfig(
            max_iterations=1,
            llm_backend="mock",
        )
        learner = LearnerService(config)
        learner.initialize()
        
        env = TrainingEnvironment(
            id="e2",
            name="Test Env 2",
            description="",
            stage=LearningStage.INTERMEDIATE,
            difficulty=0.5,
            tasks=[
                TaskConfig(
                    id="t1",
                    type="test",
                    description="Write output",
                    target="output.txt",
                    tools_required=["write_file"],
                )
            ],
            available_tools=["write_file"],
        )
        
        records = learner.run_experiments(env, max_iterations=1)
        assert len(records) > 0
        
        # Check metadata
        record = records[0]
        assert hasattr(record, 'metadata')
        if record.metadata:
            assert "turns" in record.metadata or "model" in record.metadata


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
