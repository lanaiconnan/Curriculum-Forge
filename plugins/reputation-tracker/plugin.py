"""Reputation Tracker Plugin

Tracks agent reputation changes and provides analytics.

Hooks:
    governance:agent_registered  - Initialize reputation tracking
    governance:reputation_changed - Record reputation changes
    governance:task_completed    - Update reputation stats
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

from services.plugin_system import Plugin, PluginMeta, PluginContext

logger = logging.getLogger(__name__)


@dataclass
class ReputationEvent:
    """A single reputation change event"""
    agent_id: str
    delta: int
    reason: str
    timestamp: str
    task_id: Optional[str] = None
    

@dataclass
class AgentReputationStats:
    """Reputation statistics for an agent"""
    agent_id: str
    current_score: int = 50  # Default starting score
    total_changes: int = 0
    total_positive: int = 0
    total_negative: int = 0
    events: List[ReputationEvent] = field(default_factory=list)
    registered_at: Optional[str] = None
    
    def apply_change(self, delta: int, reason: str, task_id: Optional[str] = None):
        """Apply a reputation change"""
        self.current_score += delta
        self.total_changes += 1
        
        if delta > 0:
            self.total_positive += delta
        else:
            self.total_negative += abs(delta)
        
        self.events.append(ReputationEvent(
            agent_id=self.agent_id,
            delta=delta,
            reason=reason,
            timestamp=datetime.utcnow().isoformat(),
            task_id=task_id,
        ))


class ReputationTrackerPlugin(Plugin):
    """
    Tracks agent reputation changes across the governance system.
    
    Provides:
    - Per-agent reputation history
    - Aggregated statistics
    - Trend analysis
    - Alert when reputation drops below threshold
    
    Usage in governance:
        # In Mayor.apply_reputation_change()
        plugin_manager.dispatch("governance:reputation_changed", {
            "agent_id": agent_id,
            "delta": delta,
            "reason": reason,
        })
    """
    
    meta = PluginMeta(
        name="reputation-tracker",
        version="1.0.0",
        description="Tracks agent reputation changes and provides analytics",
        hooks=[
            "governance:agent_registered",
            "governance:agent_unregistered",
            "governance:reputation_changed",
            "governance:task_completed",
        ],
        priority=100,
    )
    
    def __init__(
        self,
        alert_threshold: int = 30,
        starting_score: int = 50,
    ):
        super().__init__()
        self.alert_threshold = alert_threshold
        self.starting_score = starting_score
        self._stats: Dict[str, AgentReputationStats] = {}
        self._alerts: List[Dict[str, Any]] = []
    
    def initialize(self) -> None:
        self._initialized = True
        logger.info(
            f"ReputationTrackerPlugin initialized "
            f"(alert_threshold={self.alert_threshold}, starting_score={self.starting_score})"
        )
    
    def cleanup(self) -> None:
        self._stats.clear()
        self._alerts.clear()
        self._initialized = False
    
    def on_hook(self, ctx: PluginContext) -> Optional[PluginContext]:
        if ctx.hook_name == "governance:agent_registered":
            return self._on_agent_registered(ctx)
        elif ctx.hook_name == "governance:agent_unregistered":
            return self._on_agent_unregistered(ctx)
        elif ctx.hook_name == "governance:reputation_changed":
            return self._on_reputation_changed(ctx)
        elif ctx.hook_name == "governance:task_completed":
            return self._on_task_completed(ctx)
        return ctx
    
    def _on_agent_registered(self, ctx: PluginContext) -> PluginContext:
        """Initialize tracking when agent registers"""
        agent_id = ctx.get("agent_id")
        if not agent_id:
            return ctx
        
        if agent_id not in self._stats:
            self._stats[agent_id] = AgentReputationStats(
                agent_id=agent_id,
                current_score=self.starting_score,
                registered_at=datetime.utcnow().isoformat(),
            )
            logger.info(f"Started tracking agent: {agent_id}")
        
        return ctx
    
    def _on_agent_unregistered(self, ctx: PluginContext) -> PluginContext:
        """Clean up tracking when agent unregisters"""
        agent_id = ctx.get("agent_id")
        if agent_id and agent_id in self._stats:
            # Keep stats for historical analysis, just mark as inactive
            logger.info(f"Agent unregistered (keeping history): {agent_id}")
        
        return ctx
    
    def _on_reputation_changed(self, ctx: PluginContext) -> PluginContext:
        """Record reputation change"""
        agent_id = ctx.get("agent_id")
        delta = ctx.get("delta", 0)
        reason = ctx.get("reason", "unknown")
        task_id = ctx.get("task_id")
        
        if not agent_id:
            return ctx
        
        # Initialize if not exists
        if agent_id not in self._stats:
            self._stats[agent_id] = AgentReputationStats(
                agent_id=agent_id,
                current_score=self.starting_score,
                registered_at=datetime.utcnow().isoformat(),
            )
        
        stats = self._stats[agent_id]
        old_score = stats.current_score
        stats.apply_change(delta, reason, task_id)
        
        # Check for alert threshold
        if stats.current_score < self.alert_threshold and old_score >= self.alert_threshold:
            alert = {
                "agent_id": agent_id,
                "score": stats.current_score,
                "threshold": self.alert_threshold,
                "timestamp": datetime.utcnow().isoformat(),
            }
            self._alerts.append(alert)
            logger.warning(
                f"Agent {agent_id} reputation dropped below threshold: "
                f"{stats.current_score} < {self.alert_threshold}"
            )
            ctx.set("reputation_alert", True)
        
        ctx.set("current_score", stats.current_score)
        return ctx
    
    def _on_task_completed(self, ctx: PluginContext) -> PluginContext:
        """Update stats when task completes"""
        agent_id = ctx.get("agent_id")
        task_id = ctx.get("task_id")
        success = ctx.get("success", False)
        
        if agent_id and agent_id in self._stats:
            # Task completion is already tracked via reputation changes
            # This hook is for additional analytics if needed
            pass
        
        return ctx
    
    # ===== Public API =====
    
    def get_agent_stats(self, agent_id: str) -> Optional[AgentReputationStats]:
        """Get reputation stats for an agent"""
        return self._stats.get(agent_id)
    
    def get_all_stats(self) -> Dict[str, AgentReputationStats]:
        """Get all agent reputation stats"""
        return self._stats
    
    def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top agents by reputation"""
        sorted_agents = sorted(
            self._stats.values(),
            key=lambda s: s.current_score,
            reverse=True,
        )
        return [
            {
                "rank": i + 1,
                "agent_id": stats.agent_id,
                "score": stats.current_score,
                "total_changes": stats.total_changes,
            }
            for i, stats in enumerate(sorted_agents[:limit])
        ]
    
    def get_alerts(self, clear: bool = False) -> List[Dict[str, Any]]:
        """Get reputation alerts"""
        alerts = list(self._alerts)
        if clear:
            self._alerts.clear()
        return alerts
    
    def get_summary(self) -> Dict[str, Any]:
        """Get overall reputation summary"""
        if not self._stats:
            return {
                "total_agents": 0,
                "average_score": 0,
                "total_events": 0,
            }
        
        scores = [s.current_score for s in self._stats.values()]
        events = sum(s.total_changes for s in self._stats.values())
        
        return {
            "total_agents": len(self._stats),
            "average_score": sum(scores) / len(scores),
            "min_score": min(scores),
            "max_score": max(scores),
            "total_events": events,
            "total_alerts": len(self._alerts),
        }
