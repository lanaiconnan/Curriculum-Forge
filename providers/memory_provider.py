"""
MemoryProvider

经验存储与检索 Provider。
封装 Curriculum-Forge 的 Experience Buffer 逻辑。

对应 TaskPhase.MEMORY。
参考：services/learner.py 的 ExperienceBuffer
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from providers.base import (
    ProviderConfig,
    TaskOutput,
    TaskPhase,
    TaskProvider,
)

if TYPE_CHECKING:
    from runtimes.adaptive_runtime import AdaptiveRuntime


class MemoryProvider(TaskProvider):
    """
    经验存储 Provider。
    
    输入：experiences（来自 Harness + Review）
    输出：buffer_stats（buffer 大小、命中率、检索结果）
    
    封装 services/learner.py 的 ExperienceBuffer。
    """
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config or ProviderConfig(name="MemoryProvider"))
        self._buffer: Dict[str, Any] = {}
    
    @property
    def phase(self) -> TaskPhase:
        return TaskPhase.MEMORY
    
    def can_handle(self, config: Dict[str, Any]) -> bool:
        return "experiences" in config or "memory" in config
    
    async def execute(
        self,
        config: Dict[str, Any],
        runtime: AdaptiveRuntime,
    ) -> TaskOutput:
        """
        存储经验到 Experience Buffer。
        
        从前序 Provider（Harness/Review）提取结果，
        存入 buffer 并计算统计指标。
        """
        # 提取经验数据
        harness_data = runtime._record.state_data.get("harness", {})
        review_data = runtime._record.state_data.get("review", {})
        
        experiences = config.get("experiences", [])
        experiences.extend(self._extract_from_harness(harness_data))
        experiences.extend(self._extract_from_review(review_data))
        
        # 存储
        self._store_experiences(experiences)
        
        stats = self._compute_stats(experiences)
        
        runtime._record.metrics["memory_experiences"] = len(experiences)
        runtime._record.metrics["memory_hit_rate"] = stats["hit_rate"]
        
        return TaskOutput(
            phase=TaskPhase.MEMORY,
            data={
                "status": "ok",
                "memory": {
                    "buffer_size": stats["buffer_size"],
                    "experiences_stored": len(experiences),
                    "hit_rate": stats["hit_rate"],
                    "top_tags": stats["top_tags"],
                },
            },
            metadata={
                "provider": "MemoryProvider",
                "buffer_size": stats["buffer_size"],
            },
        )
    
    def _extract_from_harness(self, harness_data: Dict) -> list[Dict]:
        """从 Harness 结果提取经验"""
        if not harness_data:
            return []
        report = harness_data.get("data", {}).get("test_report", {})
        results = report.get("results", [])
        return [
            {
                "type": "harness_pass" if r["verdict"] == "pass" else "harness_fail",
                "case_id": r["case_id"],
                "data": r,
            }
            for r in results
        ]
    
    def _extract_from_review(self, review_data: Dict) -> list[Dict]:
        """从 Review 结果提取经验"""
        if not review_data:
            return []
        verdicts = review_data.get("data", {}).get("verdicts", [])
        return [
            {"type": "review_verdict", "verdict": v.get("verdict"), "data": v}
            for v in verdicts
        ]
    
    def _store_experiences(self, experiences: list[Dict]) -> None:
        """存储经验到 buffer（内存）"""
        for exp in experiences:
            key = f"{exp['type']}:{exp.get('case_id', id(exp))}"
            self._buffer[key] = exp
    
    def _compute_stats(self, experiences: list[Dict]) -> Dict[str, Any]:
        """计算 buffer 统计"""
        tag_counts: Dict[str, int] = {}
        for exp in experiences:
            t = exp["type"]
            tag_counts[t] = tag_counts.get(t, 0) + 1
        
        total = len(experiences)
        hits = sum(1 for e in experiences if e["type"] == "harness_pass")
        
        return {
            "buffer_size": len(self._buffer),
            "experiences_stored": total,
            "hit_rate": round(hits / max(total, 1), 3),
            "top_tags": sorted(tag_counts.items(), key=lambda x: -x[1])[:5],
        }
