"""Experiment Filter Plugin

Filters low-quality experiments before they enter the RL training buffer.
"""

import logging
from typing import Optional

from services.plugin_system import Plugin, PluginMeta, PluginContext

logger = logging.getLogger(__name__)


class ExperimentFilterPlugin(Plugin):
    """
    Filters low-quality experiments.
    
    Hooks:
        exp:before_run      - Skip invalid experiment configs
        result:before_save  - Filter results below quality threshold
    """
    
    meta = PluginMeta(
        name="experiment-filter",
        version="1.0.0",
        description="Filters low-quality experiments before RL training",
        hooks=["exp:before_run", "result:before_save"],
        priority=10,  # High priority — runs first
    )
    
    def __init__(
        self,
        min_reward: float = -2.0,
        max_duration: float = 60.0,
    ):
        super().__init__()
        self.min_reward = min_reward
        self.max_duration = max_duration
        self._filtered_count = 0
        self._passed_count = 0
    
    def initialize(self) -> None:
        self._initialized = True
        logger.info(
            f"ExperimentFilterPlugin initialized "
            f"(min_reward={self.min_reward}, max_duration={self.max_duration})"
        )
    
    def cleanup(self) -> None:
        self._initialized = False
    
    def on_hook(self, ctx: PluginContext) -> Optional[PluginContext]:
        if ctx.hook_name == "exp:before_run":
            return self._before_run(ctx)
        elif ctx.hook_name == "result:before_save":
            return self._before_save(ctx)
        return ctx
    
    def _before_run(self, ctx: PluginContext) -> Optional[PluginContext]:
        """Validate experiment config before running"""
        env = ctx.get('env')
        
        if env is None:
            logger.warning("ExperimentFilter: no env in context, skipping filter")
            return ctx
        
        # Check difficulty is valid
        difficulty = getattr(env, 'difficulty', None)
        if difficulty is not None and not (0.0 <= difficulty <= 1.0):
            logger.warning(
                f"ExperimentFilter: invalid difficulty {difficulty}, skipping experiment"
            )
            ctx.set('skip', True)
            ctx.set('skip_reason', f"invalid difficulty: {difficulty}")
            self._filtered_count += 1
            return ctx
        
        # Check tasks exist
        task_count = getattr(env, 'task_count', 0)
        if task_count == 0:
            logger.warning("ExperimentFilter: no tasks in env, skipping experiment")
            ctx.set('skip', True)
            ctx.set('skip_reason', "no tasks in environment")
            self._filtered_count += 1
            return ctx
        
        ctx.set('skip', False)
        self._passed_count += 1
        return ctx
    
    def _before_save(self, ctx: PluginContext) -> Optional[PluginContext]:
        """Filter results below quality threshold"""
        reward = ctx.get('reward', 0.0)
        duration = ctx.get('duration', 0.0)
        
        # Filter by reward
        if reward < self.min_reward:
            logger.debug(
                f"ExperimentFilter: reward {reward:.2f} < min {self.min_reward}, filtering"
            )
            ctx.set('filtered', True)
            ctx.set('filter_reason', f"reward {reward:.2f} below threshold {self.min_reward}")
            self._filtered_count += 1
            return ctx
        
        # Filter by duration
        if duration > self.max_duration:
            logger.debug(
                f"ExperimentFilter: duration {duration:.1f}s > max {self.max_duration}s, filtering"
            )
            ctx.set('filtered', True)
            ctx.set('filter_reason', f"duration {duration:.1f}s exceeds max {self.max_duration}s")
            self._filtered_count += 1
            return ctx
        
        ctx.set('filtered', False)
        self._passed_count += 1
        return ctx
    
    @property
    def filtered_count(self) -> int:
        return self._filtered_count
    
    @property
    def passed_count(self) -> int:
        return self._passed_count
    
    @property
    def filter_rate(self) -> float:
        total = self._filtered_count + self._passed_count
        return self._filtered_count / total if total > 0 else 0.0
    
    def get_stats(self):
        return {
            "filtered": self._filtered_count,
            "passed": self._passed_count,
            "filter_rate": self.filter_rate,
            "min_reward": self.min_reward,
            "max_duration": self.max_duration,
        }
