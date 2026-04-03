"""Dual-Agent Coordinator

Specialized coordinator for Curriculum-Forge's dual-agent architecture.
Integrates with existing services (EnvironmentService, LearnerService, RLTrainerService).

Architecture:
    
    ┌─────────────────────────────────────────────────────┐
    │              DualAgentCoordinator                    │
    │                                                      │
    │  ┌─────────┐    ┌─────────┐    ┌─────────┐         │
    │  │ Agent A │───▶│  Queue  │───▶│ Agent B │         │
    │  │(Producer)│    │(Tasks)  │    │(Executor)│         │
    │  └────┬────┘    └────┬────┘    └────┬────┘         │
    │       │              │              │               │
    │       │         ┌────▼────┐         │               │
    │       │         │ Review  │◀────────┘               │
    │       └────────▶│ (A+B)   │                         │
    │              └────┬────┘                            │
    │                   │                                 │
    │              ┌────▼────┐                            │
    │              │   RL    │                            │
    │              │ Trainer │                            │
    │              └─────────┘                            │
    └─────────────────────────────────────────────────────┘

Flow:
    1. Agent A (Producer) generates environments
    2. Tasks queued for Agent B (Executor)
    3. Agent B runs experiments
    4. Results reviewed (by Agent A or heuristic)
    5. RL Trainer updates model with GRPO
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime
import logging
import time

from .coordinator import (
    Coordinator,
    Task,
    TaskStatus,
    Workflow,
    AgentInfo,
    AgentRole,
    Message,
)
from .models import (
    TrainingEnvironment,
    ExperimentRecord,
    ProgressMetrics,
    LearningStage,
)
from .environment import EnvironmentService
from .learner import LearnerService
from .trainer import RLTrainerService
from .plugin_system import PluginManager, PluginContext

logger = logging.getLogger(__name__)


@dataclass
class DualAgentConfig:
    """Configuration for DualAgentCoordinator"""
    max_iterations: int = 10
    max_rounds_per_episode: int = 3
    review_timeout: float = 60.0
    training_timeout: float = 300.0
    
    # Stage transition thresholds
    beginner_threshold: float = 0.3
    advanced_threshold: float = 0.6
    
    # Parallel execution
    parallel_experiments: int = 1  # Number of experiments to run in parallel


@dataclass
class EpisodeResult:
    """Result of a dual-agent training episode"""
    episode_id: str
    stage: str
    environment_id: str
    tasks_completed: int
    tasks_failed: int
    total_reward: float
    keep_rate: float
    
    review_verdict: str  # "accept", "revise", "reject"
    review_rounds: int
    
    grpo_advantage: float
    training_loss: float
    
    duration: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class DualAgentCoordinator:
    """
    Specialized coordinator for dual-agent training.
    
    This class orchestrates the interaction between:
    - EnvironmentService (Agent A / Producer)
    - LearnerService (Agent B / Executor)
    - RLTrainerService (GRPO training)
    
    Usage:
        from services import (
            ServiceProvider,
            EnvironmentService,
            LearnerService,
            RLTrainerService,
        )
        
        # Setup services
        provider = ServiceProvider()
        provider.configure(EnvironmentService, env_config)
        provider.configure(LearnerService, learner_config)
        provider.configure(RLTrainerService, rl_config)
        provider.start()
        
        # Create coordinator
        coordinator = DualAgentCoordinator(
            env_service=provider.get(EnvironmentService),
            learner_service=provider.get(LearnerService),
            trainer_service=provider.get(RLTrainerService),
            config=DualAgentConfig(max_iterations=10),
        )
        
        # Run training
        results = coordinator.run_training(episodes=10)
        
        provider.stop()
    """
    
    def __init__(
        self,
        env_service: EnvironmentService,
        learner_service: LearnerService,
        trainer_service: RLTrainerService,
        config: Optional[DualAgentConfig] = None,
        plugin_manager: Optional[PluginManager] = None,
    ):
        self.env_service = env_service
        self.learner_service = learner_service
        self.trainer_service = trainer_service
        self.config = config or DualAgentConfig()
        self.plugins = plugin_manager or PluginManager()
        
        # Internal coordinator for task management
        self._coordinator = Coordinator()
        
        # Register agents
        self._coordinator.register_agent(AgentInfo(
            id="agent_a",
            name="Environment Generator",
            role=AgentRole.PRODUCER,
            capabilities=["generate", "analyze", "review"],
        ))
        
        self._coordinator.register_agent(AgentInfo(
            id="agent_b",
            name="Experiment Runner",
            role=AgentRole.EXECUTOR,
            capabilities=["execute", "train", "collect"],
        ))
        
        # Register task handlers
        self._coordinator.register_handler("environment", self._handle_environment_task)
        self._coordinator.register_handler("experiment", self._handle_experiment_task)
        self._coordinator.register_handler("review", self._handle_review_task)
        self._coordinator.register_handler("training", self._handle_training_task)
        
        # State
        self._progress = ProgressMetrics()
        self._current_env: Optional[TrainingEnvironment] = None
        self._episode_count = 0
        self._results: List[EpisodeResult] = []
        
        # Callbacks
        self._on_episode_complete: Optional[Callable[[EpisodeResult], None]] = None
    
    def set_callbacks(self, on_episode_complete: Optional[Callable[[EpisodeResult], None]] = None) -> None:
        """Set event callbacks"""
        self._on_episode_complete = on_episode_complete
    
    def _determine_stage(self, keep_rate: float) -> LearningStage:
        """Determine learning stage from keep rate"""
        if keep_rate < self.config.beginner_threshold:
            return LearningStage.BEGINNER
        elif keep_rate < self.config.advanced_threshold:
            return LearningStage.INTERMEDIATE
        else:
            return LearningStage.ADVANCED
    
    def _handle_environment_task(self, task: Task) -> Dict[str, Any]:
        """Handle environment generation task"""
        stage_str = task.payload.get("stage", "beginner")
        stage = LearningStage(stage_str) if isinstance(stage_str, str) else stage_str
        
        # Plugin hook: before generate
        ctx = self.plugins.dispatch("env:before_generate", {
            "stage": stage_str,
            "progress": self._progress.to_dict(),
        })
        
        # Generate environment
        env = self.env_service.generate_environment(self._progress)
        self._current_env = env
        
        # Plugin hook: after generate
        self.plugins.dispatch("env:after_generate", {
            "env_id": env.id,
            "stage": env.stage.value,
            "difficulty": env.difficulty,
        })
        
        return {
            "env_id": env.id,
            "env_name": env.name,
            "stage": env.stage.value,
            "difficulty": env.difficulty,
            "task_count": env.task_count,
        }
    
    def _handle_experiment_task(self, task: Task) -> Dict[str, Any]:
        """Handle experiment execution task"""
        if not self._current_env:
            return {"error": "No environment generated"}
        
        # Plugin hook: before run
        ctx = self.plugins.dispatch("exp:before_run", {
            "env": self._current_env,
            "stage": self._current_env.stage.value,
        })
        if ctx.get('skip'):
            logger.info(f"Experiment skipped by plugin: {ctx.get('skip_reason')}")
            return {"experiments": 0, "keep_count": 0, "keep_rate": 0.0, "total_reward": 0.0, "records": []}
        
        # Run experiments
        max_iterations = task.payload.get("max_iterations", self.config.max_iterations)
        records = self.learner_service.run_experiments(
            self._current_env,
            max_iterations=max_iterations,
        )
        
        keep_count = sum(1 for r in records if r.is_keep)
        keep_rate = keep_count / len(records) if records else 0.0
        total_reward = sum(r.reward for r in records)
        
        # Plugin hook: after run
        self.plugins.dispatch("exp:after_run", {
            "exp_id": f"ep_{self._episode_count}",
            "stage": self._current_env.stage.value,
            "keep_rate": keep_rate,
            "total_reward": total_reward,
            "experiments": len(records),
        })
        
        # Check for stage transition
        old_stage = self._progress.current_stage.value if self._progress.total_experiments > 0 else None
        self._progress = ProgressMetrics.from_records(records)
        new_stage = self._progress.current_stage.value
        
        if old_stage and old_stage != new_stage:
            self.plugins.dispatch("stage:before_transition", {
                "from_stage": old_stage,
                "to_stage": new_stage,
                "keep_rate": keep_rate,
            })
            self.plugins.dispatch("stage:after_transition", {
                "from_stage": old_stage,
                "to_stage": new_stage,
                "keep_rate": keep_rate,
            })
        
        return {
            "experiments": len(records),
            "keep_count": keep_count,
            "keep_rate": keep_rate,
            "total_reward": total_reward,
            "records": [r.to_dict() for r in records],
        }
    
    def _handle_review_task(self, task: Task) -> Dict[str, Any]:
        """Handle review task (Producer-Reviewer pattern)"""
        experiment_result = task.payload.get("experiment_result", {})
        round_num = task.payload.get("round", 1)
        
        # Simple heuristic review
        keep_rate = experiment_result.get("keep_rate", 0.0)
        
        if keep_rate >= 0.6:
            verdict = "accept"
            score = 1.0
        elif keep_rate >= 0.3:
            verdict = "revise"
            score = 0.5
        else:
            verdict = "reject"
            score = 0.0
        
        # Calculate reward for review
        reward = score * self.env_service.get_reward_scale(
            self._determine_stage(keep_rate)
        )
        
        return {
            "verdict": verdict,
            "score": score,
            "reward": reward,
            "round": round_num,
        }
    
    def _handle_training_task(self, task: Task) -> Dict[str, Any]:
        """Handle RL training task"""
        rewards = task.payload.get("rewards", [])
        
        # GRPO training
        from .trainer import Experience
        
        experiences = [
            Experience(
                state={"round": i},
                action={},
                reward=r,
                next_state={},
                done=(i == len(rewards) - 1),
            )
            for i, r in enumerate(rewards)
        ]
        
        stats = self.trainer_service.train_step(experiences)
        
        return {
            "total_reward": stats.total_reward,
            "avg_reward": stats.avg_reward,
            "experiences": stats.experiences,
            "grpo_advantage": stats.grpo_advantage,
            "policy_loss": stats.policy_loss,
        }
    
    def run_episode(
        self,
        stage: Optional[str] = None,
        objectives: Optional[List[str]] = None,
    ) -> EpisodeResult:
        """
        Run a single training episode.
        
        This is the core training loop:
        1. Generate environment (Agent A)
        2. Run experiments (Agent B)
        3. Review results
        4. Train with GRPO
        5. Update progress
        
        Args:
            stage: Override learning stage
            objectives: Optional objectives for the episode
        
        Returns:
            EpisodeResult with all metrics
        """
        self._episode_count += 1
        episode_id = f"ep_{self._episode_count:04d}"
        
        start_time = time.time()
        
        # Determine stage
        current_stage = stage or self._determine_stage(self._progress.keep_rate).value
        
        # Create workflow
        workflow = self._coordinator.create_workflow(
            name=f"episode_{episode_id}",
            description=f"Training episode {self._episode_count}",
        )
        
        # Phase 1: Generate environment (Agent A)
        env_task = Task(
            id=f"{episode_id}_env",
            type="environment",
            payload={"stage": current_stage},
            priority=10,
        )
        workflow.add_task(env_task, stage="produce")
        
        # Phase 2: Run experiments (Agent B)
        exp_task = Task(
            id=f"{episode_id}_exp",
            type="experiment",
            payload={"max_iterations": self.config.max_iterations},
            dependencies=[env_task.id],
            priority=5,
        )
        workflow.add_task(exp_task, stage="execute")
        
        # Phase 3: Review results
        review_task = Task(
            id=f"{episode_id}_review",
            type="review",
            payload={"round": 1},
            dependencies=[exp_task.id],
            priority=3,
        )
        workflow.add_task(review_task, stage="review")
        
        # Execute workflow
        result = self._coordinator.run_workflow(workflow)
        
        # Extract results
        env_result = result["tasks"].get(env_task.id, {}).get("result", {})
        exp_result = result["tasks"].get(exp_task.id, {}).get("result", {})
        review_result = result["tasks"].get(review_task.id, {}).get("result", {})
        
        # Run GRPO training
        rewards = [exp_result.get("total_reward", 0.0)]
        training_result = self._handle_training_task(Task(
            id=f"{episode_id}_train",
            type="training",
            payload={"rewards": rewards},
        ))
        
        # Compile episode result
        duration = time.time() - start_time
        
        episode = EpisodeResult(
            episode_id=episode_id,
            stage=current_stage,
            environment_id=env_result.get("env_id", "unknown"),
            tasks_completed=result["statistics"]["completed"],
            tasks_failed=result["statistics"]["failed"],
            total_reward=exp_result.get("total_reward", 0.0),
            keep_rate=exp_result.get("keep_rate", 0.0),
            review_verdict=review_result.get("verdict", "unknown"),
            review_rounds=review_result.get("round", 1),
            grpo_advantage=training_result.get("grpo_advantage", 0.0),
            training_loss=training_result.get("policy_loss", 0.0),
            duration=duration,
            metadata={
                "workflow_id": workflow.id,
                "env_name": env_result.get("env_name"),
                "experiments": exp_result.get("experiments", 0),
            },
        )
        
        self._results.append(episode)
        
        # Callback
        if self._on_episode_complete:
            self._on_episode_complete(episode)
        
        logger.info(f"Episode {episode_id}: keep_rate={episode.keep_rate:.1%}, verdict={episode.review_verdict}")
        
        return episode
    
    def run_training(self, episodes: int = 10) -> List[EpisodeResult]:
        """
        Run multiple training episodes.
        
        Args:
            episodes: Number of episodes to run
        
        Returns:
            List of all episode results
        """
        logger.info(f"Starting training: {episodes} episodes")
        
        results = []
        for i in range(episodes):
            episode = self.run_episode()
            results.append(episode)
            
            # Log progress
            if (i + 1) % 5 == 0:
                avg_keep_rate = sum(e.keep_rate for e in results) / len(results)
                logger.info(f"Progress: {i+1}/{episodes}, avg_keep_rate={avg_keep_rate:.1%}")
        
        return results
    
    def get_progress(self) -> ProgressMetrics:
        """Get current progress metrics"""
        return self._progress
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive training statistics"""
        if not self._results:
            return {"episodes": 0}
        
        episodes = self._results
        verdicts = {}
        stages = {}
        
        for ep in episodes:
            verdicts[ep.review_verdict] = verdicts.get(ep.review_verdict, 0) + 1
            stages[ep.stage] = stages.get(ep.stage, 0) + 1
        
        return {
            "episodes": len(episodes),
            "total_duration": sum(e.duration for e in episodes),
            "average_keep_rate": sum(e.keep_rate for e in episodes) / len(episodes),
            "average_reward": sum(e.total_reward for e in episodes) / len(episodes),
            "verdict_distribution": verdicts,
            "stage_distribution": stages,
            "final_progress": self._progress.to_dict(),
            "coordinator_status": self._coordinator.get_status(),
        }
    
    def print_summary(self) -> None:
        """Print training summary"""
        stats = self.get_statistics()
        
        print("\n" + "=" * 60)
        print("Dual-Agent Training Summary")
        print("=" * 60)
        print(f"Episodes:         {stats['episodes']}")
        print(f"Total Duration:   {stats['total_duration']:.1f}s")
        print(f"Average Keep Rate: {stats['average_keep_rate']:.1%}")
        print(f"Average Reward:   {stats['average_reward']:.3f}")
        print(f"Verdicts:         {stats['verdict_distribution']}")
        print(f"Stages:           {stats['stage_distribution']}")
        print("=" * 60)
