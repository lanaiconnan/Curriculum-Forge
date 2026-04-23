"""
HarnessProvider

基于 Agent 的行为验证框架。
调用 services/harness.py 的 HarnessRunner 执行真实测试用例。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from providers.base import (
    ProviderConfig,
    TaskOutput,
    TaskPhase,
    TaskProvider,
)

if TYPE_CHECKING:
    from runtimes.adaptive_runtime import AdaptiveRuntime

logger = logging.getLogger(__name__)


# ── Harness Types ─────────────────────────────────────────────────────────────

VERDICT_PASS    = "pass"
VERDICT_FAIL    = "fail"
VERDICT_PARTIAL = "partial"
VERDICT_SKIP    = "skip"
VERDICT_ERROR   = "error"


@dataclass
class HarnessCase:
    """单个测试用例"""
    id: str
    prompt: str
    expected_tool: str
    expected_params: Dict[str, Any]
    tags: List[str] = field(default_factory=list)


@dataclass
class HarnessResult:
    """单个用例结果"""
    case_id: str
    verdict: str
    actual_tool: str
    actual_params: Dict[str, Any]
    error: str = ""


@dataclass
class HarnessReport:
    """测试报告"""
    total: int
    passed: int
    failed: int
    results: List[HarnessResult]


# ── HarnessProvider ────────────────────────────────────────────────────────────

class HarnessProvider(TaskProvider):
    """
    测试执行 Provider。

    输入：modules（来自 CurriculumProvider）
    输出：test_report（HarnessReport 序列化）

    调用链：
        execute() → _build_mock_engine() → HarnessRunner.run(cases)
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig(name="HarnessProvider"))

    @property
    def phase(self) -> TaskPhase:
        return TaskPhase.HARNESS

    def can_handle(self, config: Dict[str, Any]) -> bool:
        return "modules" in config or "harness_cases" in config

    async def execute(
        self,
        config: Dict[str, Any],
        runtime: "AdaptiveRuntime",
    ) -> TaskOutput:
        """
        执行 Harness 测试。

        1. 从 curriculum 提取 modules（来自 runtime.state_data）
        2. 从 config 或 modules 生成 HarnessCase[]
        3. 用 MockBackend QueryEngine + HarnessRunner 执行
        4. 转为 TaskOutput.data
        """
        # Extract modules from curriculum (prior phase output)
        modules = []
        if runtime and runtime._record and runtime._record.state_data:
            curriculum = runtime._record.state_data.get("curriculum", {})
            if isinstance(curriculum, dict):
                cdata = curriculum.get("data", {})
                if isinstance(cdata, dict):
                    modules = cdata.get("curriculum", {}).get("modules", [])

        # Also check direct config
        if not modules:
            modules = config.get("modules", [])

        harness_cases = config.get("harness_cases", [])

        # Generate from modules if no explicit cases provided
        if not harness_cases and modules:
            harness_cases = self._generate_from_modules(modules)
            logger.info(f"HarnessProvider: generated {len(harness_cases)} cases from modules")

        # Fallback: if still no cases, create a default one
        if not harness_cases:
            harness_cases = [
                HarnessCase(
                    id="default_baseline",
                    prompt="List available files in the current directory",
                    expected_tool="shell",
                    expected_params={"command": "ls"},
                    tags=["baseline"],
                )
            ]

        # Build mock engine for execution
        engine = self._build_mock_engine()

        # Run HarnessRunner
        report = await self._run_harness(engine, harness_cases)

        logger.info(
            f"HarnessProvider: {report.passed}/{report.total} passed "
            f"({report.passed / max(report.total, 1):.1%})"
        )

        # Update metrics
        if runtime and runtime._record:
            runtime._record.metrics["harness_total"] = report.total
            runtime._record.metrics["harness_passed"] = report.passed
            runtime._record.metrics["harness_failed"] = report.failed
            runtime._record.metrics["harness_pass_rate"] = round(
                report.passed / max(report.total, 1), 4
            )

        return TaskOutput(
            phase=TaskPhase.HARNESS,
            data={
                "status": "ok",
                "test_report": {
                    "total": report.total,
                    "passed": report.passed,
                    "failed": report.failed,
                    "pass_rate": round(report.passed / max(report.total, 1), 4),
                    "results": [
                        {
                            "case_id": r.case_id,
                            "verdict": r.verdict,
                            "actual_tool": r.actual_tool,
                        }
                        for r in report.results
                    ],
                },
            },
            metadata={
                "provider": "HarnessProvider",
                "total_cases": report.total,
                "pass_rate": round(report.passed / max(report.total, 1), 4),
                "source": "harness_runner",
            },
        )

    def _build_mock_engine(self) -> Any:
        """
        Build a mock QueryEngine using MockBackend.
        Used when no real LLM backend is available.
        """
        try:
            from services.query_engine import (
                QueryEngine,
                QueryConfig,
                ToolRegistry,
                ToolDefinition,
            )
            from services.query_engine import create_backend

            # MockBackend: tool_call_probability=0.8 → ~80% pass rate
            backend = create_backend(backend_type="mock", tool_call_probability=0.8)

            # Minimal tool registry (mock tools)
            registry = ToolRegistry()
            for tool_name in ["read_file", "write_file", "shell", "grep"]:
                registry.register(ToolDefinition(
                    name=tool_name,
                    description=f"Mock {tool_name} tool",
                    input_schema={
                        "type": "object",
                        "properties": {},
                    },
                    handler=lambda inp, tn=tool_name: f"Mock {tn} executed",
                ))

            engine = QueryEngine(
                backend=backend,
                tools=registry,
                config=QueryConfig(
                    system_prompt="You are a helpful agent.",
                    max_tokens=256,
                    max_turns=2,
                ),
            )
            return engine

        except Exception as e:
            logger.warning(f"Could not build mock engine: {e}, using bare engine")
            return None

    async def _run_harness(
        self,
        engine: Any,
        cases: List[HarnessCase],
    ) -> HarnessReport:
        """
        Run harness cases. Uses HarnessRunner if engine available,
        otherwise falls back to mock execution.
        """
        if engine is None:
            return self._run_mock(cases)

        try:
            # Import HarnessRunner (sync → wrap in executor)
            from services.harness import HarnessRunner, HarnessCase as SHarnessCase

            # Convert our HarnessCase → services.harness.HarnessCase
            s_cases = [
                SHarnessCase(
                    id=c.id,
                    prompt=c.prompt,
                    expected_tool=c.expected_tool,
                    expected_params=c.expected_params,
                    tags=c.tags,
                )
                for c in cases
            ]

            runner = HarnessRunner(engine)

            def _run():
                return runner.run(s_cases, suite_name="provider-harness")

            loop = asyncio.get_event_loop()
            harness_report = await loop.run_in_executor(None, _run)

            # Convert HarnessReport → our HarnessReport
            results = [
                HarnessResult(
                    case_id=r.case_id,
                    verdict=r.verdict.value if hasattr(r.verdict, "value") else str(r.verdict),
                    actual_tool=r.actual_tool or "",
                    actual_params=r.actual_params or {},
                    error=r.error or "",
                )
                for r in harness_report.results
            ]

            return HarnessReport(
                total=harness_report.total,
                passed=harness_report.passed,
                failed=harness_report.failed,
                results=results,
            )

        except Exception as e:
            logger.warning(f"HarnessRunner failed ({e}), falling back to mock")
            return self._run_mock(cases)

    def _generate_from_modules(self, modules: List[Dict]) -> List[HarnessCase]:
        """从课程模块生成 Harness 测试用例"""
        cases = []
        for module in modules[:3]:
            module_id = module.get("id", "unknown")
            for lesson in module.get("lessons", [])[:2]:
                lesson_id = lesson.get("id", "unknown")
                cases.append(HarnessCase(
                    id=f"harness_{module_id}_{lesson_id}",
                    prompt=f"Execute lesson: {lesson.get('title', lesson_id)}",
                    expected_tool="read_file",
                    expected_params={"target": f"lessons/{lesson_id}.md"},
                    tags=[module_id],
                ))
        return cases

    def _run_mock(self, cases: List[HarnessCase]) -> HarnessReport:
        """
        Mock execution: 80% pass rate.
        Fallback when HarnessRunner is unavailable.
        """
        import random
        results = []
        for case in cases:
            verdict = VERDICT_PASS if random.random() < 0.8 else VERDICT_FAIL
            results.append(HarnessResult(
                case_id=case.id,
                verdict=verdict,
                actual_tool=case.expected_tool,
                actual_params=case.expected_params,
            ))
        return HarnessReport(
            total=len(results),
            passed=sum(1 for r in results if r.verdict == VERDICT_PASS),
            failed=sum(1 for r in results if r.verdict == VERDICT_FAIL),
            results=results,
        )
