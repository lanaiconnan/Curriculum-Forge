"""Expert Pool Integration - Bridge Expert Pool with existing Curriculum-Forge

Integrates Expert Pool selection with:
- Agent A (Generator)
- Agent B (Learner)  
- Producer-Reviewer Protocol
- FeedbackLoop

Flow:
  FeedbackLoop/Analyst → LearnerState 
    → ExpertSelector.select() 
    → Selected Expert 
    → Specialized TrainingEnvironment 
    → Producer-Reviewer Loop
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from protocols.expert_pool.pool import ExpertPool, ExpertRegistry
from protocols.expert_pool.selector import ExpertSelector, LearnerState, SelectionStrategy, SelectionResult
from protocols.producer_reviewer.feedback_loop import FeedbackLoop


@dataclass
class ExpertPoolConfig:
    """Configuration for Expert Pool integration"""
    strategy: str = "hybrid"  # weak_area_first, performance_based, exploration, hybrid
    exploration_rate: float = 0.2
    min_weak_areas_for_selection: int = 1
    fallback_to_stage_based: bool = True


@dataclass
class ExpertSelectionResult:
    """Result of expert selection process"""
    expert_id: str
    expert_name: str
    category: str
    score: float
    reasoning: str
    alternatives: List[str]
    environment: Dict[str, Any]


class ExpertPoolIntegration:
    """Integration layer combining Expert Pool with Curriculum-Forge
    
    Bridges the gap between:
    - FeedbackLoop's weak area analysis
    - ExpertSelector's dynamic selection
    - Agent A's environment generation
    - Producer-Reviewer's review loop
    """
    
    def __init__(
        self,
        agent_a=None,
        agent_b=None,
        feedback_loop: FeedbackLoop = None,
        config: ExpertPoolConfig = None,
    ):
        self.agent_a = agent_a
        self.agent_b = agent_b
        self.feedback_loop = feedback_loop or FeedbackLoop()
        self.config = config or ExpertPoolConfig()
        
        # Initialize Expert Pool
        self.pool = ExpertPool(ExpertRegistry())
        
        # Initialize Selector
        strategy = SelectionStrategy.from_string(self.config.strategy)
        self.selector = ExpertSelector(
            strategy=strategy,
            exploration_rate=self.config.exploration_rate,
        )
        
        # State tracking
        self.current_learner_state: Optional[LearnerState] = None
        self.selection_history: List[ExpertSelectionResult] = []
    
    def update_learner_state(
        self,
        weak_areas: List[str] = None,
        skill_level: str = "beginner",
        recent_success_rate: float = 0.5,
        overall_success_rate: float = 0.5,
        avg_reward: float = 0.5,
        available_tools: List[str] = None,
        completed_episodes: int = 0,
    ):
        """Update the learner state from external sources"""
        
        # Get expert history from previous selections
        expert_history = [s.expert_id for s in self.selection_history]
        
        self.current_learner_state = LearnerState(
            weak_areas=weak_areas or [],
            skill_level=skill_level,
            recent_success_rate=recent_success_rate,
            overall_success_rate=overall_success_rate,
            avg_reward=avg_reward,
            available_tools=available_tools or ["git", "moon"],
            completed_episodes=completed_episodes,
            expert_history=expert_history,
        )
        
        return self.current_learner_state
    
    def update_from_feedback_loop(self) -> LearnerState:
        """Extract learner state from FeedbackLoop analysis"""
        
        if not self.feedback_loop.history.entries:
            # Default state if no history
            return self.update_learner_state()
        
        # Get weak areas from feedback patterns
        patterns = self.feedback_loop.history.patterns
        weak_areas = [p.pattern_type for p in patterns[:3]]
        
        # Get performance metrics from session
        session = self.feedback_loop.history.entries
        if session:
            recent_success = sum(1 for e in session[-5:] if e.verdict == "accept") / min(5, len(session))
            avg_reward = sum(e.score for e in session) / len(session)
        else:
            recent_success = 0.5
            avg_reward = 0.5
        
        # Determine skill level from episode count
        completed = len(session)
        if completed < 5:
            skill_level = "beginner"
        elif completed < 15:
            skill_level = "intermediate"
        else:
            skill_level = "advanced"
        
        return self.update_learner_state(
            weak_areas=weak_areas,
            skill_level=skill_level,
            recent_success_rate=recent_success,
            avg_reward=avg_reward,
            completed_episodes=completed,
        )
    
    def select_expert(
        self,
        learner_state: LearnerState = None,
    ) -> ExpertSelectionResult:
        """
        Select the best expert for current learner state
        
        Args:
            learner_state: Override learner state (uses current if None)
        
        Returns:
            ExpertSelectionResult with selected expert and generated environment
        """
        # Use provided state or current state
        state = learner_state or self.current_learner_state
        
        if state is None:
            state = self.update_from_feedback_loop()
        
        # Check if we have enough weak areas
        if len(state.weak_areas) < self.config.min_weak_areas_for_selection:
            if self.config.fallback_to_stage_based:
                # Fallback: select based on skill level
                state.weak_areas = self._infer_weak_areas_from_level(state.skill_level)
        
        # Get available experts
        available_experts = self.pool.list_experts()
        
        # Run selection
        selection = self.selector.select(state, available_experts)
        
        # Get expert and generate environment
        expert = self.pool.get_expert(selection.selected_expert_id)
        
        if expert and hasattr(expert, "generate_environment"):
            environment = expert.generate_environment(
                stage=state.skill_level,
                weak_areas=state.weak_areas,
                context={"selection": selection.to_dict()},
            )
        else:
            environment = self._default_environment(state)
        
        # Update expert stats after selection
        self.pool.update_expert_stats(expert.id, success=None)  # Unknown yet
        
        # Record selection
        result = ExpertSelectionResult(
            expert_id=expert.id if expert else selection.selected_expert_id,
            expert_name=expert.name if expert else selection.selected_expert_id,
            category=expert.category.value if expert else "unknown",
            score=selection.score,
            reasoning=selection.reasoning,
            alternatives=selection.alternatives,
            environment=environment,
        )
        
        self.selection_history.append(result)
        
        return result
    
    def record_result(self, expert_id: str, success: bool):
        """Record the result of an expert's training episode"""
        self.pool.update_expert_stats(expert_id, success)
    
    def _infer_weak_areas_from_level(self, skill_level: str) -> List[str]:
        """Infer default weak areas based on skill level"""
        mapping = {
            "beginner": ["tool_usage", "basic_operations"],
            "intermediate": ["tool_coordination", "error_handling"],
            "advanced": ["performance", "edge_cases", "optimization"],
        }
        return mapping.get(skill_level, ["general"])
    
    def _default_environment(self, state: LearnerState) -> Dict[str, Any]:
        """Generate default environment if expert fails"""
        return {
            "expert_id": "default",
            "expert_name": "Default Generalist",
            "category": "general",
            "tasks": [
                {
                    "id": "default_task1",
                    "type": "general",
                    "description": "General practice task",
                    "target": "Complete successfully",
                    "tools_required": state.available_tools,
                }
            ],
            "difficulty": {"beginner": 0.3, "intermediate": 0.5, "advanced": 0.7}.get(state.skill_level, 0.5),
            "tools": state.available_tools,
            "reward_config": {"r_format_scale": 1.0, "r_correct_scale": 3.0, "stage": state.skill_level},
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get integration statistics"""
        return {
            "expert_pool": self.pool.get_statistics(),
            "selector": self.selector.get_selection_statistics(),
            "total_selections": len(self.selection_history),
            "current_state": self.current_learner_state.to_dict() if self.current_learner_state else None,
        }
    
    def print_summary(self):
        """Print human-readable summary"""
        stats = self.get_statistics()
        print("\n" + "=" * 60)
        print("Expert Pool Integration Summary")
        print("=" * 60)
        print(f"Total Selections:    {stats['total_selections']}")
        print(f"Pool Experts:       {stats['expert_pool']['total_experts']}")
        
        if stats['selector'].get('expert_distribution'):
            print("\nExpert Usage Distribution:")
            for expert_id, count in stats['selector']['expert_distribution'].items():
                print(f"  {expert_id}: {count}")
        
        if self.current_learner_state:
            print(f"\nCurrent Learner State:")
            print(f"  Skill Level:    {self.current_learner_state.skill_level}")
            print(f"  Weak Areas:     {self.current_learner_state.weak_areas}")
            print(f"  Success Rate:   {self.current_learner_state.recent_success_rate:.1%}")
        
        print("=" * 60)
