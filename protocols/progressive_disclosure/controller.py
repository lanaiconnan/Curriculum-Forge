"""Difficulty Controller - Fine-grained difficulty adjustment

Continuously adjusts task difficulty based on real-time performance signals.
Not limited to 3 fixed stages - uses float difficulty 0.0-1.0.

Key idea: Difficulty is multi-dimensional, not a single scalar.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
from datetime import datetime


class DifficultyDimension(Enum):
    """Dimensions of difficulty"""
    COMPLEXITY = "complexity"       # Task complexity
    CONSTRAINTS = "constraints"     # Time/tool constraints
    CONTEXT = "context"             # Context richness (hints, examples)
    TOOLS = "tools"                 # Tool requirements
    SCOPE = "scope"                 # Task scope/breadth


@dataclass
class DifficultyDimensions:
    """Multi-dimensional difficulty settings
    
    Each dimension is 0.0-1.0:
    - 0.0 = easiest (most scaffolding, fewest constraints)
    - 1.0 = hardest (no help, tight constraints)
    """
    complexity: float = 0.3       # Task complexity
    constraints: float = 0.3      # Time/tool limits
    context: float = 0.3          # Context richness (low = more hints)
    tools: float = 0.3            # Tool requirements
    scope: float = 0.3            # Task scope
    
    def overall(self) -> float:
        """Compute weighted overall difficulty"""
        weights = {
            "complexity": 0.30,
            "constraints": 0.20,
            "context": 0.20,
            "tools": 0.15,
            "scope": 0.15,
        }
        return (
            self.complexity * weights["complexity"] +
            self.constraints * weights["constraints"] +
            self.context * weights["context"] +
            self.tools * weights["tools"] +
            self.scope * weights["scope"]
        )
    
    def to_dict(self) -> Dict[str, float]:
        return {
            "complexity": self.complexity,
            "constraints": self.constraints,
            "context": self.context,
            "tools": self.tools,
            "scope": self.scope,
            "overall": self.overall(),
        }


@dataclass
class PerformanceSignal:
    """Real-time performance signal from learner
    
    Collected after each task/round to drive difficulty adjustment.
    """
    score: float              # 0-1, task score
    keep_rate: float          # 0-1, recent acceptance rate
    time_used: float          # Seconds
    time_budget: float        # Allowed seconds
    error_count: int          # Number of errors
    tool_calls: int           # Number of tool calls
    success: bool             # Task success?
    round_num: int            # Review round (if applicable)
    
    def time_efficiency(self) -> float:
        """Time efficiency 0-1 (higher = faster)"""
        if self.time_budget <= 0:
            return 0.5
        return max(0, 1 - (self.time_used / self.time_budget))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "keep_rate": self.keep_rate,
            "time_used": self.time_used,
            "time_budget": self.time_budget,
            "time_efficiency": self.time_efficiency(),
            "error_count": self.error_count,
            "tool_calls": self.tool_calls,
            "success": self.success,
            "round_num": self.round_num,
        }


@dataclass
class DifficultyAdjustment:
    """Result of difficulty adjustment"""
    old_difficulty: DifficultyDimensions
    new_difficulty: DifficultyDimensions
    delta: Dict[str, float]          # Change per dimension
    reason: str
    confidence: float                # Confidence in adjustment
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "old": self.old_difficulty.to_dict(),
            "new": self.new_difficulty.to_dict(),
            "delta": self.delta,
            "reason": self.reason,
            "confidence": self.confidence,
        }


@dataclass
class DifficultyConfig:
    """Configuration for difficulty controller"""
    # Adjustment rates
    increase_rate: float = 0.05      # How fast to increase difficulty
    decrease_rate: float = 0.08      # How fast to decrease (faster = more supportive)
    
    # Thresholds
    success_threshold: float = 0.7   # Score above this = success
    failure_threshold: float = 0.4   # Score below this = failure
    
    # Bounds
    min_difficulty: float = 0.1      # Minimum difficulty
    max_difficulty: float = 0.95     # Maximum difficulty
    
    # History
    history_window: int = 5          # Number of signals to consider
    stability_window: int = 3        # Signals needed for stable adjustment
    
    # Dimension-specific adjustments
    dimension_weights: Dict[str, float] = field(default_factory=lambda: {
        "complexity": 1.0,
        "constraints": 0.8,
        "context": 1.2,  # Context adjusts faster (hints matter)
        "tools": 0.7,
        "scope": 0.6,
    })


class DifficultyController:
    """
    Controls fine-grained difficulty adjustment
    
    Uses performance signals to continuously adjust task difficulty
    across multiple dimensions. Not limited to fixed stages.
    
    Flow:
        1. Collect PerformanceSignals from learner
        2. Compute adjustment based on recent performance
        3. Apply to DifficultyDimensions
        4. Generate TaskConfig for next task
    """
    
    def __init__(self, config: DifficultyConfig = None):
        self.config = config or DifficultyConfig()
        self.current_difficulty = DifficultyDimensions()
        self.signal_history: List[PerformanceSignal] = []
        self.adjustment_history: List[DifficultyAdjustment] = []
    
    def record_signal(self, signal: PerformanceSignal):
        """Record a performance signal"""
        self.signal_history.append(signal)
        
        # Keep only recent history
        if len(self.signal_history) > self.config.history_window * 2:
            self.signal_history = self.signal_history[-self.config.history_window:]
    
    def adjust(self) -> DifficultyAdjustment:
        """
        Adjust difficulty based on recent signals
        
        Returns:
            DifficultyAdjustment with new settings
        """
        if len(self.signal_history) < self.config.stability_window:
            # Not enough data
            return DifficultyAdjustment(
                old_difficulty=self.current_difficulty,
                new_difficulty=self.current_difficulty,
                delta={},
                reason="Insufficient signals for adjustment",
                confidence=0.0,
            )
        
        # Analyze recent performance
        recent = self.signal_history[-self.config.history_window:]
        
        avg_score = sum(s.score for s in recent) / len(recent)
        avg_success = sum(1 for s in recent if s.success) / len(recent)
        avg_time_eff = sum(s.time_efficiency() for s in recent) / len(recent)
        avg_errors = sum(s.error_count for s in recent) / len(recent)
        
        # Determine adjustment direction
        delta = {}
        reason_parts = []
        
        # Score-based adjustment
        if avg_score >= self.config.success_threshold:
            # Doing well - increase difficulty
            adjustment = self.config.increase_rate
            reason_parts.append(f"high score ({avg_score:.2f})")
        elif avg_score <= self.config.failure_threshold:
            # Struggling - decrease difficulty
            adjustment = -self.config.decrease_rate
            reason_parts.append(f"low score ({avg_score:.2f})")
        else:
            # Borderline - small adjustment based on trend
            adjustment = self._compute_trend_adjustment(recent)
            reason_parts.append(f"borderline score ({avg_score:.2f})")
        
        # Time efficiency factor
        if avg_time_eff > 0.7 and adjustment > 0:
            adjustment *= 1.2  # Faster = increase more
            reason_parts.append("fast execution")
        elif avg_time_eff < 0.3 and adjustment < 0:
            adjustment *= 1.2  # Slow = decrease more
            reason_parts.append("slow execution")
        
        # Error factor
        if avg_errors > 2:
            adjustment -= 0.02  # More errors = easier
            reason_parts.append(f"errors ({avg_errors:.1f})")
        
        # Apply adjustment per dimension
        old_dims = self.current_difficulty.to_dict()
        new_dims = {}
        
        for dim in ["complexity", "constraints", "context", "tools", "scope"]:
            dim_adjust = adjustment * self.config.dimension_weights.get(dim, 1.0)
            new_val = old_dims[dim] + dim_adjust
            new_val = max(self.config.min_difficulty, 
                         min(self.config.max_difficulty, new_val))
            new_dims[dim] = new_val
            delta[dim] = new_val - old_dims[dim]
        
        # Update current difficulty
        old_difficulty = DifficultyDimensions(**{k: v for k, v in old_dims.items() if k != "overall"})
        new_difficulty = DifficultyDimensions(
            complexity=new_dims["complexity"],
            constraints=new_dims["constraints"],
            context=new_dims["context"],
            tools=new_dims["tools"],
            scope=new_dims["scope"],
        )
        
        self.current_difficulty = new_difficulty
        
        # Compute confidence
        confidence = min(1.0, len(recent) / self.config.history_window)
        
        adjustment_result = DifficultyAdjustment(
            old_difficulty=old_difficulty,
            new_difficulty=new_difficulty,
            delta=delta,
            reason=", ".join(reason_parts),
            confidence=confidence,
        )
        
        self.adjustment_history.append(adjustment_result)
        return adjustment_result
    
    def _compute_trend_adjustment(self, signals: List[PerformanceSignal]) -> float:
        """Compute adjustment based on trend (improving/declining)"""
        if len(signals) < 3:
            return 0.0
        
        # Compare recent vs older
        recent = signals[-2:]
        older = signals[-4:-2] if len(signals) >= 4 else signals[:-2]
        
        recent_avg = sum(s.score for s in recent) / len(recent)
        older_avg = sum(s.score for s in older) / len(older) if older else recent_avg
        
        trend = recent_avg - older_avg
        
        # Improving trend = slight increase
        if trend > 0.1:
            return self.config.increase_rate * 0.5
        elif trend < -0.1:
            return -self.config.decrease_rate * 0.5
        else:
            return 0.0
    
    def get_current_difficulty(self) -> DifficultyDimensions:
        """Get current difficulty settings"""
        return self.current_difficulty
    
    def set_difficulty(self, difficulty: DifficultyDimensions):
        """Manually set difficulty (e.g., from expert selection)"""
        self.current_difficulty = difficulty
    
    def reset(self, base_difficulty: float = 0.3):
        """Reset to baseline difficulty"""
        self.current_difficulty = DifficultyDimensions(
            complexity=base_difficulty,
            constraints=base_difficulty,
            context=base_difficulty,
            tools=base_difficulty,
            scope=base_difficulty,
        )
        self.signal_history.clear()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get controller statistics"""
        if not self.adjustment_history:
            return {
                "total_adjustments": 0,
                "current_difficulty": self.current_difficulty.to_dict(),
            }
        
        # Average adjustments
        avg_deltas = {}
        for dim in ["complexity", "constraints", "context", "tools", "scope"]:
            avg_deltas[dim] = sum(a.delta.get(dim, 0) for a in self.adjustment_history) / len(self.adjustment_history)
        
        return {
            "total_adjustments": len(self.adjustment_history),
            "current_difficulty": self.current_difficulty.to_dict(),
            "average_deltas": avg_deltas,
            "signals_recorded": len(self.signal_history),
        }
