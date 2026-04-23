"""
ReviewProvider

结果评审与反馈 Provider。
调用 services/learner.py 的 ProgressMetrics + services/dual_agent.py 的评审阈值。
"""

from __future__ import annotations

import asyncio
import logging
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


class ReviewProvider(TaskProvider):
    """
    结果评审 Provider。

    输入：harness_report + memory_stats（来自前序 Provider）
    输出：verdict + feedback（是否达到目标）

    调用链：
        execute() → LearnerService.get_progress() → DualAgentCoordinator 阈值判断

    阈值（与 services/dual_agent.py 保持一致）：
        keep_rate < 0.3  → reject (verdict="fail")
        0.3 ≤ kr < 0.6  → revise (verdict="partial")
        keep_rate ≥ 0.6  → accept (verdict="pass")
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig(name="ReviewProvider"))
        # Threshold overrides (None = use defaults)
        self._accept_threshold = config.accept_threshold if hasattr(config, 'accept_threshold') else None
        self._revise_threshold = config.revise_threshold if hasattr(config, 'revise_threshold') else None

    @property
    def phase(self) -> TaskPhase:
        return TaskPhase.REVIEW

    def can_handle(self, config: Dict[str, Any]) -> bool:
        # Review is the final phase; always handles
        return True

    async def execute(
        self,
        config: Dict[str, Any],
        runtime: "AdaptiveRuntime",
    ) -> TaskOutput:
        """
        评审训练结果并给出反馈。

        1. 从 LearnerService 获取 ProgressMetrics（包含真实 keep_rate）
        2. 用 dual_agent 阈值判断 verdict
        3. 生成改进建议
        """
        # Extract prior phase outputs
        harness_data = {}
        memory_data = {}
        curriculum_data = {}

        if runtime and runtime._record and runtime._record.state_data:
            harness_data = runtime._record.state_data.get("harness", {})
            memory_data = runtime._record.state_data.get("memory", {})
            curriculum_data = runtime._record.state_data.get("curriculum", {})

        # Get real ProgressMetrics from LearnerService
        keep_rate, avg_reward, total_experiments = await self._get_progress_metrics(runtime)

        harness_report = harness_data.get("data", {}) if harness_data else {}
        test_report = harness_report.get("test_report", {})
        pass_rate = test_report.get("pass_rate", 0.0)

        memory_stats = memory_data.get("data", {}).get("memory", {}) if memory_data else {}
        memory_hit_rate = memory_stats.get("hit_rate", 0.0)

        # Judge using dual_agent thresholds
        verdict, feedback = self._judge(
            keep_rate=keep_rate,
            harness_pass_rate=pass_rate,
            memory_hit_rate=memory_hit_rate,
            harness_data=harness_data,
            memory_data=memory_data,
            curriculum_data=curriculum_data,
        )

        logger.info(
            f"ReviewProvider: verdict={verdict}, keep_rate={keep_rate:.3f}, "
            f"harness_pass={pass_rate:.3f}, memory_hit={memory_hit_rate:.3f}"
        )

        # Update metrics
        if runtime and runtime._record:
            runtime._record.metrics["review_verdict"] = verdict
            runtime._record.metrics["keep_rate"] = keep_rate
            runtime._record.metrics["avg_reward"] = avg_reward

        return TaskOutput(
            phase=TaskPhase.REVIEW,
            data={
                "status": "ok",
                "verdict": verdict,
                "feedback": feedback,
                "summary": {
                    "keep_rate": round(keep_rate, 4),
                    "avg_reward": round(avg_reward, 4),
                    "harness_pass_rate": round(pass_rate, 4),
                    "memory_hit_rate": round(memory_hit_rate, 4),
                    "total_experiments": total_experiments,
                },
            },
            metadata={
                "provider": "ReviewProvider",
                "verdict": verdict,
                "has_feedback": bool(feedback),
                "keep_rate": round(keep_rate, 4),
            },
        )

    async def _get_progress_metrics(
        self,
        runtime: "AdaptiveRuntime",
    ) -> tuple:
        """
        Get ProgressMetrics from LearnerService.

        Returns:
            (keep_rate, avg_reward, total_experiments)
        """
        if runtime is None or runtime.service_container is None:
            # Fallback: try to get from memory_data
            return (0.0, 0.0, 0)

        try:
            from services.learner import LearnerService
            learner = runtime.service_container.get(LearnerService)

            def _get():
                return learner.get_progress(), learner.get_results()

            loop = asyncio.get_event_loop()
            metrics, results = await loop.run_in_executor(None, _get)

            keep_rate = metrics.keep_rate if hasattr(metrics, 'keep_rate') else 0.0
            avg_reward = metrics.avg_reward if hasattr(metrics, 'avg_reward') else 0.0
            total = len(results)

            return keep_rate, avg_reward, total

        except Exception as e:
            logger.warning(f"Could not get LearnerService metrics: {e}")
            return (0.0, 0.0, 0)

    def _judge(
        self,
        keep_rate: float,
        harness_pass_rate: float,
        memory_hit_rate: float,
        harness_data: Dict,
        memory_data: Dict,
        curriculum_data: Dict,
    ) -> tuple:
        """
        综合评审逻辑。

        Thresholds (aligned with services/dual_agent.py):
            keep_rate < 0.3   → "fail" (reject)
            0.3 ≤ kr < 0.6   → "partial" (revise)
            keep_rate ≥ 0.6   → "pass" (accept)

        Returns:
            (verdict, feedback_list)
        """
        # Use dual_agent thresholds
        accept_threshold = self._accept_threshold if self._accept_threshold is not None else 0.6
        revise_threshold = self._revise_threshold if self._revise_threshold is not None else 0.3

        feedback: List[str] = []

        # Primary: keep_rate based verdict (from LearnerService experiments)
        if keep_rate > 0:
            if keep_rate >= accept_threshold:
                verdict = "pass"
                feedback.append(f"✅ Keep rate {keep_rate:.1%} ≥ {accept_threshold:.0%}，验收通过")
            elif keep_rate >= revise_threshold:
                verdict = "partial"
                feedback.append(f"⚠️ Keep rate {keep_rate:.1%}，需要调整（{revise_threshold:.0%}≤kr<{accept_threshold:.0%}）")
            else:
                verdict = "fail"
                feedback.append(f"❌ Keep rate {keep_rate:.1%} < {revise_threshold:.0%}，需要重新设计课程")
        else:
            # No experiment data yet — fall back to harness pass rate
            pass_threshold = 0.7
            hit_threshold = 0.5

            if harness_pass_rate >= pass_threshold:
                verdict = "pass"
                feedback.append(f"✅ Harness 通过率 {harness_pass_rate:.1%} ≥ {pass_threshold:.0%}，初步验收")
            elif harness_pass_rate >= pass_threshold * 0.6:
                verdict = "partial"
                feedback.append(f"⚠️ Harness 通过率 {harness_pass_rate:.1%}，建议增加练习")
            else:
                verdict = "fail"
                feedback.append(f"❌ Harness 通过率 {harness_pass_rate:.1%}，需要重新设计课程")

        # Secondary: memory hit rate
        if memory_hit_rate >= 0.5:
            feedback.append(f"✅ Memory 命中率 {memory_hit_rate:.1%} 良好")
        elif memory_hit_rate > 0:
            feedback.append(f"💡 Memory 命中率 {memory_hit_rate:.1%}，建议加强经验复用")
        # If 0, skip memory check (no data yet)

        # Harness-specific feedback
        harness_report = harness_data.get("data", {}) if harness_data else {}
        test_report = harness_report.get("test_report", {})
        total = test_report.get("total", 0)
        passed = test_report.get("passed", 0)
        if total > 0:
            feedback.append(f"📋 Harness: {passed}/{total} 测试用例通过")

        # Improvement suggestions
        if verdict != "pass":
            modules = curriculum_data.get("data", {}).get("curriculum", {}).get("modules", []) \
                     if curriculum_data else []
            if modules:
                first = modules[0]
                feedback.append(
                    f"💡 建议复习：{first.get('title', '第一模块')}"
                    f"（难度 {first.get('difficulty', first.get('level', '?'))}）"
                )

        return verdict, feedback
