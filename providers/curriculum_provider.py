"""
CurriculumProvider

将 Topic/Difficulty 分解为结构化课程模块。
调用 services/environment.py 的 EnvironmentService 生成真实课程环境。
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


class CurriculumProvider(TaskProvider):
    """
    课程设计 Provider。

    输入：topic, difficulty, goal, stage_override
    输出：curriculum（TrainingEnvironment 序列化结果）

    调用链：
        execute() → EnvironmentService.generate_environment()
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig(name="CurriculumProvider"))
        self._env_service = None  # Lazily initialized

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
        runtime: "AdaptiveRuntime",
    ) -> TaskOutput:
        """
        生成课程结构。

        调用 EnvironmentService.generate_environment()：
        1. 从 runtime.service_container 获取 EnvironmentService
        2. 用 ProgressMetrics（初始为空）确定 stage
        3. 生成 TrainingEnvironment → 转为 dict
        """
        topic = config.get("topic", "general")
        difficulty = config.get("difficulty", "beginner")
        goal = config.get("goal", "")
        stage_override = config.get("stage_override")
        max_tasks = config.get("max_tasks", {})

        logger.info(f"CurriculumProvider: topic={topic}, difficulty={difficulty}")

        # Build ProgressMetrics (initial = empty records)
        try:
            from services.models import ProgressMetrics, LearningStage

            metrics = ProgressMetrics.from_records([])

            # Get EnvironmentService from runtime
            env_service = self._get_env_service(runtime)

            if env_service is None:
                # Fallback: static generation
                logger.warning("No EnvironmentService available, using static generation")
                modules = self._generate_modules_static(topic, difficulty, goal)
                curriculum = {
                    "topic": topic,
                    "difficulty": difficulty,
                    "modules": modules,
                    "total_lessons": sum(len(m["lessons"]) for m in modules),
                    "source": "static_fallback",
                }
                ok = True
            else:
                # Real execution: call EnvironmentService
                stage = None
                if stage_override:
                    stage = getattr(LearningStage, stage_override.upper(), None)

                def _generate():
                    return env_service.generate_environment(
                        progress=metrics,
                        override_stage=stage,
                    )

                # Sync call in executor (EnvironmentService is sync)
                loop = asyncio.get_event_loop()
                training_env = await loop.run_in_executor(None, _generate)

                # Convert TrainingEnvironment to curriculum dict
                curriculum = self._env_to_curriculum(training_env)
                curriculum["source"] = "environment_service"

                # Inject max_tasks overrides if provided
                if max_tasks:
                    curriculum["max_tasks"] = max_tasks

                ok = True
                logger.info(
                    f"EnvironmentService generated: env_id={training_env.id}, "
                    f"stage={training_env.stage.value}, tasks={len(training_env.tasks)}"
                )

        except Exception as e:
            logger.error(f"CurriculumProvider failed: {e}")
            curriculum = {
                "topic": topic,
                "difficulty": difficulty,
                "error": str(e),
                "source": "error",
            }
            ok = False

        # Update metrics
        if runtime and runtime._record:
            runtime._record.metrics["curriculum_modules"] = len(curriculum.get("modules", []))
            runtime._record.metrics["curriculum_source"] = curriculum.get("source", "unknown")

        return TaskOutput(
            phase=TaskPhase.CURRICULUM,
            data={
                "status": "ok" if ok else "error",
                "curriculum": curriculum,
            },
            metadata={
                "provider": "CurriculumProvider",
                "module_count": len(curriculum.get("modules", [])),
                "source": curriculum.get("source", "unknown"),
            },
        )

    def _get_env_service(self, runtime: "AdaptiveRuntime") -> Optional[Any]:
        """Get EnvironmentService from runtime's ServiceContainer."""
        if self._env_service is not None:
            return self._env_service

        if runtime is None or runtime.service_container is None:
            return None

        try:
            # Lazy load to avoid import at module level
            from services.environment import EnvironmentService
            self._env_service = runtime.service_container.get(EnvironmentService)
            return self._env_service
        except Exception as e:
            logger.warning(f"Could not get EnvironmentService: {e}")
            return None

    def _env_to_curriculum(self, env: Any) -> Dict[str, Any]:
        """Convert TrainingEnvironment to curriculum dict format."""
        # Convert tasks to module format
        modules = []
        for task in env.tasks:
            modules.append({
                "id": task.id,
                "title": task.description,
                "type": task.type,
                "target": task.target,
                "tools_required": task.tools_required,
                "level": env.difficulty,
            })

        return {
            "env_id": env.id,
            "name": env.name,
            "stage": env.stage.value if hasattr(env.stage, "value") else str(env.stage),
            "difficulty": env.difficulty,
            "modules": modules,
            "total_lessons": len(modules),
            "available_tools": env.available_tools,
            "reward_config": env.reward_config,
            "topic": env.description,
        }

    def _generate_modules_static(
        self,
        topic: str,
        difficulty: str,
        goal: str,
    ) -> List[Dict[str, Any]]:
        """
        Fallback: static curriculum generation.
        Used when EnvironmentService is not available.
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
