"""
ReviewProvider

结果评审与反馈 Provider。
封装 Curriculum-Forge 的 Trainer 评审逻辑。

对应 TaskPhase.REVIEW。
参考：services/trainer.py 的 TrainerAgent
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


class ReviewProvider(TaskProvider):
    """
    结果评审 Provider。
    
    输入：harness_report + memory_stats（来自前序 Provider）
    输出：feedback + verdict（是否达到目标）
    
    封装 services/trainer.py 的 TrainerAgent 评审逻辑。
    """
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config or ProviderConfig(name="ReviewProvider"))
    
    @property
    def phase(self) -> TaskPhase:
        return TaskPhase.REVIEW
    
    def can_handle(self, config: Dict[str, Any]) -> bool:
        # Review 是最后一个阶段，通常不需要显式 can_handle
        return True
    
    async def execute(
        self,
        config: Dict[str, Any],
        runtime: AdaptiveRuntime,
    ) -> TaskOutput:
        """
        评审训练结果并给出反馈。
        
        综合 Harness 测试结果 + Memory Buffer 统计，
        给出 pass/fail verdict 和改进建议。
        """
        # 提取前序结果
        curriculum_data = runtime._record.state_data.get("curriculum", {})
        harness_data   = runtime._record.state_data.get("harness", {})
        memory_data    = runtime._record.state_data.get("memory", {})
        
        # 评审逻辑
        verdict, feedback = self._judge(
            harness_data=harness_data,
            memory_data=memory_data,
            curriculum_data=curriculum_data,
        )
        
        runtime._record.metrics["review_verdict"] = verdict
        
        return TaskOutput(
            phase=TaskPhase.REVIEW,
            data={
                "status": "ok",
                "verdict": verdict,
                "feedback": feedback,
                "summary": {
                    "harness_pass_rate": harness_data.get("data", {})
                        .get("test_report", {}).get("pass_rate", 0),
                    "memory_hit_rate": memory_data.get("data", {})
                        .get("memory", {}).get("hit_rate", 0),
                },
            },
            metadata={
                "provider": "ReviewProvider",
                "verdict": verdict,
                "has_feedback": bool(feedback),
            },
        )
    
    def _judge(
        self,
        harness_data: Dict,
        memory_data: Dict,
        curriculum_data: Dict,
    ) -> tuple[str, list[str]]:
        """
        综合评审逻辑。
        
        Returns:
            (verdict, feedback_list)
            verdict: "pass" | "partial" | "fail"
        """
        harness_report = harness_data.get("data", {}).get("test_report", {})
        pass_rate = harness_report.get("pass_rate", 0)
        memory_hit = memory_data.get("data", {}).get("memory", {}).get("hit_rate", 0)
        
        feedback = []
        
        # 评分标准（可配置）
        pass_threshold = 0.7
        hit_threshold  = 0.5
        
        if pass_rate >= pass_threshold:
            verdict = "pass"
            feedback.append(f"✅ Harness 通过率 {pass_rate:.1%} 达标（≥{pass_threshold:.0%}）")
        elif pass_rate >= pass_threshold * 0.6:
            verdict = "partial"
            feedback.append(f"⚠️ Harness 通过率 {pass_rate:.1%} 未达标，建议增加训练")
        else:
            verdict = "fail"
            feedback.append(f"❌ Harness 通过率 {pass_rate:.1%} 过低，需要重新设计课程")
        
        if memory_hit >= hit_threshold:
            feedback.append(f"✅ Memory 命中率 {memory_hit:.1%} 良好")
        else:
            feedback.append(f"💡 Memory 命中率 {memory_hit:.1%}，建议增加练习强度")
        
        # 生成改进建议
        if verdict != "pass":
            modules = curriculum_data.get("data", {}).get("curriculum", {}).get("modules", [])
            if modules:
                feedback.append(f"建议复习模块：{modules[0]['title']}（难度 {modules[0]['level']}）")
        
        return verdict, feedback
