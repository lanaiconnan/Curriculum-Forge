"""Stage Tracker Plugin

Tracks learning stage transitions and emits alerts on regressions.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from services.plugin_system import Plugin, PluginMeta, PluginContext

logger = logging.getLogger(__name__)

STAGE_ORDER = {"beginner": 0, "intermediate": 1, "advanced": 2}


class StageTrackerPlugin(Plugin):
    """
    Tracks learning stage transitions.
    
    Hooks:
        stage:before_transition  - Validate transition
        stage:after_transition   - Record and alert
    """
    
    meta = PluginMeta(
        name="stage-tracker",
        version="1.0.0",
        description="Tracks learning stage transitions and alerts on regressions",
        hooks=["stage:before_transition", "stage:after_transition"],
        priority=50,
    )
    
    def __init__(self):
        super().__init__()
        self._history: List[Dict[str, Any]] = []
        self._current_stage: Optional[str] = None
        self._regression_count = 0
    
    def initialize(self) -> None:
        self._initialized = True
        logger.info("StageTrackerPlugin initialized")
    
    def cleanup(self) -> None:
        self._initialized = False
    
    def on_hook(self, ctx: PluginContext) -> Optional[PluginContext]:
        if ctx.hook_name == "stage:before_transition":
            return self._before_transition(ctx)
        elif ctx.hook_name == "stage:after_transition":
            return self._after_transition(ctx)
        return ctx
    
    def _before_transition(self, ctx: PluginContext) -> Optional[PluginContext]:
        """Validate stage transition before it happens"""
        from_stage = ctx.get('from_stage')
        to_stage = ctx.get('to_stage')
        keep_rate = ctx.get('keep_rate', 0.0)
        
        if not from_stage or not to_stage:
            return ctx
        
        from_order = STAGE_ORDER.get(from_stage, -1)
        to_order = STAGE_ORDER.get(to_stage, -1)
        
        # Detect regression
        if to_order < from_order:
            self._regression_count += 1
            logger.warning(
                f"StageTracker: REGRESSION detected! "
                f"{from_stage} → {to_stage} "
                f"(keep_rate={keep_rate:.1%}, regression #{self._regression_count})"
            )
            ctx.set('is_regression', True)
        else:
            ctx.set('is_regression', False)
        
        return ctx
    
    def _after_transition(self, ctx: PluginContext) -> Optional[PluginContext]:
        """Record stage transition after it happens"""
        from_stage = ctx.get('from_stage')
        to_stage = ctx.get('to_stage')
        keep_rate = ctx.get('keep_rate', 0.0)
        
        if not from_stage or not to_stage:
            return ctx
        
        # Record transition
        record = {
            "from": from_stage,
            "to": to_stage,
            "at": datetime.now().isoformat(),
            "keep_rate": keep_rate,
            "is_regression": ctx.get('is_regression', False),
        }
        self._history.append(record)
        self._current_stage = to_stage
        
        direction = "↑" if not ctx.get('is_regression') else "↓"
        logger.info(
            f"StageTracker: {from_stage} {direction} {to_stage} "
            f"(keep_rate={keep_rate:.1%})"
        )
        
        return ctx
    
    @property
    def history(self) -> List[Dict[str, Any]]:
        return self._history.copy()
    
    @property
    def regression_count(self) -> int:
        return self._regression_count
    
    @property
    def current_stage(self) -> Optional[str]:
        return self._current_stage
    
    def get_summary(self) -> Dict[str, Any]:
        """Get transition summary"""
        return {
            "total_transitions": len(self._history),
            "regressions": self._regression_count,
            "current_stage": self._current_stage,
            "history": self._history,
        }
