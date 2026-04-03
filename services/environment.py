"""Environment Generation Service

This service handles Agent A's core responsibility:
- Analyzing experiment progress
- Determining learning stage
- Generating training environments

Based on the service-oriented architecture pattern.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
import logging

from .base import ServiceBase, ServiceConfig, ServiceState
from .models import (
    TrainingEnvironment,
    TaskConfig,
    LearningStage,
    ProgressMetrics,
)
from .container import ServiceProvider

logger = logging.getLogger(__name__)


class EnvironmentServiceConfig(ServiceConfig):
    """Configuration for EnvironmentService"""
    
    def __init__(
        self,
        name: str = "environment",
        workspace: str = ".",
        max_tasks_beginner: int = 2,
        max_tasks_intermediate: int = 3,
        max_tasks_advanced: int = 5,
        **kwargs
    ):
        super().__init__(name=name, **kwargs)
        self.workspace = workspace
        self.max_tasks_beginner = max_tasks_beginner
        self.max_tasks_intermediate = max_tasks_intermediate
        self.max_tasks_advanced = max_tasks_advanced


class EnvironmentService(ServiceBase[EnvironmentServiceConfig]):
    """
    Service for generating training environments.
    
    This is Agent A's core service. It:
    1. Analyzes progress from results.tsv
    2. Determines the current learning stage
    3. Generates appropriate training environments
    
    Usage:
        provider = ServiceProvider()
        provider.configure(EnvironmentService, config)
        provider.start()
        
        env_service = provider.get(EnvironmentService)
        env = env_service.generate_environment(progress)
    """
    
    def __init__(self, config: EnvironmentServiceConfig):
        super().__init__(config)
        self._task_templates: Dict[LearningStage, List[Dict]] = {}
        self._stage_thresholds = {
            LearningStage.BEGINNER: (0.0, 0.3),
            LearningStage.INTERMEDIATE: (0.3, 0.6),
            LearningStage.ADVANCED: (0.6, 1.0),
        }
    
    def initialize(self) -> None:
        """Initialize the service"""
        logger.info(f"Initializing EnvironmentService in {self.config.workspace}")
        self._load_task_templates()
    
    def start(self) -> None:
        """Start the service"""
        logger.info("EnvironmentService started")
    
    def stop(self) -> None:
        """Stop the service"""
        logger.info("EnvironmentService stopped")
    
    def _load_task_templates(self) -> None:
        """Load task templates for each stage"""
        self._task_templates = {
            LearningStage.BEGINNER: [
                {
                    "id": "b1",
                    "type": "optimize",
                    "description": "Simple optimization task",
                    "target": "score > 100",
                    "tools_required": ["git"],
                },
                {
                    "id": "b2",
                    "type": "refactor",
                    "description": "Simple refactoring task",
                    "target": "score > 80",
                    "tools_required": ["git"],
                },
            ],
            LearningStage.INTERMEDIATE: [
                {
                    "id": "i1",
                    "type": "optimize",
                    "description": "Multi-step optimization",
                    "target": "score > 200",
                    "tools_required": ["git", "shell"],
                },
                {
                    "id": "i2",
                    "type": "test",
                    "description": "Add test coverage",
                    "target": "coverage > 80%",
                    "tools_required": ["git", "shell"],
                },
                {
                    "id": "i3",
                    "type": "debug",
                    "description": "Fix reported bug",
                    "target": "all tests pass",
                    "tools_required": ["git", "shell", "grep"],
                },
            ],
            LearningStage.ADVANCED: [
                {
                    "id": "a1",
                    "type": "optimize",
                    "description": "Complex performance optimization",
                    "target": "speed up 2x",
                    "tools_required": ["git", "shell", "grep", "bench"],
                },
                {
                    "id": "a2",
                    "type": "refactor",
                    "description": "Architecture refactoring",
                    "target": "maintain all tests",
                    "tools_required": ["git", "shell"],
                },
                {
                    "id": "a3",
                    "type": "debug",
                    "description": "Debug race condition",
                    "target": "no race detected",
                    "tools_required": ["git", "shell", "debug"],
                },
                {
                    "id": "a4",
                    "type": "security",
                    "description": "Security audit",
                    "target": "no vulnerabilities",
                    "tools_required": ["git", "shell", "audit"],
                },
                {
                    "id": "a5",
                    "type": "integration",
                    "description": "Integrate external API",
                    "target": "all endpoints work",
                    "tools_required": ["git", "shell", "api"],
                },
            ],
        }
    
    def determine_stage(self, progress: ProgressMetrics) -> LearningStage:
        """
        Determine learning stage from progress metrics.
        
        Args:
            progress: Aggregated progress metrics
        
        Returns:
            Current learning stage
        """
        keep_rate = progress.keep_rate
        
        for stage, (low, high) in self._stage_thresholds.items():
            if low <= keep_rate < high:
                return stage
        
        return LearningStage.ADVANCED
    
    def get_difficulty(self, stage: LearningStage) -> float:
        """Get difficulty level for a stage"""
        difficulties = {
            LearningStage.BEGINNER: 0.3,
            LearningStage.INTERMEDIATE: 0.5,
            LearningStage.ADVANCED: 0.7,
        }
        return difficulties.get(stage, 0.5)
    
    def get_reward_scale(self, stage: LearningStage) -> float:
        """Get reward scale for a stage"""
        scales = {
            LearningStage.BEGINNER: 1.0,
            LearningStage.INTERMEDIATE: 0.7,
            LearningStage.ADVANCED: 0.5,
        }
        return scales.get(stage, 0.7)
    
    def _create_tasks(self, stage: LearningStage) -> List[TaskConfig]:
        """Create task configs from templates"""
        templates = self._task_templates.get(stage, [])
        
        max_tasks = {
            LearningStage.BEGINNER: self.config.max_tasks_beginner,
            LearningStage.INTERMEDIATE: self.config.max_tasks_intermediate,
            LearningStage.ADVANCED: self.config.max_tasks_advanced,
        }[stage]
        
        tasks = []
        for i, tmpl in enumerate(templates[:max_tasks]):
            tasks.append(TaskConfig(
                id=f"{tmpl['id']}_{datetime.now().strftime('%H%M%S')}",
                type=tmpl["type"],
                description=tmpl["description"],
                target=tmpl["target"],
                tools_required=tmpl.get("tools_required", []),
            ))
        
        return tasks
    
    def generate_environment(
        self,
        progress: ProgressMetrics,
        override_stage: Optional[LearningStage] = None,
    ) -> TrainingEnvironment:
        """
        Generate a training environment based on progress.
        
        This is the main entry point for environment generation.
        
        Args:
            progress: Current progress metrics
            override_stage: Optional stage override
        
        Returns:
            Configured training environment
        """
        # Determine stage
        stage = override_stage or self.determine_stage(progress)
        difficulty = self.get_difficulty(stage)
        reward_scale = self.get_reward_scale(stage)
        
        # Create tasks
        tasks = self._create_tasks(stage)
        
        # Determine available tools
        available_tools = ["git", "shell"]
        if stage == LearningStage.INTERMEDIATE:
            available_tools.append("grep")
        elif stage == LearningStage.ADVANCED:
            available_tools.extend(["grep", "bench", "debug", "audit", "api"])
        
        # Create environment
        env = TrainingEnvironment(
            id=f"env_{stage.value}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            name=f"{stage.value.capitalize()} Environment",
            description=f"Training environment for {stage.value} stage",
            stage=stage,
            difficulty=difficulty,
            tasks=tasks,
            available_tools=available_tools,
            reward_config={"scale": reward_scale},
        )
        
        logger.info(f"Generated environment: {env.id} (stage={stage.value}, difficulty={difficulty})")
        
        return env
    
    def adjust_environment(
        self,
        env: TrainingEnvironment,
        feedback: ProgressMetrics,
    ) -> TrainingEnvironment:
        """
        Adjust an existing environment based on feedback.
        
        Args:
            env: Current environment
            feedback: Latest progress metrics
        
        Returns:
            Adjusted environment
        """
        keep_rate = feedback.keep_rate
        
        # Adjust difficulty based on performance
        if keep_rate < 0.3:
            # Too hard, reduce difficulty
            env.difficulty *= 0.8
            env.reward_config["scale"] = min(1.5, env.reward_config.get("scale", 1.0) * 1.2)
        elif keep_rate > 0.6:
            # Too easy, increase difficulty
            env.difficulty = min(1.0, env.difficulty * 1.2)
            env.reward_config["scale"] = max(0.3, env.reward_config.get("scale", 1.0) * 0.8)
        
        # Determine new stage
        new_stage = self.determine_stage(feedback)
        if new_stage != env.stage:
            logger.info(f"Stage transition: {env.stage.value} -> {new_stage.value}")
            env.stage = new_stage
            env.tasks = self._create_tasks(new_stage)
        
        return env
