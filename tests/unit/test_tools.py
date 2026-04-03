"""Unit tests for tools.py — Permission, Formatting, Stats

Run: pytest tests/unit/test_tools.py -v
"""

import pytest
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.tools import (
    RateLimit,
    ToolPermission,
    PermissionBehavior,
    ToolResultFormatter,
    ToolStats,
    ToolCallRecord,
    StatsTracker,
    ManagedToolRegistry,
)
from services.query_engine import (
    ToolDefinition,
    ToolUseBlock,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def echo_tool(name="echo"):
    return ToolDefinition(
        name=name,
        description=f"Echo tool: {name}",
        input_schema={
            "type": "object",
            "properties": {"target": {"type": "string"}},
            "required": ["target"],
        },
        handler=lambda inp: f"{name}({inp.get('target', '')})",
    )


def error_tool(name="bad"):
    return ToolDefinition(
        name=name,
        description="Always errors",
        input_schema={},
        handler=lambda inp: 1 / 0,
    )


def make_registry(*tool_names, permission=None, formatter=None):
    reg = ManagedToolRegistry(permission=permission, formatter=formatter)
    for name in tool_names:
        reg.register(echo_tool(name))
    return reg


# ─── RateLimit ────────────────────────────────────────────────────────────────

class TestRateLimit:
    def test_allows_within_limit(self):
        rl = RateLimit(max_calls=3, window_seconds=60)
        assert rl.check() is True
        assert rl.check() is True
        assert rl.check() is True

    def test_blocks_over_limit(self):
        rl = RateLimit(max_calls=2, window_seconds=60)
        rl.record()
        rl.record()
        assert rl.check() is False

    def test_remaining(self):
        rl = RateLimit(max_calls=5, window_seconds=60)
        rl.record()
        rl.record()
        assert rl.remaining == 3

    def test_window_expiry(self):
        rl = RateLimit(max_calls=1, window_seconds=0.05)
        rl.record()
        assert rl.check() is False
        time.sleep(0.1)
        assert rl.check() is True  # Window expired

    def test_current_count(self):
        rl = RateLimit(max_calls=10, window_seconds=60)
        rl.record()
        rl.record()
        assert rl.current_count == 2


# ─── ToolPermission ───────────────────────────────────────────────────────────

class TestToolPermission:
    def test_allow_all(self):
        perm = ToolPermission.allow_all()
        assert perm.check("any_tool").allowed is True

    def test_allow_only(self):
        perm = ToolPermission.allow_only(["read_file", "search"])
        assert perm.check("read_file").allowed is True
        assert perm.check("write_file").allowed is False
        assert perm.check("search").allowed is True

    def test_deny_only(self):
        perm = ToolPermission.deny_only(["dangerous_tool"])
        assert perm.check("safe_tool").allowed is True
        assert perm.check("dangerous_tool").allowed is False

    def test_deny_overrides_allow(self):
        perm = ToolPermission(
            allow_list=["read_file", "bad_tool"],
            deny_list=["bad_tool"],
        )
        assert perm.check("read_file").allowed is True
        assert perm.check("bad_tool").allowed is False

    def test_rate_limit_blocks(self):
        perm = ToolPermission(
            rate_limits={"read_file": RateLimit(max_calls=1, window_seconds=60)}
        )
        perm.record_call("read_file")  # Use up the 1 allowed call
        result = perm.check("read_file")
        assert result.allowed is False
        assert "rate limited" in result.reason.lower()

    def test_rate_limit_allows_before_limit(self):
        perm = ToolPermission(
            rate_limits={"read_file": RateLimit(max_calls=5, window_seconds=60)}
        )
        assert perm.check("read_file").allowed is True

    def test_deny_reason_provided(self):
        perm = ToolPermission.deny_only(["bad"])
        result = perm.check("bad")
        assert result.reason is not None
        assert "deny list" in result.reason.lower()

    def test_allow_list_reason_provided(self):
        perm = ToolPermission.allow_only(["good"])
        result = perm.check("other")
        assert result.reason is not None
        assert "allow list" in result.reason.lower()


# ─── ToolResultFormatter ──────────────────────────────────────────────────────

class TestToolResultFormatter:
    def test_short_result_unchanged(self):
        fmt = ToolResultFormatter(max_length=100)
        result = fmt.format_success("tool", "short output")
        assert result == "short output"

    def test_long_result_truncated(self):
        fmt = ToolResultFormatter(max_length=20, truncation_marker="...[cut]")
        long_content = "x" * 100
        result = fmt.format_success("tool", long_content)
        assert len(result) <= 20 + len("...[cut]")
        assert "...[cut]" in result

    def test_error_format(self):
        fmt = ToolResultFormatter(error_prefix="ERR: ")
        result = fmt.format_error("tool", "something went wrong")
        assert result.startswith("ERR: ")
        assert "something went wrong" in result

    def test_denied_format(self):
        fmt = ToolResultFormatter()
        result = fmt.format_denied("bad_tool", "not in allow list")
        assert "bad_tool" in result
        assert "not in allow list" in result

    def test_metadata_included(self):
        fmt = ToolResultFormatter(include_metadata=True)
        result = fmt.format_success("my_tool", "output", duration=0.123)
        assert "my_tool" in result
        assert "0.123" in result

    def test_metadata_excluded_by_default(self):
        fmt = ToolResultFormatter(include_metadata=False)
        result = fmt.format_success("my_tool", "output", duration=0.123)
        assert "my_tool" not in result


# ─── ToolStats / StatsTracker ─────────────────────────────────────────────────

class TestToolStats:
    def test_initial_zero(self):
        stats = ToolStats(tool_name="read_file")
        assert stats.total_calls == 0
        assert stats.success_rate == 0.0

    def test_record_success(self):
        stats = ToolStats(tool_name="read_file")
        stats.record(ToolCallRecord("read_file", success=True, duration=0.1))
        assert stats.total_calls == 1
        assert stats.success_calls == 1
        assert stats.success_rate == 1.0

    def test_record_error(self):
        stats = ToolStats(tool_name="read_file")
        stats.record(ToolCallRecord("read_file", success=False, duration=0.05))
        assert stats.error_calls == 1
        assert stats.success_rate == 0.0

    def test_record_denied(self):
        stats = ToolStats(tool_name="bad")
        stats.record(ToolCallRecord("bad", success=False, denied=True, duration=0.0))
        assert stats.denied_calls == 1

    def test_avg_duration(self):
        stats = ToolStats(tool_name="t")
        stats.record(ToolCallRecord("t", success=True, duration=0.1))
        stats.record(ToolCallRecord("t", success=True, duration=0.3))
        assert abs(stats.avg_duration - 0.2) < 1e-9

    def test_to_dict(self):
        stats = ToolStats(tool_name="read_file")
        stats.record(ToolCallRecord("read_file", success=True, duration=0.1))
        d = stats.to_dict()
        assert d["tool"] == "read_file"
        assert d["success"] == 1
        assert d["success_rate"] == 1.0


class TestStatsTracker:
    def test_track_multiple_tools(self):
        tracker = StatsTracker()
        tracker.record(ToolCallRecord("read_file", success=True, duration=0.1))
        tracker.record(ToolCallRecord("write_file", success=True, duration=0.2))
        tracker.record(ToolCallRecord("read_file", success=False, duration=0.05))

        assert tracker.total_calls == 3
        assert tracker.get("read_file").total_calls == 2
        assert tracker.get("write_file").total_calls == 1

    def test_reset(self):
        tracker = StatsTracker()
        tracker.record(ToolCallRecord("t", success=True, duration=0.1))
        tracker.reset()
        assert tracker.total_calls == 0
        assert tracker.get("t") is None

    def test_summary(self):
        tracker = StatsTracker()
        tracker.record(ToolCallRecord("read_file", success=True, duration=0.1))
        summary = tracker.summary()
        assert summary["total_calls"] == 1
        assert "read_file" in summary["tools"]

    def test_denied_count(self):
        tracker = StatsTracker()
        tracker.record(ToolCallRecord("bad", success=False, denied=True, duration=0.0))
        tracker.record(ToolCallRecord("good", success=True, duration=0.1))
        assert tracker.denied_calls == 1


# ─── ManagedToolRegistry ──────────────────────────────────────────────────────

class TestManagedToolRegistry:
    def test_execute_allowed_tool(self):
        reg = make_registry("echo")
        result = reg.execute(ToolUseBlock(id="t1", name="echo", input={"target": "hello"}))
        assert not result.is_error
        assert "echo" in result.content

    def test_execute_denied_tool(self):
        reg = make_registry("echo", "bad",
                            permission=ToolPermission.deny_only(["bad"]))
        result = reg.execute(ToolUseBlock(id="t1", name="bad", input={}))
        assert result.is_error
        assert "denied" in result.content.lower() or "Permission" in result.content

    def test_execute_not_in_allow_list(self):
        reg = make_registry("read_file", "write_file",
                            permission=ToolPermission.allow_only(["read_file"]))
        result = reg.execute(ToolUseBlock(id="t1", name="write_file", input={"target": "x"}))
        assert result.is_error

    def test_execute_unknown_tool(self):
        reg = make_registry("echo")
        result = reg.execute(ToolUseBlock(id="t1", name="unknown", input={}))
        assert result.is_error

    def test_execute_error_tool(self):
        reg = ManagedToolRegistry()
        reg.register(error_tool("bad"))
        result = reg.execute(ToolUseBlock(id="t1", name="bad", input={}))
        assert result.is_error

    def test_stats_recorded_on_success(self):
        reg = make_registry("echo")
        reg.execute(ToolUseBlock(id="t1", name="echo", input={"target": "x"}))
        stats = reg.stats.get("echo")
        assert stats is not None
        assert stats.success_calls == 1

    def test_stats_recorded_on_deny(self):
        reg = make_registry("bad",
                            permission=ToolPermission.deny_only(["bad"]))
        reg.execute(ToolUseBlock(id="t1", name="bad", input={}))
        stats = reg.stats.get("bad")
        assert stats.denied_calls == 1

    def test_result_truncated(self):
        reg = ManagedToolRegistry(
            formatter=ToolResultFormatter(max_length=10, truncation_marker="...")
        )
        reg.register(ToolDefinition(
            name="big",
            description="",
            input_schema={},
            handler=lambda inp: "x" * 1000,
        ))
        result = reg.execute(ToolUseBlock(id="t1", name="big", input={}))
        assert not result.is_error
        assert len(result.content) <= 10 + len("...")

    def test_to_api_format_filters_denied(self):
        reg = make_registry("read_file", "write_file", "dangerous",
                            permission=ToolPermission.deny_only(["dangerous"]))
        api = reg.to_api_format()
        names = [t["name"] for t in api]
        assert "read_file" in names
        assert "write_file" in names
        assert "dangerous" not in names

    def test_to_api_format_allow_list(self):
        reg = make_registry("read_file", "write_file", "search",
                            permission=ToolPermission.allow_only(["read_file"]))
        api = reg.to_api_format()
        names = [t["name"] for t in api]
        assert names == ["read_file"]

    def test_rate_limit_blocks_after_limit(self):
        reg = make_registry(
            "read_file",
            permission=ToolPermission(
                rate_limits={"read_file": RateLimit(max_calls=2, window_seconds=60)}
            ),
        )
        reg.execute(ToolUseBlock(id="t1", name="read_file", input={"target": "a"}))
        reg.execute(ToolUseBlock(id="t2", name="read_file", input={"target": "b"}))
        # Third call should be rate-limited
        result = reg.execute(ToolUseBlock(id="t3", name="read_file", input={"target": "c"}))
        assert result.is_error
        assert "rate" in result.content.lower()

    def test_integration_with_learner(self):
        """ManagedToolRegistry integrates with LearnerService"""
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
            name="Test",
            description="",
            stage=LearningStage.BEGINNER,
            difficulty=0.3,
            tasks=[TaskConfig(
                id="t1", type="test",
                description="Read a file", target="test.txt",
                tools_required=["read_file"],
            )],
            available_tools=["read_file", "write_file"],
        )

        records = learner.run_experiments(env, max_iterations=1)
        assert len(records) > 0

        # Engine should use ManagedToolRegistry
        assert isinstance(learner._query_engine.tools, ManagedToolRegistry)

        # Stats should be tracked
        stats = learner._query_engine.tools.stats.summary()
        assert "total_calls" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
