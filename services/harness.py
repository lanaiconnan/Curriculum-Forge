"""Harness — Agent Behavior Verification Framework

Inspired by Claude Code's harness/ pattern:
- Define test cases (expected tool + params)
- Run QueryEngine, capture actual tool_calls
- Compare actual vs expected
- Generate pass/fail report

Core insight: don't test LLM text output,
test WHICH tool it called and WITH WHAT PARAMS.
This maps directly to ToolRL reward design:
  rname  = tool name match
  rparam = parameter match

Usage:
    runner = HarnessRunner(engine)

    cases = [
        HarnessCase(
            id="read-basic",
            prompt="Read the file config.json",
            expected_tool="read_file",
            expected_params={"path": "config.json"},
        ),
    ]

    report = runner.run(cases)
    print(report.summary())
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from enum import Enum
import logging
import time
import json

from .query_engine import QueryEngine, QueryResult, QueryConfig, ToolRegistry

logger = logging.getLogger(__name__)


# ─── Verdict ──────────────────────────────────────────────────────────────────

class Verdict(Enum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"   # Right tool, wrong params
    SKIP = "skip"         # No tool called (when one was expected)
    ERROR = "error"       # QueryEngine error


# ─── HarnessCase ─────────────────────────────────────────────────────────────

@dataclass
class HarnessCase:
    """
    A single harness test case.

    Defines what the LLM SHOULD do given a prompt.
    The harness verifies it actually does it.
    """
    id: str
    prompt: str
    expected_tool: str                          # Tool name that must be called
    expected_params: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    tags: List[str] = field(default_factory=list)
    param_tolerance: float = 0.0                # 0.0 = exact, 1.0 = ignore params
    require_first_call: bool = True             # Must be the FIRST tool call
    extra_system: Optional[str] = None         # Extra system context for this case


# ─── CaseResult ──────────────────────────────────────────────────────────────

@dataclass
class CaseResult:
    """Result of running a single HarnessCase"""
    case_id: str
    verdict: Verdict
    actual_tool: Optional[str]
    actual_params: Dict[str, Any]
    expected_tool: str
    expected_params: Dict[str, Any]

    # Scores (mirrors ToolRL reward components)
    rname: float    # 1.0 = correct tool, -1.0 = wrong tool, 0.0 = no call
    rparam: float   # [-1, 1] parameter match score
    rfinal: float   # Combined score

    turns: int = 0
    duration: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "verdict": self.verdict.value,
            "actual_tool": self.actual_tool,
            "expected_tool": self.expected_tool,
            "rname": round(self.rname, 3),
            "rparam": round(self.rparam, 3),
            "rfinal": round(self.rfinal, 3),
            "turns": self.turns,
            "duration": round(self.duration, 3),
            "error": self.error,
        }


# ─── HarnessReport ────────────────────────────────────────────────────────────

@dataclass
class HarnessReport:
    """Aggregated results from running a harness suite"""
    results: List[CaseResult]
    suite_name: str = "harness"
    duration: float = 0.0

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.verdict == Verdict.PASS)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.verdict == Verdict.FAIL)

    @property
    def partial(self) -> int:
        return sum(1 for r in self.results if r.verdict == Verdict.PARTIAL)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.verdict == Verdict.SKIP)

    @property
    def errors(self) -> int:
        return sum(1 for r in self.results if r.verdict == Verdict.ERROR)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total > 0 else 0.0

    @property
    def tool_accuracy(self) -> float:
        """Fraction of cases where correct tool was called"""
        correct = sum(
            1 for r in self.results
            if r.actual_tool == r.expected_tool
        )
        return correct / self.total if self.total > 0 else 0.0

    @property
    def avg_rname(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.rname for r in self.results) / len(self.results)

    @property
    def avg_rparam(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.rparam for r in self.results) / len(self.results)

    @property
    def avg_rfinal(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.rfinal for r in self.results) / len(self.results)

    def by_tag(self, tag: str) -> 'HarnessReport':
        """Filter results by tag"""
        # We need the original cases to filter by tag
        # Return a sub-report with matching results
        return HarnessReport(
            results=self.results,  # Simplified: return all
            suite_name=f"{self.suite_name}[{tag}]",
        )

    def failures(self) -> List[CaseResult]:
        return [r for r in self.results if r.verdict in (Verdict.FAIL, Verdict.PARTIAL, Verdict.SKIP)]

    def summary(self) -> str:
        lines = [
            f"{'='*50}",
            f"Harness Report: {self.suite_name}",
            f"{'='*50}",
            f"Total:    {self.total}",
            f"Pass:     {self.passed}  ({self.pass_rate:.1%})",
            f"Partial:  {self.partial}",
            f"Fail:     {self.failed}",
            f"Skip:     {self.skipped}",
            f"Error:    {self.errors}",
            f"{'─'*50}",
            f"Tool accuracy:  {self.tool_accuracy:.1%}",
            f"Avg rname:      {self.avg_rname:+.3f}",
            f"Avg rparam:     {self.avg_rparam:+.3f}",
            f"Avg rfinal:     {self.avg_rfinal:+.3f}",
            f"Duration:       {self.duration:.2f}s",
            f"{'='*50}",
        ]

        if self.failures():
            lines.append("Failures:")
            for r in self.failures():
                lines.append(
                    f"  [{r.verdict.value.upper()}] {r.case_id}: "
                    f"expected={r.expected_tool}, actual={r.actual_tool or 'none'} "
                    f"rfinal={r.rfinal:+.2f}"
                )

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suite": self.suite_name,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "partial": self.partial,
            "skipped": self.skipped,
            "errors": self.errors,
            "pass_rate": round(self.pass_rate, 4),
            "tool_accuracy": round(self.tool_accuracy, 4),
            "avg_rname": round(self.avg_rname, 4),
            "avg_rparam": round(self.avg_rparam, 4),
            "avg_rfinal": round(self.avg_rfinal, 4),
            "duration": round(self.duration, 3),
            "results": [r.to_dict() for r in self.results],
        }


# ─── Scorer ───────────────────────────────────────────────────────────────────

class HarnessScorer:
    """
    Scores a single case result.

    Mirrors ToolRL reward design:
      rname  ∈ {-1.0, 1.0}
      rparam ∈ [-1.0, 1.0]
      rfinal = rname + rparam (normalized)
    """

    def score(
        self,
        actual_tool: Optional[str],
        actual_params: Dict[str, Any],
        expected_tool: str,
        expected_params: Dict[str, Any],
        param_tolerance: float = 0.0,
    ) -> tuple:
        """
        Returns (rname, rparam, rfinal, verdict)
        """
        # No tool called
        if not actual_tool:
            return 0.0, 0.0, 0.0, Verdict.SKIP

        # Tool name score
        rname = 1.0 if actual_tool == expected_tool else -1.0

        # Parameter score
        rparam = self._score_params(actual_params, expected_params, param_tolerance)

        # Final score
        rfinal = (rname + rparam) / 2.0

        # Verdict
        if rname == 1.0 and rparam >= (1.0 - param_tolerance):
            verdict = Verdict.PASS
        elif rname == 1.0:
            verdict = Verdict.PARTIAL
        else:
            verdict = Verdict.FAIL

        return rname, rparam, rfinal, verdict

    def _score_params(
        self,
        actual: Dict[str, Any],
        expected: Dict[str, Any],
        tolerance: float,
    ) -> float:
        """Score parameter match in [-1, 1]"""
        if not expected:
            # No params expected — any params are fine
            return 1.0

        if not actual:
            return -1.0

        matches = 0
        total = len(expected)

        for key, exp_val in expected.items():
            if key not in actual:
                continue
            act_val = actual[key]

            if self._values_match(act_val, exp_val, tolerance):
                matches += 1

        # Scale to [-1, 1]
        ratio = matches / total
        return ratio * 2.0 - 1.0

    def _values_match(self, actual: Any, expected: Any, tolerance: float) -> bool:
        """Check if two values match within tolerance"""
        if actual == expected:
            return True

        # Numeric tolerance
        if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
            if expected == 0:
                return actual == 0
            return abs(actual - expected) / abs(expected) <= tolerance

        # String: case-insensitive if tolerance > 0
        if isinstance(actual, str) and isinstance(expected, str):
            if tolerance > 0:
                return actual.lower() == expected.lower()

        return False


# ─── HarnessRunner ────────────────────────────────────────────────────────────

class HarnessRunner:
    """
    Runs a suite of HarnessCases against a QueryEngine.

    Mirrors Claude Code's harness execution pattern:
    1. For each case: submit prompt to QueryEngine
    2. Capture actual tool_calls from QueryResult
    3. Score with HarnessScorer
    4. Aggregate into HarnessReport
    """

    def __init__(
        self,
        engine: QueryEngine,
        scorer: Optional[HarnessScorer] = None,
        on_result: Optional[Callable[[CaseResult], None]] = None,
    ):
        self.engine = engine
        self.scorer = scorer or HarnessScorer()
        self.on_result = on_result

    def run_case(self, case: HarnessCase) -> CaseResult:
        """Run a single harness case"""
        start = time.time()

        try:
            # Reset engine for each case (fresh conversation)
            self.engine.reset()

            # Submit prompt
            query_result = self.engine.submit(
                case.prompt,
                extra_system=case.extra_system,
            )

            duration = time.time() - start

            if not query_result.success:
                return CaseResult(
                    case_id=case.id,
                    verdict=Verdict.ERROR,
                    actual_tool=None,
                    actual_params={},
                    expected_tool=case.expected_tool,
                    expected_params=case.expected_params,
                    rname=0.0, rparam=0.0, rfinal=0.0,
                    turns=query_result.turns,
                    duration=duration,
                    error=query_result.error,
                )

            # Extract actual tool call
            tool_calls = query_result.tool_calls
            if case.require_first_call and tool_calls:
                actual_call = tool_calls[0]
            elif tool_calls:
                # Find the call matching expected tool (if any)
                matching = [tc for tc in tool_calls if tc["name"] == case.expected_tool]
                actual_call = matching[0] if matching else tool_calls[0]
            else:
                actual_call = None

            actual_tool = actual_call["name"] if actual_call else None
            actual_params = actual_call["input"] if actual_call else {}

            # Score
            rname, rparam, rfinal, verdict = self.scorer.score(
                actual_tool=actual_tool,
                actual_params=actual_params,
                expected_tool=case.expected_tool,
                expected_params=case.expected_params,
                param_tolerance=case.param_tolerance,
            )

            result = CaseResult(
                case_id=case.id,
                verdict=verdict,
                actual_tool=actual_tool,
                actual_params=actual_params,
                expected_tool=case.expected_tool,
                expected_params=case.expected_params,
                rname=rname,
                rparam=rparam,
                rfinal=rfinal,
                turns=query_result.turns,
                duration=duration,
            )

        except Exception as e:
            duration = time.time() - start
            logger.error(f"HarnessCase '{case.id}' error: {e}")
            result = CaseResult(
                case_id=case.id,
                verdict=Verdict.ERROR,
                actual_tool=None,
                actual_params={},
                expected_tool=case.expected_tool,
                expected_params=case.expected_params,
                rname=0.0, rparam=0.0, rfinal=0.0,
                duration=duration,
                error=str(e),
            )

        logger.info(
            f"[{result.verdict.value.upper():7s}] {case.id}: "
            f"expected={case.expected_tool}, actual={result.actual_tool or 'none'} "
            f"rfinal={result.rfinal:+.2f}"
        )

        if self.on_result:
            self.on_result(result)

        return result

    def run(
        self,
        cases: List[HarnessCase],
        suite_name: str = "harness",
    ) -> HarnessReport:
        """
        Run all cases and return aggregated report.

        Args:
            cases: List of test cases
            suite_name: Name for the report

        Returns:
            HarnessReport with all results
        """
        logger.info(f"Running harness suite '{suite_name}' ({len(cases)} cases)")
        start = time.time()

        results = []
        for i, case in enumerate(cases):
            logger.debug(f"Case {i+1}/{len(cases)}: {case.id}")
            result = self.run_case(case)
            results.append(result)

        duration = time.time() - start

        report = HarnessReport(
            results=results,
            suite_name=suite_name,
            duration=duration,
        )

        logger.info(
            f"Suite '{suite_name}' complete: "
            f"{report.passed}/{report.total} passed "
            f"({report.pass_rate:.1%}) in {duration:.2f}s"
        )

        return report


# ─── HarnessSuite ─────────────────────────────────────────────────────────────

class HarnessSuite:
    """
    A named collection of HarnessCases.

    Supports:
    - Tag-based filtering
    - Case registration via decorator
    - Serialization to/from JSON

    Usage:
        suite = HarnessSuite("tool-basics")

        @suite.case(expected_tool="read_file")
        def read_config(self):
            return HarnessCase(
                id="read-config",
                prompt="Read config.json",
                expected_tool="read_file",
                expected_params={"path": "config.json"},
            )

        # Or directly:
        suite.add(HarnessCase(...))
    """

    def __init__(self, name: str):
        self.name = name
        self._cases: List[HarnessCase] = []

    def add(self, case: HarnessCase) -> 'HarnessSuite':
        self._cases.append(case)
        return self

    def cases(self, tags: Optional[List[str]] = None) -> List[HarnessCase]:
        """Get cases, optionally filtered by tags"""
        if not tags:
            return self._cases.copy()
        return [c for c in self._cases if any(t in c.tags for t in tags)]

    def __len__(self) -> int:
        return len(self._cases)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "cases": [
                {
                    "id": c.id,
                    "prompt": c.prompt,
                    "expected_tool": c.expected_tool,
                    "expected_params": c.expected_params,
                    "description": c.description,
                    "tags": c.tags,
                    "param_tolerance": c.param_tolerance,
                }
                for c in self._cases
            ],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HarnessSuite':
        suite = cls(data["name"])
        for c in data.get("cases", []):
            suite.add(HarnessCase(
                id=c["id"],
                prompt=c["prompt"],
                expected_tool=c["expected_tool"],
                expected_params=c.get("expected_params", {}),
                description=c.get("description", ""),
                tags=c.get("tags", []),
                param_tolerance=c.get("param_tolerance", 0.0),
            ))
        return suite

    @classmethod
    def from_json(cls, path: str) -> 'HarnessSuite':
        with open(path) as f:
            return cls.from_dict(json.load(f))

    def to_json(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)


# ─── Built-in Suites ──────────────────────────────────────────────────────────

def build_tool_basics_suite(available_tools: List[str]) -> HarnessSuite:
    """
    Build a basic tool-calling harness suite.

    Tests that the LLM calls the right tool for common prompts.
    Designed to work with any ToolRegistry.
    """
    suite = HarnessSuite("tool-basics")

    if "read_file" in available_tools:
        suite.add(HarnessCase(
            id="read-file-basic",
            prompt="Read the contents of config.json",
            expected_tool="read_file",
            expected_params={"target": "config.json"},
            description="Basic file read",
            tags=["read", "basic"],
            param_tolerance=0.0,
        ))
        suite.add(HarnessCase(
            id="read-file-path",
            prompt="Show me what's in /tmp/output.txt",
            expected_tool="read_file",
            expected_params={"target": "/tmp/output.txt"},
            description="File read with path",
            tags=["read", "path"],
            param_tolerance=0.0,
        ))

    if "write_file" in available_tools:
        suite.add(HarnessCase(
            id="write-file-basic",
            prompt="Write 'hello world' to output.txt",
            expected_tool="write_file",
            expected_params={"target": "output.txt"},
            description="Basic file write",
            tags=["write", "basic"],
            param_tolerance=0.5,  # Content may vary
        ))

    if "search" in available_tools:
        suite.add(HarnessCase(
            id="search-basic",
            prompt="Search for 'error' in the logs",
            expected_tool="search",
            expected_params={"target": "error"},
            description="Basic search",
            tags=["search", "basic"],
            param_tolerance=0.3,
        ))

    return suite


def build_curriculum_suite(stage: str) -> HarnessSuite:
    """
    Build a harness suite for a specific learning stage.

    Beginner: single tool, simple params
    Intermediate: tool selection, param matching
    Advanced: multi-step, edge cases
    """
    suite = HarnessSuite(f"curriculum-{stage}")

    if stage == "beginner":
        suite.add(HarnessCase(
            id="beginner-read",
            prompt="Read the file data.csv",
            expected_tool="read_file",
            expected_params={"target": "data.csv"},
            tags=["beginner", "read"],
        ))
        suite.add(HarnessCase(
            id="beginner-write",
            prompt="Save the result to result.txt",
            expected_tool="write_file",
            expected_params={"target": "result.txt"},
            tags=["beginner", "write"],
            param_tolerance=0.5,
        ))

    elif stage == "intermediate":
        suite.add(HarnessCase(
            id="intermediate-search",
            prompt="Find all occurrences of 'TODO' in the codebase",
            expected_tool="search",
            expected_params={"target": "TODO"},
            tags=["intermediate", "search"],
            param_tolerance=0.2,
        ))
        suite.add(HarnessCase(
            id="intermediate-read-specific",
            prompt="Read the configuration from /etc/app/config.yaml",
            expected_tool="read_file",
            expected_params={"target": "/etc/app/config.yaml"},
            tags=["intermediate", "read"],
        ))

    elif stage == "advanced":
        suite.add(HarnessCase(
            id="advanced-write-structured",
            prompt="Write a JSON report with key 'status' set to 'complete' to report.json",
            expected_tool="write_file",
            expected_params={"target": "report.json"},
            tags=["advanced", "write", "json"],
            param_tolerance=0.3,
        ))

    return suite
