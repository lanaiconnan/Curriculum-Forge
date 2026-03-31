"""Expert Selector - Dynamic expert selection based on learner state

Selects the most appropriate expert based on:
- Current weak areas from FeedbackLoop/Analyst
- Learning stage (beginner/intermediate/advanced)
- Performance history
- Tool availability
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
import math
import random


class SelectionStrategy(Enum):
    """Strategies for expert selection"""
    WEAK_AREA_FIRST = "weak_area_first"
    PERFORMANCE_BASED = "performance_based"
    EXPLORATION = "exploration"
    HYBRID = "hybrid"
    
    @classmethod
    def from_string(cls, s: str):
        """Create from string, mapping common variations"""
        s = s.upper().replace("-", "_")
        try:
            return cls(s)
        except ValueError:
            return cls.HYBRID  # Default


@dataclass
class LearnerState:
    """Current state of the learner (Agent B)"""
    weak_areas: List[str] = field(default_factory=list)
    skill_level: str = "beginner"
    recent_success_rate: float = 0.5
    overall_success_rate: float = 0.5
    avg_reward: float = 0.5
    available_tools: List[str] = field(default_factory=list)
    completed_episodes: int = 0
    expert_history: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "weak_areas": self.weak_areas,
            "skill_level": self.skill_level,
            "recent_success_rate": self.recent_success_rate,
            "overall_success_rate": self.overall_success_rate,
            "avg_reward": self.avg_reward,
            "available_tools": self.available_tools,
            "completed_episodes": self.completed_episodes,
            "expert_history": self.expert_history[-5:],
        }


@dataclass
class SelectionResult:
    """Result of expert selection"""
    selected_expert_id: str
    score: float
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    reasoning: str = ""
    alternatives: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_expert_id": self.selected_expert_id,
            "score": self.score,
            "score_breakdown": self.score_breakdown,
            "reasoning": self.reasoning,
            "alternatives": self.alternatives,
        }


class ExpertSelector:
    """Selects the best expert for current learner state"""
    
    def __init__(
        self,
        strategy: SelectionStrategy = SelectionStrategy.HYBRID,
        exploration_rate: float = 0.2,
    ):
        self.strategy = strategy
        self.exploration_rate = exploration_rate
        self.selection_history: List[SelectionResult] = []
    
    def select(
        self,
        learner_state: LearnerState,
        available_experts: List,
    ) -> SelectionResult:
        """Select the best expert for current learner state"""
        if not available_experts:
            raise ValueError("No experts available for selection")
        
        scored_experts = []
        for expert in available_experts:
            score_result = self._score_expert(expert, learner_state)
            scored_experts.append((expert, score_result))
        
        scored_experts.sort(key=lambda x: x[1].score, reverse=True)
        
        selected_expert, selected_result = self._apply_exploration(
            scored_experts, learner_state
        )
        
        alternatives = [e.id for e, _ in scored_experts[1:4]]
        selected_result.alternatives = alternatives
        self.selection_history.append(selected_result)
        
        return SelectionResult(
            selected_expert_id=selected_expert.id,
            score=selected_result.score,
            score_breakdown=selected_result.score_breakdown,
            reasoning=selected_result.reasoning,
            alternatives=alternatives,
        )
    
    def _score_expert(self, expert, learner_state: LearnerState) -> SelectionResult:
        """Score a single expert against learner state"""
        breakdown = {}
        
        # 1. Weak area matching (0-40)
        weak_area_score = self._calculate_weak_area_score(
            expert.target_weak_areas, 
            learner_state.weak_areas
        )
        breakdown["weak_area"] = weak_area_score * 40
        
        # 2. Skill level (0-20)
        skill_score = self._calculate_skill_level_score(
            expert.skill_level,
            learner_state.skill_level
        )
        breakdown["skill_level"] = skill_score * 20
        
        # 3. Tool availability (0-20)
        tool_score = self._calculate_tool_score(
            expert.required_tools,
            learner_state.available_tools
        )
        breakdown["tools"] = tool_score * 20
        
        # 4. Performance (0-20)
        perf_score = self._calculate_performance_score(expert, learner_state)
        breakdown["performance"] = perf_score * 20
        
        total_score = sum(breakdown.values()) / 100.0
        
        return SelectionResult(
            selected_expert_id=expert.id,
            score=total_score,
            score_breakdown=breakdown,
            reasoning=self._generate_reasoning(expert, breakdown, total_score),
        )
    
    def _calculate_weak_area_score(self, expert_areas: List[str], learner_areas: List[str]) -> float:
        if not learner_areas or not expert_areas:
            return 0.5
        learner_lower = [a.lower() for a in learner_areas]
        matches = sum(1 for ea in expert_areas if ea.lower() in learner_lower)
        return min(1.0, matches * 0.5)
    
    def _calculate_skill_level_score(self, expert_level: str, learner_level: str) -> float:
        level_order = {"beginner": 0, "intermediate": 1, "advanced": 2}
        expert_idx = level_order.get(expert_level, 1)
        learner_idx = level_order.get(learner_level, 0)
        if expert_idx == learner_idx + 1:
            return 1.0
        elif expert_idx == learner_idx:
            return 0.7
        elif expert_idx > learner_idx + 1:
            return 0.3
        return 0.5
    
    def _calculate_tool_score(self, required_tools: List[str], available_tools: List[str]) -> float:
        if not required_tools:
            return 1.0
        if not available_tools:
            return 0.0
        available_set = set(available_tools)
        required_set = set(required_tools)
        if required_set.issubset(available_set):
            return 1.0
        matches = len(required_set & available_set)
        return matches / len(required_set)
    
    def _calculate_performance_score(self, expert, learner_state: LearnerState) -> float:
        success_rate = getattr(expert, "success_rate", 0.5)
        if expert.id not in learner_state.expert_history:
            exploration_bonus = self.exploration_rate * (1.0 - min(1.0, learner_state.completed_episodes / 20))
            return min(1.0, success_rate + exploration_bonus)
        return success_rate
    
    def _apply_exploration(self, scored_experts, learner_state: LearnerState):
        if random.random() < self.exploration_rate:
            candidates = scored_experts[:min(3, len(scored_experts))]
            selected = random.choice(candidates)
            selected[1].reasoning += " [EXPLORATION]"
            return selected
        return scored_experts[0]
    
    def _generate_reasoning(self, expert, breakdown: Dict[str, float], total_score: float) -> str:
        if breakdown["weak_area"] >= 30:
            assessment = f"targets weak areas: {expert.target_weak_areas[:2]}"
        elif breakdown["skill_level"] >= 15:
            assessment = f"matches skill level ({expert.skill_level})"
        elif breakdown["tools"] >= 15:
            assessment = "uses available tools"
        else:
            assessment = "default selection"
        
        level = "excellent" if total_score >= 0.8 else "good" if total_score >= 0.6 else "moderate"
        return f"{level} match: {assessment}"
    
    def get_selection_statistics(self) -> Dict[str, Any]:
        if not self.selection_history:
            return {"total_selections": 0}
        expert_counts = {}
        avg_score = 0
        for result in self.selection_history:
            expert_counts[result.selected_expert_id] = expert_counts.get(result.selected_expert_id, 0) + 1
            avg_score += result.score
        return {
            "total_selections": len(self.selection_history),
            "expert_distribution": expert_counts,
            "average_score": avg_score / len(self.selection_history),
        }
