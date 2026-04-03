"""Unit tests for Harness

Run: pytest tests/unit/test_harness.py -v
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.harness import (
    HarnessCase,
    CaseResult,
    HarnessReport,
    HarnessRunner,
    HarnessSuite,
    HarnessScorer,
    Verdict,
    build_tool_basics_suite,
    build_curriculum_suite,
)
from services.query_engine import (
    QueryEngine,
    QueryConfig,
    ToolRegistry,
    ToolDefinition,
    LLMResponse,
    ToolUseBlock,
    MockBackend,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_engine_with_responses(responses):
    """Build a QueryEngine with scripted responses"""

    class FixedBackend(MockBackend):
        def __init__(self, resps):
            super().__init__()
            self._resps = list(resps)
            self._idx = 0

        def call(self, messages, system, tools, max_tokens):
            if self._idx < len(self._resps):
                r = self._resps[self._idx]
                self._idx += 1
                return r
            return LLMResponse("Done.", [], "end_turn", 10, 5)

    registry = ToolRegistry()
    for name in ["read_file", "write_file", "search"]:
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

    engine = QueryEngine(
        backend=FixedBackend(responses),
        tools=registry,
        config=QueryConfig(max_turns=3),
    )
    return engine


def tool_response(name, target, extra=None):
    """Helper: LLM calls a tool"""
    inp = {"target": target}
    if extra:
        inp.update(extra)
    return LLMResponse(
        content=f"Using {name}...",
        tool_uses=[ToolUseBlock(id="t1", name=name, input=inp)],
        stop_reason="tool_use",
        input_tokens=50, output_tokens=20,
    )


def end_response(content="Done."):
    return LLMResponse(content=content, tool_uses=[], stop_reason="end_turn",
                       input_tokens=30, output_tokens=10)


# ─── HarnessScorer ────────────────────────────────────────────────────────────

class TestHarnessScorer:
    def setup_method(self):
        self.scorer = HarnessScorer()

    def test_perfect_match(self):
        rname, rparam, rfinal, verdict = self.scorer.score(
            actual_tool="read_file",
            actual_params={"target": "config.json"},
            expected_tool="read_file",
            expected_params={"target": "config.json"},
        )
        assert rname == 1.0
        assert rparam == 1.0
        assert verdict == Verdict.PASS

    def test_wrong_tool(self):
        rname, rparam, rfinal, verdict = self.scorer.score(
            actual_tool="write_file",
            actual_params={"target": "config.json"},
            expected_tool="read_file",
            expected_params={"target": "config.json"},
        )
        assert rname == -1.0
        assert verdict == Verdict.FAIL

    def test_right_tool_wrong_params(self):
        rname, rparam, rfinal, verdict = self.scorer.score(
            actual_tool="read_file",
            actual_params={"target": "wrong.json"},
            expected_tool="read_file",
            expected_params={"target": "config.json"},
        )
        assert rname == 1.0
        assert rparam < 1.0
        assert verdict == Verdict.PARTIAL

    def test_no_tool_called(self):
        rname, rparam, rfinal, verdict = self.scorer.score(
            actual_tool=None,
            actual_params={},
            expected_tool="read_file",
            expected_params={},
        )
        assert verdict == Verdict.SKIP
        assert rfinal == 0.0

    def test_no_expected_params(self):
        """When no params expected, any params are fine"""
        rname, rparam, rfinal, verdict = self.scorer.score(
            actual_tool="read_file",
            actual_params={"target": "anything.txt"},
            expected_tool="read_file",
            expected_params={},
        )
        assert rname == 1.0
        assert rparam == 1.0
        assert verdict == Verdict.PASS

    def test_param_tolerance(self):
        """With tolerance, close values should match"""
        rname, rparam, rfinal, verdict = self.scorer.score(
            actual_tool="read_file",
            actual_params={"target": "Config.json"},  # Different case
            expected_tool="read_file",
            expected_params={"target": "config.json"},
            param_tolerance=0.5,
        )
        assert verdict == Verdict.PASS

    def test_partial_param_match(self):
        """Partial param match gives intermediate score"""
        rname, rparam, rfinal, verdict = self.scorer.score(
            actual_tool="read_file",
            actual_params={"target": "config.json", "extra": "x"},
            expected_tool="read_file",
            expected_params={"target": "config.json", "mode": "binary"},
        )
        # target matches, mode doesn't → 1/2 = 0.5 → rparam = 0.5*2-1 = 0.0
        assert rname == 1.0
        assert rparam == 0.0

    def test_rfinal_is_average(self):
        rname, rparam, rfinal, verdict = self.scorer.score(
            actual_tool="read_file",
            actual_params={"target": "config.json"},
            expected_tool="read_file",
            expected_params={"target": "config.json"},
        )
        assert abs(rfinal - (rname + rparam) / 2.0) < 1e-9


# ─── HarnessReport ────────────────────────────────────────────────────────────

class TestHarnessReport:
    def _make_result(self, verdict, rname=1.0, rparam=1.0):
        rfinal = (rname + rparam) / 2.0
        return CaseResult(
            case_id="test",
            verdict=verdict,
            actual_tool="read_file",
            actual_params={},
            expected_tool="read_file",
            expected_params={},
            rname=rname, rparam=rparam, rfinal=rfinal,
        )

    def test_pass_rate(self):
        results = [
            self._make_result(Verdict.PASS),
            self._make_result(Verdict.PASS),
            self._make_result(Verdict.FAIL),
            self._make_result(Verdict.SKIP),
        ]
        report = HarnessReport(results=results)
        assert report.pass_rate == 0.5
        assert report.passed == 2
        assert report.failed == 1
        assert report.skipped == 1

    def test_tool_accuracy(self):
        results = [
            self._make_result(Verdict.PASS),
            self._make_result(Verdict.PARTIAL),
            CaseResult("x", Verdict.FAIL, "wrong_tool", {}, "read_file", {},
                       -1.0, -1.0, -1.0),
        ]
        report = HarnessReport(results=results)
        # 2 out of 3 have actual_tool == expected_tool
        assert report.tool_accuracy == pytest.approx(2/3)

    def test_avg_scores(self):
        results = [
            self._make_result(Verdict.PASS, rname=1.0, rparam=1.0),
            self._make_result(Verdict.FAIL, rname=-1.0, rparam=-1.0),
        ]
        report = HarnessReport(results=results)
        assert report.avg_rname == 0.0
        assert report.avg_rparam == 0.0

    def test_summary_string(self):
        results = [self._make_result(Verdict.PASS)]
        report = HarnessReport(results=results, suite_name="test-suite")
        summary = report.summary()
        assert "test-suite" in summary
        assert "100.0%" in summary

    def test_to_dict(self):
        results = [self._make_result(Verdict.PASS)]
        report = HarnessReport(results=results)
        d = report.to_dict()
        assert d["passed"] == 1
        assert d["pass_rate"] == 1.0
        assert len(d["results"]) == 1

    def test_failures_filter(self):
        results = [
            self._make_result(Verdict.PASS),
            self._make_result(Verdict.FAIL),
            self._make_result(Verdict.PARTIAL),
        ]
        report = HarnessReport(results=results)
        failures = report.failures()
        assert len(failures) == 2


# ─── HarnessRunner ────────────────────────────────────────────────────────────

class TestHarnessRunner:
    def test_pass_case(self):
        """LLM calls correct tool → PASS"""
        engine = make_engine_with_responses([
            tool_response("read_file", "config.json"),
            end_response(),
        ])
        runner = HarnessRunner(engine)
        case = HarnessCase(
            id="test-pass",
            prompt="Read config.json",
            expected_tool="read_file",
            expected_params={"target": "config.json"},
        )
        result = runner.run_case(case)
        assert result.verdict == Verdict.PASS
        assert result.actual_tool == "read_file"
        assert result.rname == 1.0

    def test_fail_case(self):
        """LLM calls wrong tool → FAIL"""
        engine = make_engine_with_responses([
            tool_response("write_file", "config.json"),
            end_response(),
        ])
        runner = HarnessRunner(engine)
        case = HarnessCase(
            id="test-fail",
            prompt="Read config.json",
            expected_tool="read_file",
            expected_params={"target": "config.json"},
        )
        result = runner.run_case(case)
        assert result.verdict == Verdict.FAIL
        assert result.rname == -1.0

    def test_skip_case(self):
        """LLM calls no tool → SKIP"""
        engine = make_engine_with_responses([end_response("I don't need tools.")])
        runner = HarnessRunner(engine)
        case = HarnessCase(
            id="test-skip",
            prompt="Read config.json",
            expected_tool="read_file",
        )
        result = runner.run_case(case)
        assert result.verdict == Verdict.SKIP

    def test_partial_case(self):
        """LLM calls right tool, wrong params → PARTIAL"""
        engine = make_engine_with_responses([
            tool_response("read_file", "wrong.json"),
            end_response(),
        ])
        runner = HarnessRunner(engine)
        case = HarnessCase(
            id="test-partial",
            prompt="Read config.json",
            expected_tool="read_file",
            expected_params={"target": "config.json"},
        )
        result = runner.run_case(case)
        assert result.verdict == Verdict.PARTIAL
        assert result.rname == 1.0
        assert result.rparam < 1.0

    def test_run_suite(self):
        """Run multiple cases"""
        engine = make_engine_with_responses([
            tool_response("read_file", "config.json"), end_response(),
            tool_response("write_file", "out.txt"), end_response(),
            end_response("No tool needed"),
        ])
        runner = HarnessRunner(engine)
        cases = [
            HarnessCase("c1", "Read config.json", "read_file", {"target": "config.json"}),
            HarnessCase("c2", "Write to out.txt", "write_file", {"target": "out.txt"}),
            HarnessCase("c3", "Read data.csv", "read_file"),
        ]
        report = runner.run(cases, suite_name="test-suite")
        assert report.total == 3
        assert report.passed >= 1

    def test_callback_called(self):
        """on_result callback should be called for each case"""
        engine = make_engine_with_responses([end_response()])
        results_received = []
        runner = HarnessRunner(engine, on_result=results_received.append)
        case = HarnessCase("c1", "test", "read_file")
        runner.run_case(case)
        assert len(results_received) == 1

    def test_engine_reset_between_cases(self):
        """Each case should start with fresh message history"""
        engine = make_engine_with_responses([
            tool_response("read_file", "a.txt"), end_response(),
            tool_response("read_file", "b.txt"), end_response(),
        ])
        runner = HarnessRunner(engine)
        cases = [
            HarnessCase("c1", "Read a.txt", "read_file"),
            HarnessCase("c2", "Read b.txt", "read_file"),
        ]
        report = runner.run(cases)
        # Both should pass independently
        assert report.total == 2


# ─── HarnessSuite ─────────────────────────────────────────────────────────────

class TestHarnessSuite:
    def test_add_and_len(self):
        suite = HarnessSuite("test")
        suite.add(HarnessCase("c1", "prompt", "tool"))
        suite.add(HarnessCase("c2", "prompt", "tool"))
        assert len(suite) == 2

    def test_filter_by_tag(self):
        suite = HarnessSuite("test")
        suite.add(HarnessCase("c1", "p", "t", tags=["read"]))
        suite.add(HarnessCase("c2", "p", "t", tags=["write"]))
        suite.add(HarnessCase("c3", "p", "t", tags=["read", "advanced"]))

        read_cases = suite.cases(tags=["read"])
        assert len(read_cases) == 2

    def test_to_from_dict(self):
        suite = HarnessSuite("test")
        suite.add(HarnessCase(
            id="c1",
            prompt="Read config.json",
            expected_tool="read_file",
            expected_params={"target": "config.json"},
            tags=["read"],
        ))
        d = suite.to_dict()
        restored = HarnessSuite.from_dict(d)
        assert len(restored) == 1
        assert restored.cases()[0].id == "c1"
        assert restored.cases()[0].expected_tool == "read_file"

    def test_to_from_json(self, tmp_path):
        suite = HarnessSuite("test")
        suite.add(HarnessCase("c1", "Read file", "read_file"))
        path = str(tmp_path / "suite.json")
        suite.to_json(path)
        restored = HarnessSuite.from_json(path)
        assert len(restored) == 1


# ─── Built-in Suites ──────────────────────────────────────────────────────────

class TestBuiltinSuites:
    def test_tool_basics_suite(self):
        suite = build_tool_basics_suite(["read_file", "write_file", "search"])
        assert len(suite) > 0
        tools = {c.expected_tool for c in suite.cases()}
        assert "read_file" in tools

    def test_tool_basics_empty_tools(self):
        suite = build_tool_basics_suite([])
        assert len(suite) == 0

    def test_curriculum_beginner(self):
        suite = build_curriculum_suite("beginner")
        assert len(suite) > 0
        assert all("beginner" in c.tags for c in suite.cases())

    def test_curriculum_intermediate(self):
        suite = build_curriculum_suite("intermediate")
        assert len(suite) > 0

    def test_curriculum_advanced(self):
        suite = build_curriculum_suite("advanced")
        assert len(suite) > 0

    def test_run_curriculum_suite(self):
        """Run curriculum suite against mock engine"""
        suite = build_curriculum_suite("beginner")
        engine = make_engine_with_responses(
            [tool_response("read_file", "data.csv"), end_response()] * 10
        )
        runner = HarnessRunner(engine)
        report = runner.run(suite.cases(), suite_name=suite.name)
        assert report.total == len(suite)
        assert report.pass_rate >= 0.0  # At least runs without error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
