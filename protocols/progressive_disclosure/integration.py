"""Progressive Disclosure Integration - Bridge with existing system

Integrates progressive disclosure with:
- Expert Pool (gets task requirements + weak areas)
- Difficulty Controller (adjusts difficulty)
- Context Discloser (reveals context)
- Producer-Reviewer Protocol (generates tasks)

Flow:
    ExpertPool.select_expert()
         ↓
    DifficultyController.adjust() 
         ↓
    ContextDiscloser.compute_disclosure()
         ↓
    TaskConfig (complete specification)
         ↓
    Producer-Reviewer Loop
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from protocols.progressive_disclosure.controller import (
    DifficultyController, DifficultyConfig, DifficultyDimensions,
    PerformanceSignal, DifficultyAdjustment,
)
from protocols.progressive_disclosure.disclosure import (
    ContextDiscloser, DisclosurePolicy, ContextLayer, ContextType,
)
from protocols.progressive_disclosure.task_config import TaskConfig, TaskConfigBuilder


@dataclass
class DisclosureSession:
    """A single disclosure session (one task)"""
    session_id: str
    expert_id: str
    difficulty_before: DifficultyDimensions
    difficulty_after: DifficultyDimensions
    adjustment: DifficultyAdjustment
    disclosure: Dict[str, List[str]]
    task_config: TaskConfig
    signal: Optional[PerformanceSignal] = None


@dataclass
class ProgressiveDisclosureConfig:
    """Configuration for progressive disclosure integration"""
    # Difficulty settings
    initial_difficulty: float = 0.3
    difficulty_config: DifficultyConfig = None
    
    # Context disclosure settings
    disclosure_policy: DisclosurePolicy = None
    
    # Expert pool integration
    use_expert_pool: bool = True
    
    # Fallback
    fallback_to_stage_based: bool = True


class ProgressiveDisclosureIntegration:
    """
    Integration layer for progressive disclosure
    
    Bridges:
    - DifficultyController: Real-time difficulty adjustment
    - ContextDiscloser: Progressive context release
    - ExpertPool: Task-specific requirements
    - Producer-Reviewer: Task generation
    """
    
    def __init__(
        self,
        config: ProgressiveDisclosureConfig = None,
        difficulty_controller: DifficultyController = None,
        context_discloser: ContextDiscloser = None,
    ):
        self.config = config or ProgressiveDisclosureConfig()
        
        # Initialize components
        self.difficulty_controller = difficulty_controller or DifficultyController(
            config=self.config.difficulty_config or DifficultyConfig()
        )
        self.context_discloser = context_discloser or ContextDiscloser(
            policy=self.config.disclosure_policy or DisclosurePolicy()
        )
        
        # Session tracking
        self.sessions: List[DisclosureSession] = []
        self.current_session: Optional[DisclosureSession] = None
    
    def prepare_task(
        self,
        expert_id: str,
        objectives: List[str],
        requirements: List[str] = None,
        weak_areas: List[str] = None,
        stage: str = "intermediate",
        round_num: int = 1,
        context_layers: List[ContextLayer] = None,
    ) -> TaskConfig:
        """
        Prepare task configuration for a round
        
        Flow:
        1. Get current difficulty from controller
        2. Register context layers
        3. Compute disclosure
        4. Build task config
        
        Args:
            expert_id: Selected expert ID
            objectives: Task objectives
            requirements: Task requirements
            weak_areas: Learner's weak areas
            stage: Current learning stage
            round_num: Current review round
            context_layers: Expert-specific context layers
        
        Returns:
            TaskConfig ready for learner
        """
        requirements = requirements or []
        weak_areas = weak_areas or []
        
        # Step 1: Get current difficulty
        current_difficulty = self.difficulty_controller.get_current_difficulty()
        
        # Step 2: Register context layers
        self.context_discloser.reset()
        if context_layers:
            self.context_discloser.register_layers(context_layers)
        else:
            # Default context layers
            self._register_default_layers(expert_id)
        
        # Step 3: Get recent performance signal
        recent_score = 0.5
        if self.difficulty_controller.signal_history:
            recent_score = self.difficulty_controller.signal_history[-1].score
        
        # Step 4: Compute disclosure
        disclosure = self.context_discloser.compute_disclosure(
            context_difficulty=current_difficulty.context,
            current_score=recent_score,
            round_num=round_num,
            weak_areas=weak_areas,
        )
        
        # Step 5: Build task config
        task_config = (
            TaskConfigBuilder()
            .task_id(f"{expert_id}-r{round_num}")
            .description(objectives[0] if objectives else "Task")
            .difficulty({
                "complexity": current_difficulty.complexity,
                "constraints": current_difficulty.constraints,
                "context": current_difficulty.context,
                "tools": current_difficulty.tools,
                "scope": current_difficulty.scope,
            })
            .from_disclosure(disclosure)
            .objectives(objectives)
            .requirements(requirements)
            .expert(expert_id)
            .stage(stage)
            .round(round_num)
            .build()
        )
        
        # Store session
        self.current_session = DisclosureSession(
            session_id=task_config.task_id,
            expert_id=expert_id,
            difficulty_before=current_difficulty,
            difficulty_after=current_difficulty,  # Will update after signal
            adjustment=None,  # Will add after adjustment
            disclosure=disclosure,
            task_config=task_config,
        )
        
        return task_config
    
    def record_result(
        self,
        score: float,
        success: bool,
        time_used: float,
        time_budget: float,
        error_count: int = 0,
        tool_calls: int = 0,
    ):
        """
        Record task result and adjust difficulty
        
        After recording, the controller will adjust difficulty
        for the next task.
        """
        if not self.current_session:
            return
        
        # Create performance signal
        # Get recent keep_rate from history
        keep_rate = 0.5
        if len(self.difficulty_controller.signal_history) >= 3:
            recent = self.difficulty_controller.signal_history[-3:]
            keep_rate = sum(1 for s in recent if s.success) / len(recent)
        
        signal = PerformanceSignal(
            score=score,
            keep_rate=keep_rate,
            time_used=time_used,
            time_budget=time_budget,
            error_count=error_count,
            tool_calls=tool_calls,
            success=success,
            round_num=self.current_session.task_config.round_num,
        )
        
        # Record signal
        self.difficulty_controller.record_signal(signal)
        
        # Adjust difficulty
        adjustment = self.difficulty_controller.adjust()
        
        # Update session
        self.current_session.signal = signal
        self.current_session.difficulty_after = self.difficulty_controller.get_current_difficulty()
        self.current_session.adjustment = adjustment
        self.sessions.append(self.current_session)
        
        return adjustment
    
    def _register_default_layers(self, expert_id: str):
        """Register default context layers for an expert"""
        # These would typically come from the expert definition
        layers = [
            ContextLayer(
                type=ContextType.HINTS,
                content="Start by identifying the key components.",
                importance=0.8,
                condition="beginner",
            ),
            ContextLayer(
                type=ContextType.HINTS,
                content="Consider using the tool's --help flag.",
                importance=0.7,
            ),
            ContextLayer(
                type=ContextType.EXAMPLES,
                content="Example: git status shows current branch.",
                importance=0.6,
            ),
            ContextLayer(
                type=ContextType.SCAFFOLD,
                content="Step 1: Check current state\nStep 2: Make changes\nStep 3: Verify",
                importance=0.5,
                condition="intermediate",
            ),
            ContextLayer(
                type=ContextType.DOCUMENTATION,
                content="Refer to official documentation for advanced usage.",
                importance=0.4,
                condition="advanced",
            ),
        ]
        
        self.context_discloser.register_layers(layers)
    
    def get_current_difficulty(self) -> DifficultyDimensions:
        """Get current difficulty settings"""
        return self.difficulty_controller.get_current_difficulty()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get integration statistics"""
        diff_stats = self.difficulty_controller.get_statistics()
        disc_stats = self.context_discloser.get_statistics()
        
        return {
            "difficulty": diff_stats,
            "disclosure": disc_stats,
            "total_sessions": len(self.sessions),
            "current_difficulty": self.difficulty_controller.get_current_difficulty().to_dict(),
            "signals_recorded": len(self.difficulty_controller.signal_history),
        }
    
    def print_summary(self):
        """Print human-readable summary"""
        stats = self.get_statistics()
        
        print("\n" + "=" * 60)
        print("Progressive Disclosure Summary")
        print("=" * 60)
        
        diff = stats["current_difficulty"]
        print(f"\nCurrent Difficulty (overall: {diff.get('overall', 0):.2f}):")
        print(f"  Complexity:   {diff.get('complexity', 0):.2f}")
        print(f"  Constraints: {diff.get('constraints', 0):.2f}")
        print(f"  Context:     {diff.get('context', 0):.2f}")
        print(f"  Tools:       {diff.get('tools', 0):.2f}")
        print(f"  Scope:       {diff.get('scope', 0):.2f}")
        
        print(f"\nSessions: {stats['total_sessions']}")
        print(f"Signals:  {stats['difficulty'].get('signals_recorded', 0)}")
        print(f"Adjustments: {stats['difficulty'].get('total_adjustments', 0)}")
        
        print("=" * 60)
