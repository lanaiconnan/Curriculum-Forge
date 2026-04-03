"""RL Training Service

This service handles the RL training loop:
- Computing rewards
- Updating models with GRPO
- Managing experience buffer

Based on the service-oriented architecture pattern.
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import logging
import math

from .base import ServiceBase, ServiceConfig, ServiceState
from .models import ExperimentRecord, RewardBreakdown
from .container import ServiceProvider

logger = logging.getLogger(__name__)


@dataclass
class RLConfig(ServiceConfig):
    """Configuration for RLTrainerService"""
    
    def __init__(
        self,
        name: str = "trainer",
        learning_rate: float = 3e-4,
        gamma: float = 0.99,
        epsilon: float = 0.2,
        max_experiences: int = 10000,
        batch_size: int = 32,
        use_grpo: bool = True,
        **kwargs
    ):
        super().__init__(name=name, **kwargs)
        self.learning_rate = learning_rate
        self.gamma = gamma
        self.epsilon = epsilon
        self.max_experiences = max_experiences
        self.batch_size = batch_size
        self.use_grpo = use_grpo


@dataclass
class Experience:
    """A single experience for RL training"""
    state: Dict[str, Any]
    action: Dict[str, Any]
    reward: float
    next_state: Dict[str, Any]
    done: bool
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TrainingStats:
    """Statistics from a training step"""
    total_reward: float
    avg_reward: float
    max_reward: float
    min_reward: float
    experiences: int
    grpo_advantage: float
    policy_loss: float


class RLTrainerService(ServiceBase[RLConfig]):
    """
    Service for RL training.
    
    This service:
    1. Maintains an experience buffer
    2. Computes GRPO advantages
    3. Updates policy (simulated in this implementation)
    
    Usage:
        provider = ServiceProvider()
        provider.configure(RLTrainerService, config)
        provider.start()
        
        trainer = provider.get(RLTrainerService)
        stats = trainer.train_step(experiences)
    """
    
    def __init__(self, config: RLConfig):
        super().__init__(config)
        self._buffer: List[Experience] = []
        self._total_steps = 0
    
    def initialize(self) -> None:
        """Initialize the service"""
        logger.info(f"Initializing RLTrainerService (lr={self.config.learning_rate})")
    
    def start(self) -> None:
        """Start the service"""
        logger.info("RLTrainerService started")
    
    def stop(self) -> None:
        """Stop the service"""
        logger.info("RLTrainerService stopped")
    
    def add_experience(self, exp: Experience) -> None:
        """Add an experience to the buffer"""
        if len(self._buffer) >= self.config.max_experiences:
            self._buffer.pop(0)
        self._buffer.append(exp)
    
    def add_experiences(self, experiences: List[Experience]) -> None:
        """Add multiple experiences"""
        for exp in experiences:
            self.add_experience(exp)
    
    def compute_grpo_advantage(
        self,
        rewards: List[float],
    ) -> List[float]:
        """
        Compute GRPO (Group Relative Policy Optimization) advantages.
        
        GRPO normalizes advantages within a group:
        A_i = (r_i - μ_Q) / (σ_Q + η)
        
        This reduces variance and improves training stability.
        
        Args:
            rewards: List of rewards from a group
        
        Returns:
            List of advantages
        """
        if not rewards:
            return []
        
        n = len(rewards)
        mean = sum(rewards) / n
        variance = sum((r - mean) ** 2 for r in rewards) / n
        std = math.sqrt(variance)
        
        # Small constant to avoid division by zero
        eta = 0.01
        
        advantages = [(r - mean) / (std + eta) for r in rewards]
        
        return advantages
    
    def train_step(
        self,
        experiences: Optional[List[Experience]] = None,
    ) -> TrainingStats:
        """
        Perform one training step.
        
        Args:
            experiences: Optional new experiences to add
        
        Returns:
            Training statistics
        """
        if experiences:
            self.add_experiences(experiences)
        
        if not self._buffer:
            return TrainingStats(
                total_reward=0.0,
                avg_reward=0.0,
                max_reward=0.0,
                min_reward=0.0,
                experiences=0,
                grpo_advantage=0.0,
                policy_loss=0.0,
            )
        
        # Get rewards from buffer
        rewards = [exp.reward for exp in self._buffer]
        
        # Compute GRPO advantages
        advantages = self.compute_grpo_advantage(rewards)
        
        # Compute stats
        total_reward = sum(rewards)
        avg_reward = total_reward / len(rewards)
        max_reward = max(rewards)
        min_reward = min(rewards)
        avg_advantage = sum(advantages) / len(advantages) if advantages else 0.0
        
        # Simulate policy loss (in real implementation, this would update the model)
        policy_loss = -avg_advantage * self.config.learning_rate
        
        self._total_steps += 1
        
        logger.info(f"Training step {self._total_steps}: avg_reward={avg_reward:.3f}, advantage={avg_advantage:.3f}")
        
        return TrainingStats(
            total_reward=total_reward,
            avg_reward=avg_reward,
            max_reward=max_reward,
            min_reward=min_reward,
            experiences=len(self._buffer),
            grpo_advantage=avg_advantage,
            policy_loss=policy_loss,
        )
    
    def get_buffer_size(self) -> int:
        """Get current buffer size"""
        return len(self._buffer)
    
    def clear_buffer(self) -> None:
        """Clear the experience buffer"""
        self._buffer.clear()
    
    def sample_batch(self, batch_size: Optional[int] = None) -> List[Experience]:
        """Sample a batch from the buffer"""
        size = batch_size or self.config.batch_size
        if len(self._buffer) <= size:
            return self._buffer.copy()
        
        # Simple random sampling (in real implementation, use proper sampling)
        import random
        return random.sample(self._buffer, size)
    
    def health_check(self) -> Dict[str, Any]:
        """Extended health check"""
        base = super().health_check()
        base.update({
            "buffer_size": len(self._buffer),
            "max_buffer": self.config.max_experiences,
            "total_steps": self._total_steps,
        })
        return base
