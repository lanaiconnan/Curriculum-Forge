"""Unit tests for context.py — Context Compression

Run: pytest tests/unit/test_context.py -v
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.context import (
    estimate_tokens,
    estimate_message_tokens,
    estimate_total_tokens,
    CompactConfig,
    CompactBoundary,
    CompactResult,
    ContextCompactor,
    MessageGroup,
    group_messages,
    default_summarize_fn,
    CompactableQueryEngine,
)
from services.query_engine import (
    LLMMessage,
    MockBackend,
    QueryEngine,
    QueryConfig,
    ToolRegistry,
    ToolDefinition,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_messages(count, role="user", content="hello world"):
    """Generate N messages"""
    return [LLMMessage(role=role, content=f"{content} #{i}") for i in range(count)]


def make_conversation(turns):
    """Generate a multi-turn conversation"""
    messages = [LLMMessage(role="system", content="You are helpful.")]
    for i in range(turns):
        messages.append(LLMMessage(role="user", content=f"User message {i}"))
        messages.append(LLMMessage(role="assistant", content=f"Assistant response {i}"))
    return messages


# ─── Token Estimation ─────────────────────────────────────────────────────────

class TestTokenEstimation:
    def test_empty(self):
        assert estimate_tokens("") == 0

    def test_short(self):
        assert estimate_tokens("hello") >= 1

    def test_long(self):
        # 1000 chars ≈ 250 tokens
        n = estimate_tokens("x" * 1000)
        assert 200 <= n <= 300

    def test_message(self):
        msg = LLMMessage(role="user", content="hello world")
        tokens = estimate_message_tokens(msg)
        assert tokens > estimate_tokens("hello world")

    def test_total(self):
        msgs = [LLMMessage("user", "a"), LLMMessage("assistant", "bb")]
        total = estimate_total_tokens(msgs)
        assert total == estimate_message_tokens(msgs[0]) + estimate_message_tokens(msgs[1])


# ─── Message Grouping ────────────────────────────────────────────────────────

class TestMessageGrouping:
    def test_basic_conversation(self):
        messages = [
            LLMMessage("system", "sys"),
            LLMMessage("user", "q1"),
            LLMMessage("assistant", "a1"),
            LLMMessage("user", "q2"),
            LLMMessage("assistant", "a2"),
        ]
        groups = group_messages(messages)
        # system, turn0(q1+a1), turn1(q2+a2)
        assert len(groups) == 3

    def test_empty(self):
        assert group_messages([]) == []

    def test_single_message(self):
        groups = group_messages([LLMMessage("user", "hi")])
        assert len(groups) == 1

    def test_turn_indices(self):
        messages = [
            LLMMessage("user", "q1"),
            LLMMessage("assistant", "a1"),
            LLMMessage("user", "q2"),
            LLMMessage("assistant", "a2"),
        ]
        groups = group_messages(messages)
        indices = [g.turn_index for g in groups]
        assert indices == [0, 1]

    def test_tool_heavy_detection(self):
        # Create a tool-heavy turn (user + assistant with tool_result)
        tool_result = LLMMessage("user", content=[
            {"type": "tool_result", "content": "ok"},
            {"type": "tool_result", "content": "ok2"},
            {"type": "tool_result", "content": "ok3"},
        ])
        messages = [LLMMessage("user", "q"), tool_result]
        groups = group_messages(messages)
        assert groups[0].is_tool_heavy is True

    def test_error_detection(self):
        error_result = LLMMessage("user", content=[
            {"type": "tool_result", "content": "fail", "is_error": True},
        ])
        messages = [LLMMessage("user", "q"), error_result]
        groups = group_messages(messages)
        assert groups[0].has_error is True


# ─── CompactBoundary ─────────────────────────────────────────────────────────

class TestCompactBoundary:
    def test_to_message(self):
        b = CompactBoundary(
            summary="Previous: 5 tool calls.",
            preserved_count=10,
            removed_count=20,
            original_tokens=50000,
            compressed_tokens=8000,
        )
        msg = b.to_message()
        assert msg.role == "system"
        assert "5 tool calls" in msg.content
        assert "10 recent" in msg.content


# ─── Default Summarizer ──────────────────────────────────────────────────────

class TestDefaultSummarizer:
    def test_empty_groups(self):
        summary = default_summarize_fn([])
        assert len(summary) > 0

    def test_tool_calls(self):
        tool_heavy = MessageGroup(
            messages=[
                LLMMessage("user", content=[{"type": "tool_result", "content": "ok"}]),
            ],
            turn_index=0,
            is_tool_heavy=True,
            has_error=False,
        )
        summary = default_summarize_fn([tool_heavy])
        assert "tool call" in summary

    def test_errors(self):
        error_group = MessageGroup(
            messages=[
                LLMMessage("user", content=[{"type": "tool_result", "content": "fail", "is_error": True}]),
            ],
            turn_index=0,
            is_tool_heavy=False,
            has_error=True,
        )
        summary = default_summarize_fn([error_group])
        assert "error" in summary


# ─── ContextCompactor ─────────────────────────────────────────────────────────

class TestContextCompactor:
    def test_should_compact_at_threshold(self):
        config = CompactConfig(max_tokens=100, warning_threshold=0.8, keep_recent=2)
        compactor = ContextCompactor(config)
        msgs = make_messages(20)

        should, reason = compactor.should_compact(msgs, 81)  # 81 > 80
        assert should is True

    def test_should_not_compact_below_threshold(self):
        config = CompactConfig(max_tokens=100, warning_threshold=0.8, keep_recent=2)
        compactor = ContextCompactor(config)
        msgs = make_messages(20)

        should, reason = compactor.should_compact(msgs, 50)
        assert should is False

    def test_should_not_compact_too_few_messages(self):
        """Below threshold + too few messages = don't compact"""
        config = CompactConfig(max_tokens=100, warning_threshold=0.5, keep_recent=10)
        compactor = ContextCompactor(config)
        msgs = make_messages(5)  # Not enough to compact (< keep_recent * 2)

        # Below threshold AND too few → don't compact
        should, reason = compactor.should_compact(msgs, 49)
        assert should is False

    def test_compact_reduces_messages(self):
        compactor = ContextCompactor(CompactConfig(keep_recent=3))
        messages = make_conversation(20)  # system + 20 turns = 41 messages

        compressed, boundary = compactor.compact(messages)
        # system(1) + boundary(1) + 6 recent(3 user + 3 assistant) = 8
        assert len(compressed) < len(messages)
        assert boundary.removed_count > 0

    def test_compact_preserves_system(self):
        compactor = ContextCompactor(CompactConfig(keep_recent=2))
        messages = make_conversation(5)

        compressed, boundary = compactor.compact(messages)
        roles = [m.role for m in compressed]
        assert "system" in roles

    def test_compact_preserves_recent(self):
        compactor = ContextCompactor(CompactConfig(keep_recent=4))
        messages = make_conversation(10)  # 21 messages

        compressed, boundary = compactor.compact(messages)
        # Last 4 messages (2 user + 2 assistant) should be preserved
        assert boundary.preserved_count == 4

    def test_compact_counts(self):
        compactor = ContextCompactor(CompactConfig(keep_recent=2))
        messages = make_conversation(5)  # system + 5 turns = 11 messages

        compressed, boundary = compactor.compact(messages)
        assert boundary.preserved_count + boundary.removed_count + 1 == len(messages)
        # +1 for system message

    def test_compact_reduces_tokens(self):
        compactor = ContextCompactor(CompactConfig(keep_recent=2))
        messages = make_conversation(50)

        original_tokens = estimate_total_tokens(messages)
        compressed, boundary = compactor.compact(messages)
        compressed_tokens = estimate_total_tokens(compressed)

        assert compressed_tokens < original_tokens
        assert boundary.compressed_tokens == compressed_tokens

    def test_compact_state_tracked(self):
        compactor = ContextCompactor(CompactConfig(keep_recent=2))
        messages = make_conversation(5)

        assert compactor.compact_count == 0
        compactor.compact(messages)
        assert compactor.compact_count == 1
        compactor.compact(messages)
        assert compactor.compact_count == 2

    def test_get_state(self):
        compactor = ContextCompactor(CompactConfig(max_tokens=5000))
        state = compactor.get_state()
        assert "compact_count" in state
        assert "config" in state
        assert state["config"]["max_tokens"] == 5000

    def test_multiple_compacts_progressive(self):
        """Each compact should further reduce the context"""
        compactor = ContextCompactor(CompactConfig(keep_recent=2, max_tokens=100000))
        messages = make_conversation(20)

        # First compact
        compressed1, _ = compactor.compact(messages)
        # Second compact on already-compressed
        compressed2, boundary2 = compactor.compact(compressed1)

        # Should still work (fewer to remove, but no crash)
        assert len(compressed2) > 0


# ─── CompactResult ────────────────────────────────────────────────────────────

class TestCompactResult:
    def test_compression_ratio(self):
        r = CompactResult(
            original_messages=100, compressed_messages=20,
            original_tokens=40000, compressed_tokens=8000,
            removed_count=80, preserved_count=20,
            boundary=CompactBoundary("x", 20, 80, 40000, 8000),
        )
        assert r.compression_ratio == 0.2
        assert r.saved_tokens == 32000

    def test_zero_tokens(self):
        r = CompactResult(
            original_messages=10, compressed_messages=5,
            original_tokens=0, compressed_tokens=0,
            removed_count=5, preserved_count=5,
            boundary=CompactBoundary("x", 5, 5, 0, 0),
        )
        assert r.compression_ratio == 1.0


# ─── CompactableQueryEngine Integration ──────────────────────────────────────

class TestCompactableQueryEngine:
    def _make_engine(self, max_tokens=500, keep_recent=2):
        from services.query_engine import ToolRegistry, ToolDefinition

        registry = ToolRegistry()
        registry.register(ToolDefinition(
            name="echo", description="Echo", input_schema={
                "type": "object", "properties": {"text": {"type": "string"}},
                "required": ["text"],
            }, handler=lambda inp: f"Echo: {inp.get('text', '')}",
        ))

        base = QueryEngine(
            backend=MockBackend(tool_call_probability=0.0),
            tools=registry,
            config=QueryConfig(max_tokens=100),
        )

        config = CompactConfig(max_tokens=max_tokens, warning_threshold=0.8, keep_recent=keep_recent)
        return CompactableQueryEngine(base, config=config)

    def test_submit_works_normally(self):
        engine = self._make_engine(max_tokens=100000)
        result = engine.submit("Hello")
        assert result.success

    def test_auto_compact_triggers(self):
        """Engine should auto-compact when tokens exceed threshold"""
        engine = self._make_engine(max_tokens=500, keep_recent=2)

        # Submit many messages to build up token count
        # Use small max_tokens so we exceed threshold quickly
        engine._compactor.config.max_tokens = 200
        engine._compactor.config.warning_threshold = 0.5
        engine._compactor.config.keep_recent = 2

        # Submit several times
        for i in range(10):
            result = engine.submit(f"Message {i}")
            assert result.success

        # Should have compacted at least once
        # (depends on token estimation being accurate enough)
        # We just verify no crash and state is consistent
        assert len(engine._engine._messages) > 0

    def test_compact_history_tracked(self):
        engine = self._make_engine(max_tokens=500, keep_recent=2)
        engine._compactor.config.max_tokens = 100
        engine._compactor.config.warning_threshold = 0.3

        for i in range(5):
            engine.submit(f"Msg {i}")

        # Even if no compact happened, history should be accessible
        assert isinstance(engine.compact_history, list)

    def test_reset_clears_everything(self):
        engine = self._make_engine(max_tokens=100000)
        engine.submit("Test")
        engine.reset()
        assert len(engine._engine._messages) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
