"""Reward Logger Plugin

Logs reward breakdown after each experiment.
Writes structured logs to rewards.log.
"""

import os
import logging
from datetime import datetime
from typing import Optional

from services.plugin_system import Plugin, PluginMeta, PluginContext

logger = logging.getLogger(__name__)


class RewardLoggerPlugin(Plugin):
    """
    Logs reward breakdown after each experiment.
    
    Hooks:
        reward:after_calc  - Log reward components
        exp:after_run      - Log experiment summary
    """
    
    meta = PluginMeta(
        name="reward-logger",
        version="1.0.0",
        description="Logs reward breakdown after each experiment",
        hooks=["reward:after_calc", "exp:after_run"],
        priority=100,
    )
    
    def __init__(self):
        super().__init__()
        self._log_path: Optional[str] = None
        self._log_count = 0
    
    def initialize(self) -> None:
        workspace = os.environ.get('CURRICULUM_FORGE_WORKSPACE', '.')
        self._log_path = os.path.join(workspace, 'rewards.log')
        self._initialized = True
        logger.info(f"RewardLoggerPlugin: logging to {self._log_path}")
    
    def cleanup(self) -> None:
        self._initialized = False
    
    def on_hook(self, ctx: PluginContext) -> Optional[PluginContext]:
        if ctx.hook_name == "reward:after_calc":
            self._log_reward(ctx)
        elif ctx.hook_name == "exp:after_run":
            self._log_experiment(ctx)
        return ctx
    
    def _log_reward(self, ctx: PluginContext) -> None:
        """Log reward breakdown"""
        reward = ctx.get('reward', {})
        exp_id = ctx.get('exp_id', 'unknown')
        
        rformat = reward.get('rformat', 0.0)
        rname = reward.get('rname', 0.0)
        rparam = reward.get('rparam', 0.0)
        rvalue = reward.get('rvalue', 0.0)
        rfinal = reward.get('rfinal', 0.0)
        
        line = (
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
            f"{exp_id} | "
            f"rformat={rformat:.1f} rname={rname:.1f} "
            f"rparam={rparam:.2f} rvalue={rvalue:.2f} | "
            f"rfinal={rfinal:.2f}\n"
        )
        
        self._write(line)
        self._log_count += 1
    
    def _log_experiment(self, ctx: PluginContext) -> None:
        """Log experiment summary"""
        exp_id = ctx.get('exp_id', 'unknown')
        keep_rate = ctx.get('keep_rate', 0.0)
        total_reward = ctx.get('total_reward', 0.0)
        stage = ctx.get('stage', 'unknown')
        
        line = (
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
            f"SUMMARY {exp_id} | "
            f"stage={stage} keep_rate={keep_rate:.1%} "
            f"total_reward={total_reward:.2f}\n"
        )
        
        self._write(line)
    
    def _write(self, line: str) -> None:
        """Write a line to the log file"""
        if self._log_path:
            try:
                with open(self._log_path, 'a') as f:
                    f.write(line)
            except Exception as e:
                logger.error(f"RewardLoggerPlugin: write failed: {e}")
        else:
            # Fallback to logger
            logger.info(line.strip())
    
    @property
    def log_count(self) -> int:
        return self._log_count
