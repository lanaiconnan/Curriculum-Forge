"""
MemoryProvider

经验存储与检索 Provider。
调用 services/learner.py 的 LearnerService 经验 buffer。
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


class MemoryProvider(TaskProvider):
    """
    经验存储 Provider。

    输入：experiences（来自 Harness + Review）
    输出：buffer_stats + ProgressMetrics

    调用链：
        execute() → LearnerService.get_results() + get_progress()
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig(name="MemoryProvider"))
        self._learner_service = None  # Lazily initialized
        self._local_buffer: Dict[str, Any] = {}  # Fallback storage

    @property
    def phase(self) -> TaskPhase:
        return TaskPhase.MEMORY

    def can_handle(self, config: Dict[str, Any]) -> bool:
        return "experiences" in config or "memory" in config

    async def execute(
        self,
        config: Dict[str, Any],
        runtime: "AdaptiveRuntime",
    ) -> TaskOutput:
        """
        存储经验到 Experience Buffer 并计算统计。

        1. 从 runtime.service_container 获取 LearnerService
        2. 提取前序 Provider 结果 → 存入 LearnerService buffer
        3. 调用 get_progress() → ProgressMetrics
        4. 返回 buffer 统计
        """
        # Extract experiences from prior phases
        experiences = self._extract_experiences(runtime)
        extra_experiences = config.get("experiences", [])
        experiences.extend(extra_experiences)

        learner_service = self._get_learner_service(runtime)

        if learner_service is not None:
            # Real execution: use LearnerService buffer
            progress = await self._execute_with_service(learner_service, experiences)
            source = "learner_service"
        else:
            # Fallback: local buffer
            progress = self._execute_with_local_buffer(experiences)
            source = "local_buffer"
            logger.warning("No LearnerService available, using local buffer")

        # Update metrics
        if runtime and runtime._record:
            runtime._record.metrics["memory_experiences"] = len(experiences)
            runtime._record.metrics["memory_hit_rate"] = progress.get("hit_rate", 0.0)

        return TaskOutput(
            phase=TaskPhase.MEMORY,
            data={
                "status": "ok",
                "memory": {
                    "experiences_stored": len(experiences),
                    "buffer_size": progress.get("buffer_size", 0),
                    "hit_rate": progress.get("hit_rate", 0.0),
                    "keep_rate": progress.get("keep_rate", 0.0),
                    "avg_reward": progress.get("avg_reward", 0.0),
                    "total_records": progress.get("total_records", 0),
                    "top_tags": progress.get("top_tags", []),
                },
            },
            metadata={
                "provider": "MemoryProvider",
                "buffer_size": progress.get("buffer_size", 0),
                "source": source,
            },
        )

    def _get_learner_service(self, runtime: "AdaptiveRuntime") -> Optional[Any]:
        """Get LearnerService from runtime's ServiceContainer."""
        if self._learner_service is not None:
            return self._learner_service

        if runtime is None or runtime.service_container is None:
            return None

        try:
            from services.learner import LearnerService
            self._learner_service = runtime.service_container.get(LearnerService)
            return self._learner_service
        except Exception as e:
            logger.warning(f"Could not get LearnerService: {e}")
            return None

    def _extract_experiences(self, runtime: "AdaptiveRuntime") -> List[Dict[str, Any]]:
        """Extract experiences from prior phase outputs."""
        experiences = []

        if runtime is None or runtime._record is None:
            return experiences

        state_data = runtime._record.state_data

        # From harness phase
        harness_data = state_data.get("harness", {})
        if harness_data and isinstance(harness_data, dict):
            report = harness_data.get("data", {}).get("test_report", {})
            results = report.get("results", [])
            for r in results:
                experiences.append({
                    "type": "harness_pass" if r.get("verdict") == "pass" else "harness_fail",
                    "case_id": r.get("case_id", "unknown"),
                    "data": r,
                })

        # From review phase
        review_data = state_data.get("review", {})
        if review_data and isinstance(review_data, dict):
            verdicts = review_data.get("data", {}).get("verdicts", [])
            for v in verdicts:
                experiences.append({
                    "type": "review_verdict",
                    "verdict": v.get("verdict"),
                    "data": v,
                })

        return experiences

    async def _execute_with_service(
        self,
        learner_service: Any,
        experiences: List[Dict],
    ) -> Dict[str, Any]:
        """Use LearnerService for real experience tracking."""
        try:
            from services.models import ProgressMetrics

            # Get progress from LearnerService
            def _get_progress():
                return learner_service.get_progress()

            loop = asyncio.get_event_loop()
            metrics = await loop.run_in_executor(None, _get_progress)

            # Compute hit_rate from records
            records = learner_service.get_results()
            total = len(records)
            hits = sum(1 for r in records if hasattr(r, 'status') and r.status.value == "keep")

            # Extract tags from records
            tag_counts: Dict[str, int] = {}
            for r in records:
                stage = r.stage.value if hasattr(r.stage, 'value') else str(r.stage)
                tag_counts[stage] = tag_counts.get(stage, 0) + 1

            top_tags = sorted(tag_counts.items(), key=lambda x: -x[1])[:5]

            return {
                "buffer_size": total,
                "experiences_stored": len(experiences),
                "hit_rate": round(hits / max(total, 1), 3),
                "keep_rate": round(metrics.keep_rate, 3) if hasattr(metrics, 'keep_rate') else 0.0,
                "avg_reward": round(metrics.avg_reward, 3) if hasattr(metrics, 'avg_reward') else 0.0,
                "total_records": total,
                "top_tags": top_tags,
            }

        except Exception as e:
            logger.warning(f"LearnerService progress query failed: {e}")
            return self._execute_with_local_buffer(experiences)

    def _execute_with_local_buffer(self, experiences: List[Dict]) -> Dict[str, Any]:
        """Fallback: use local in-memory buffer."""
        for exp in experiences:
            key = f"{exp['type']}:{exp.get('case_id', id(exp))}"
            self._local_buffer[key] = exp

        tag_counts: Dict[str, int] = {}
        for exp in experiences:
            t = exp["type"]
            tag_counts[t] = tag_counts.get(t, 0) + 1

        total = len(experiences)
        hits = sum(1 for e in experiences if e["type"] == "harness_pass")

        return {
            "buffer_size": len(self._local_buffer),
            "experiences_stored": total,
            "hit_rate": round(hits / max(total, 1), 3),
            "keep_rate": round(hits / max(total, 1), 3),
            "avg_reward": 0.0,
            "total_records": total,
            "top_tags": sorted(tag_counts.items(), key=lambda x: -x[1])[:5],
        }
