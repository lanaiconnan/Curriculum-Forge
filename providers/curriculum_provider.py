"""
CurriculumProvider

将 Topic/Difficulty 分解为结构化课程模块。
封装 services/ 中的课程设计逻辑。

对应 TaskPhase.CURRICULUM。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from providers.base import (
    ProviderConfig,
    ProviderError,
    TaskOutput,
    TaskPhase,
    TaskProvider,
)

if TYPE_CHECKING:
    from runtimes.adaptive_runtime import AdaptiveRuntime


class CurriculumProvider(TaskProvider):
    """
    课程设计 Provider。
    
    输入：topic, difficulty, goal, agent_profile
    输出：curriculum（模块列表、lesson 树、难度曲线）
    
    TODO: 接入现有的 curriculum 设计逻辑。
    计划接入：services/curriculum_generator.py（待创建）
    """
    
    def __init__(self, config: ProviderConfig | None = None):
        super().__init__(config or ProviderConfig(name="CurriculumProvider"))
    
    @property
    def phase(self) -> TaskPhase:
        return TaskPhase.CURRICULUM
    
    def can_handle(self, config: Dict[str, Any]) -> bool:
        return "topic" in config or "curriculum" in config
    
    def validate_config(self, config: Dict[str, Any]) -> None:
        if not config.get("topic"):
            raise ValueError("config.topic is required for CurriculumProvider")
    
    async def execute(
        self,
        config: Dict[str, Any],
        runtime: AdaptiveRuntime,
    ) -> TaskOutput:
        """
        生成课程结构。
        
        当前实现：基于配置的静态生成。
        TODO: 接入 LLM 生成 + services 课程分解器。
        """
        topic = config["topic"]
        difficulty = config.get("difficulty", "beginner")
        goal = config.get("goal", "")
        
        # ── 生成课程模块 ────────────────────────────────────────────────
        modules = self._generate_modules(topic, difficulty, goal)
        
        # ── 更新 metrics ────────────────────────────────────────────────
        runtime._record.metrics["curriculum_modules"] = len(modules)
        
        return TaskOutput(
            phase=TaskPhase.CURRICULUM,
            data={
                "status": "ok",
                "curriculum": {
                    "topic": topic,
                    "difficulty": difficulty,
                    "modules": modules,
                    "total_lessons": sum(len(m["lessons"]) for m in modules),
                },
            },
            metadata={
                "provider": "CurriculumProvider",
                "module_count": len(modules),
            },
        )
    
    def _generate_modules(
        self,
        topic: str,
        difficulty: str,
        goal: str,
    ) -> list[Dict[str, Any]]:
        """
        生成课程模块列表。
        
        难度曲线：beginner→intermediate→advanced→expert
        
        TODO: 替换为 services/curriculum_generator.py 的 LLM 生成逻辑。
        """
        difficulty_map = {
            "beginner":     (1, 3, ["基础概念", "环境搭建", "入门示例"]),
            "intermediate": (2, 4, ["核心特性", "实践项目", "调试技巧"]),
            "advanced":     (3, 5, ["性能优化", "架构设计", "最佳实践"]),
            "expert":       (4, 6, ["前沿技术", "社区贡献", "教学相长"]),
        }
        
        level, module_count, base_titles = difficulty_map.get(
            difficulty, difficulty_map["beginner"]
        )
        
        modules = []
        for i, title in enumerate(base_titles, 1):
            lessons = [
                {
                    "id": f"lesson_{i}_{j}",
                    "title": f"{title} - 知识点 {j}",
                    "type": "concept" if j % 2 == 0 else "exercise",
                    "difficulty_score": level * j,
                }
                for j in range(1, 4)
            ]
            modules.append({
                "id": f"module_{i}",
                "title": title,
                "level": level,
                "lessons": lessons,
                "estimated_hours": level * 2,
            })
        
        return modules
