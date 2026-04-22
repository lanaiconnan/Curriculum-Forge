"""
HarnessProvider

基于 Agent 的行为验证框架。
封装 services/harness.py 的测试用例执行逻辑。

对应 TaskPhase.HARNESS。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List

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
    输出：test_report（pass/fail/coverage 统计）
    
    封装 services/harness.py 的 HarnessRunner。
    """
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config or ProviderConfig(name="HarnessProvider"))
    
    @property
    def phase(self) -> TaskPhase:
        return TaskPhase.HARNESS
    
    def can_handle(self, config: Dict[str, Any]) -> bool:
        return "modules" in config or "harness_cases" in config
    
    async def execute(
        self,
        config: Dict[str, Any],
        runtime: AdaptiveRuntime,
    ) -> TaskOutput:
        """
        执行 Harness 测试。
        
        当前实现：静态测试用例生成 + 模拟执行。
        TODO: 接入 services/harness.py 的完整 HarnessRunner。
        """
        curriculum = runtime._record.state_data.get("curriculum", {})
        modules = curriculum.get("data", {}).get("curriculum", {}).get("modules", []) \
                 if curriculum else []
        harness_cases = config.get("harness_cases", [])
        
        # 如果 config 没有 harness_cases，从 modules 生成
        if not harness_cases and modules:
            harness_cases = self._generate_from_modules(modules)
        
        # 模拟执行（TODO: 替换为真实 HarnessRunner）
        results = self._run_mock(harness_cases)
        report = self._build_report(results)
        
        runtime._record.metrics["harness_total"] = report.total
        runtime._record.metrics["harness_passed"] = report.passed
        runtime._record.metrics["harness_failed"] = report.failed
        
        return TaskOutput(
            phase=TaskPhase.HARNESS,
            data={
                "status": "ok",
                "test_report": {
                    "total": report.total,
                    "passed": report.passed,
                    "failed": report.failed,
                    "pass_rate": round(report.passed / max(report.total, 1), 3),
                    "results": [
                        {"case_id": r.case_id, "verdict": r.verdict}
                        for r in results
                    ],
                },
            },
            metadata={
                "provider": "HarnessProvider",
                "total_cases": report.total,
                "pass_rate": round(report.passed / max(report.total, 1), 3),
            },
        )
    
    def _generate_from_modules(self, modules: List[Dict]) -> List[HarnessCase]:
        """从课程模块生成 Harness 测试用例"""
        cases = []
        for module in modules[:3]:  # 最多取前3个模块
            for lesson in module.get("lessons", [])[:2]:
                cases.append(HarnessCase(
                    id=f"harness_{module['id']}_{lesson['id']}",
                    prompt=f"Execute lesson: {lesson['title']}",
                    expected_tool="read_file",
                    expected_params={"path": f"lessons/{lesson['id']}.md"},
                    tags=[module["id"]],
                ))
        return cases
    
    def _run_mock(self, cases: List[HarnessCase]) -> List[HarnessResult]:
        """
        模拟 Harness 执行。
        
        TODO: 替换为真实 HarnessRunner 调用
              (from services.harness import HarnessRunner)
        当前按 80% pass rate 随机模拟。
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
        return results
    
    def _build_report(self, results: List[HarnessResult]) -> HarnessReport:
        passed = sum(1 for r in results if r.verdict == VERDICT_PASS)
        failed = sum(1 for r in results if r.verdict == VERDICT_FAIL)
        return HarnessReport(
            total=len(results),
            passed=passed,
            failed=failed,
            results=results,
        )
