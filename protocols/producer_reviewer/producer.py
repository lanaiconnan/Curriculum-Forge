"""Producer Agent - Task generation with progressive disclosure

Integrates with Agent A (Generator) to create tasks with graduated context hints.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class DifficultyLevel(Enum):
    """Learning difficulty stages"""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate" 
    ADVANCED = "advanced"


@dataclass
class ProductionPlan:
    """Plan for task production"""
    task_id: str
    difficulty: DifficultyLevel
    objectives: List[str]
    context_layers: List[Dict[str, Any]]  # Progressive context
    hints: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    
    def get_context_for_round(self, round_num: int) -> Dict[str, Any]:
        """Get context with progressive disclosure
        
        Round 1: Minimal context (challenge first)
        Round 2: Add hints if struggling
        Round 3: Full context as last resort
        """
        if round_num <= 1:
            return {"level": "minimal", "hints": [], "examples": []}
        elif round_num == 2:
            return {
                "level": "moderate",
                "hints": self.hints[:1] if self.hints else [],
                "examples": self.examples[:1] if self.examples else [],
            }
        else:
            return {
                "level": "full",
                "hints": self.hints,
                "examples": self.examples,
            }


@dataclass
class ProducedTask:
    """A task ready for Agent B execution"""
    id: str
    description: str
    requirements: List[str]
    difficulty: float
    stage: str
    context: Dict[str, Any]
    max_tool_calls: int
    timeout: int
    quality_gates: List[str] = field(default_factory=list)
    
    def to_producer_task(self) -> "ProducerTask":
        """Convert to protocol's ProducerTask"""
        from .protocol import ProducerTask, QualityGate
        
        gates = []
        for gate_str in self.quality_gates:
            try:
                gates.append(QualityGate[gate_str.upper()])
            except KeyError:
                pass
        
        return ProducerTask(
            id=self.id,
            description=self.description,
            requirements=self.requirements,
            context=self.context,
            difficulty=self.difficulty,
            stage=self.stage,
            max_tool_calls=self.max_tool_calls,
            timeout=self.timeout,
            quality_gates=gates,
        )


class ProducerAgent:
    """
    Producer Agent - Generates tasks with progressive disclosure
    
    Integrates with Agent A (Generator) to:
    1. Create tasks at appropriate difficulty
    2. Control context disclosure based on learner progress
    3. Incorporate feedback from review rounds
    """
    
    def __init__(
        self,
        base_difficulty: float = 0.3,
        difficulty_growth: float = 0.15,
    ):
        self.base_difficulty = base_difficulty
        self.difficulty_growth = difficulty_growth
        self.task_history: List[ProducedTask] = []
    
    def create_task(
        self,
        stage: str,
        objectives: List[str],
        context: Dict[str, Any] = None,
        previous_attempts: List[Dict[str, Any]] = None,
    ) -> ProducedTask:
        """
        Create a new task for Agent B
        
        Args:
            stage: Learning stage (beginner/intermediate/advanced)
            objectives: What the task should achieve
            context: Additional context to include
            previous_attempts: Failed attempts for progressive hint disclosure
        
        Returns:
            ProducedTask ready for execution
        """
        previous_attempts = previous_attempts or []
        
        # Calculate difficulty based on stage
        difficulty = self._calculate_difficulty(stage, len(previous_attempts))
        
        # Build progressive context
        context_layers = self._build_progressive_context(
            stage, previous_attempts, context
        )
        
        # Generate requirements from objectives
        requirements = self._generate_requirements(objectives, stage)
        
        # Determine quality gates based on stage
        quality_gates = self._get_quality_gates(stage)
        
        task = ProducedTask(
            id=f"task-{len(self.task_history) + 1}",
            description=self._format_description(objectives),
            requirements=requirements,
            difficulty=difficulty,
            stage=stage,
            context=context_layers,
            max_tool_calls=self._get_max_tool_calls(stage),
            timeout=self._get_timeout(stage),
            quality_gates=quality_gates,
        )
        
        self.task_history.append(task)
        return task
    
    def revise_task(
        self,
        original_task: ProducedTask,
        feedback: str,
        revisions_requested: List[str],
    ) -> ProducedTask:
        """
        Create revised task based on review feedback
        
        Args:
            original_task: Task that was rejected/revised
            feedback: Reviewer feedback
            revisions_requested: Specific revisions needed
        
        Returns:
            Revised task with incorporated feedback
        """
        # Increment task ID
        new_id = f"{original_task.id}-rev{len(self.task_history) + 1}"
        
        # Add feedback to context
        new_context = original_task.context.copy()
        new_context["feedback"] = feedback
        new_context["revision_count"] = new_context.get("revision_count", 0) + 1
        
        # Add hints from feedback if this is 2nd+ attempt
        if new_context.get("revision_count", 0) > 0:
            hints = new_context.get("hints", [])
            hints.append(f"Hint from review: {feedback[:100]}")
            new_context["hints"] = hints
        
        # Requirements may need adjustment
        new_requirements = original_task.requirements + revisions_requested
        
        return ProducedTask(
            id=new_id,
            description=original_task.description,
            requirements=new_requirements,
            difficulty=original_task.difficulty * 0.9,  # Slightly easier on revision
            stage=original_task.stage,
            context=new_context,
            max_tool_calls=original_task.max_tool_calls + 2,  # More flexibility
            timeout=original_task.timeout,
            quality_gates=original_task.quality_gates,
        )
    
    def _calculate_difficulty(self, stage: str, attempt_count: int) -> float:
        """Calculate task difficulty"""
        base = {
            "beginner": 0.3,
            "intermediate": 0.5,
            "advanced": 0.7,
        }.get(stage, 0.5)
        
        # Decrease slightly with more attempts (scaffolded learning)
        penalty = attempt_count * 0.05
        return max(0.1, base - penalty)
    
    def _build_progressive_context(
        self,
        stage: str,
        previous_attempts: List[Dict[str, Any]],
        additional_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build context with progressive disclosure"""
        context = {
            "stage": stage,
            "attempt_count": len(previous_attempts),
        }
        
        # Add hints based on previous failures
        if previous_attempts:
            context["previous_failures"] = [
                att.get("feedback", "") for att in previous_attempts[-2:]
            ]
        
        # Add any additional context
        if additional_context:
            context.update(additional_context)
        
        # Progressive hints
        if stage == "beginner":
            context["hints"] = [
                "Start with simple tools first",
                "Check the documentation for usage examples",
            ]
        elif stage == "intermediate":
            context["hints"] = [
                "Consider combining multiple tools",
                "Think about edge cases",
            ]
        else:
            context["hints"] = [
                "Optimize for performance",
                "Handle errors gracefully",
            ]
        
        return context
    
    def _generate_requirements(self, objectives: List[str], stage: str) -> List[str]:
        """Generate requirements from objectives"""
        base_req = [f"Achieve: {obj}" for obj in objectives]
        
        # Add stage-specific requirements
        if stage == "beginner":
            base_req.append("Use at least one tool correctly")
        elif stage == "intermediate":
            base_req.append("Combine at least 2 tools")
            base_req.append("Handle at least one edge case")
        else:
            base_req.append("Optimize for performance")
            base_req.append("Include error handling")
            base_req.append("Document the solution")
        
        return base_req
    
    def _format_description(self, objectives: List[str]) -> str:
        """Format task description"""
        if len(objectives) == 1:
            return objectives[0]
        return f"Complete the following objectives: {'; '.join(objectives)}"
    
    def _get_quality_gates(self, stage: str) -> List[str]:
        """Determine quality gates by stage"""
        base = ["format", "completeness"]
        
        if stage == "beginner":
            return base + ["accuracy"]
        elif stage == "intermediate":
            return base + ["accuracy", "style"]
        else:
            return base + ["accuracy", "performance", "style"]
    
    def _get_max_tool_calls(self, stage: str) -> int:
        """Get max tool calls allowed"""
        return {"beginner": 10, "intermediate": 15, "advanced": 20}.get(stage, 10)
    
    def _get_timeout(self, stage: str) -> int:
        """Get timeout in seconds"""
        return {"beginner": 180, "intermediate": 300, "advanced": 600}.get(stage, 300)
    
    def get_task_statistics(self) -> Dict[str, Any]:
        """Get statistics about generated tasks"""
        if not self.task_history:
            return {"total_tasks": 0}
        
        return {
            "total_tasks": len(self.task_history),
            "by_stage": self._count_by_stage(),
            "average_difficulty": sum(t.difficulty for t in self.task_history) / len(self.task_history),
        }
    
    def _count_by_stage(self) -> Dict[str, int]:
        """Count tasks by stage"""
        counts = {}
        for task in self.task_history:
            counts[task.stage] = counts.get(task.stage, 0) + 1
        return counts
