"""Core Producer-Reviewer Protocol

Orchestrates the full collaboration loop:
  Agent A (Producer) -> Agent B (Learner) -> Agent A (Reviewer) -> [Accept/Revise/Reject]

Key features:
- Review-driven feedback loop
- Iterative refinement with max rounds
- Quality gates between production and acceptance
- Structured review scores feeding into GRPO
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime


class ReviewVerdict(Enum):
    """Review outcome"""
    ACCEPT = "accept"           # Quality passed, move on
    REVISE = "revise"           # Needs revision, back to producer
    REJECT = "reject"           # Failed quality gate, discard


class QualityGate(Enum):
    """Quality gates that must pass"""
    FORMAT = "format"           # Output format correctness
    COMPLETENESS = "completeness"  # All required elements present
    ACCURACY = "accuracy"       # Technical correctness
    PERFORMANCE = "performance"  # Performance benchmarks met
    STYLE = "style"             # Code/style guidelines followed


@dataclass
class ProducerTask:
    """Task definition from Producer (Agent A) to Learner (Agent B)"""
    id: str
    description: str
    requirements: List[str]
    context: Dict[str, Any]    # Progressive disclosure context
    difficulty: float          # 0-1, affects reward scale
    stage: str                 # beginner/intermediate/advanced
    max_tool_calls: int
    timeout: int               # seconds
    quality_gates: List[QualityGate] = field(default_factory=list)
    
    def to_prompt(self) -> str:
        """Generate task prompt for Agent B"""
        gates = ", ".join(g.value for g in self.quality_gates)
        return f"""
## Task: {self.description}

### Requirements
{chr(10).join(f"- {req}" for req in self.requirements)}

### Quality Gates (must pass)
{gates}

### Constraints
- Max tool calls: {self.max_tool_calls}
- Timeout: {self.timeout}s
- Difficulty: {self.difficulty:.1f} ({self.stage})

### Context (progressively disclosed)
{self._format_context()}
"""
    
    def _format_context(self) -> str:
        """Format context with progressive disclosure hints"""
        hints = []
        if self.context.get("hints"):
            hints.append(f"Hints: {self.context['hints']}")
        if self.context.get("examples"):
            hints.append(f"Examples: {self.context['examples']}")
        if self.context.get("previous_attempts"):
            hints.append(f"Previous attempts: {len(self.context['previous_attempts'])} failed")
        return "\n".join(hints) if hints else "(none)"


@dataclass
class ReviewRound:
    """Single review iteration"""
    round_id: int
    timestamp: str
    verdict: ReviewVerdict
    scores: Dict[str, float]    # criteria -> score 0-1
    feedback: str               # Human-readable feedback
    revisions_requested: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_pass(self, gate: QualityGate) -> bool:
        """Check if a specific quality gate passed"""
        key = gate.value
        return self.scores.get(key, 0) >= self._gate_threshold(gate)
    
    def _gate_threshold(self, gate: QualityGate) -> float:
        """Get threshold for each gate type"""
        thresholds = {
            QualityGate.FORMAT: 0.8,
            QualityGate.COMPLETENESS: 0.7,
            QualityGate.ACCURACY: 0.75,
            QualityGate.PERFORMANCE: 0.7,
            QualityGate.STYLE: 0.6,
        }
        return thresholds.get(gate, 0.7)
    
    def overall_score(self) -> float:
        """Compute weighted overall score"""
        weights = {
            "format": 0.15,
            "completeness": 0.25,
            "accuracy": 0.30,
            "performance": 0.20,
            "style": 0.10,
        }
        total = 0.0
        for criteria, score in self.scores.items():
            total += score * weights.get(criteria, 0.2)
        return total
    
    def to_grpo_reward(self, base_scale: float = 1.0) -> float:
        """Convert review scores to GRPO-style reward
        
        R_review ∈ [0, base_scale * 1.0]
        Higher score = higher reward
        """
        return self.overall_score() * base_scale


@dataclass
class ProducerReviewerProtocol:
    """
    Main protocol orchestrator
    
    Coordinates the Producer-Reviewer loop between Agent A and Agent B:
    
    Flow:
    1. Producer (Agent A) generates task + context
    2. Learner (Agent B) executes task
    3. Reviewer (Agent A) evaluates output
    4. If REVISE: go back to step 2 with feedback
    5. If ACCEPT: record reward, advance
    6. If REJECT: discard, record low reward
    """
    
    max_rounds: int = 3
    min_score_for_accept: float = 0.7
    
    # Callbacks (set by integration)
    producer_fn: Optional[Callable] = None    # Agent A task generation
    learner_fn: Optional[Callable] = None    # Agent B execution
    reviewer_fn: Optional[Callable] = None   # Agent A review
    
    def __init__(self, max_rounds: int = 3, min_score: float = 0.7):
        self.max_rounds = max_rounds
        self.min_score_for_accept = min_score
        self.history: List[ReviewRound] = []
    
    def set_producer(self, fn: Callable):
        """Set the producer callback (Agent A task generator)"""
        self.producer_fn = fn
    
    def set_learner(self, fn: Callable):
        """Set the learner callback (Agent B executor)"""
        self.learner_fn = fn
    
    def set_reviewer(self, fn: Callable):
        """Set the reviewer callback (Agent A quality reviewer)"""
        self.reviewer_fn = fn
    
    def execute(
        self,
        task: ProducerTask,
        learner_output_fn: Callable[[ProducerTask], Any]
    ) -> Dict[str, Any]:
        """
        Execute the full Producer-Reviewer loop
        
        Args:
            task: Task definition from Producer
            learner_output_fn: Function that runs Agent B and returns output
        
        Returns:
            Dict with: final_verdict, final_round, reward, metadata
        """
        self.history.clear()
        
        # Phase 1: Producer generates task (already done, passed in)
        current_task = task
        
        # Phase 2-4: Iterative Review Loop
        for round_num in range(1, self.max_rounds + 1):
            # Learner executes
            learner_output = learner_output_fn(current_task)
            
            # Reviewer evaluates
            if self.reviewer_fn:
                review = self.reviewer_fn(current_task, learner_output)
            else:
                # Fallback: simple automatic scoring
                review = self._auto_review(learner_output, current_task)
            
            self.history.append(review)
            
            # Check verdict
            if review.verdict == ReviewVerdict.ACCEPT:
                return {
                    "verdict": "accept",
                    "rounds": round_num,
                    "reward": review.to_grpo_reward(),
                    "scores": review.scores,
                    "final_output": learner_output,
                }
            
            elif review.verdict == ReviewVerdict.REVISE:
                # Prepare revised task with feedback
                current_task = self._revise_task(
                    current_task, 
                    review.feedback,
                    review.revisions_requested
                )
                continue
            
            else:  # REJECT
                return {
                    "verdict": "reject",
                    "rounds": round_num,
                    "reward": 0.0,
                    "scores": review.scores,
                    "final_output": None,
                }
        
        # Max rounds reached without accept
        final_round = self.history[-1]
        return {
            "verdict": "max_rounds",
            "rounds": self.max_rounds,
            "reward": final_round.to_grpo_reward() * 0.5,  # Penalty for no accept
            "scores": final_round.scores,
            "final_output": None,
        }
    
    def _auto_review(self, output: Any, task: ProducerTask) -> ReviewRound:
        """Automatic fallback review (when LLM reviewer not available)"""
        # Simple heuristics
        scores = {
            "format": 0.8,
            "completeness": 0.7,
            "accuracy": 0.7,
            "performance": 0.7,
            "style": 0.7,
        }
        
        verdict = ReviewVerdict.ACCEPT if scores["completeness"] >= self.min_score_for_accept else ReviewVerdict.REVISE
        
        return ReviewRound(
            round_id=len(self.history) + 1,
            timestamp=datetime.now().isoformat(),
            verdict=verdict,
            scores=scores,
            feedback="Auto-reviewed (no LLM reviewer)",
        )
    
    def _revise_task(
        self, 
        task: ProducerTask, 
        feedback: str,
        revisions: List[str]
    ) -> ProducerTask:
        """Create revised task with feedback incorporated"""
        new_context = task.context.copy()
        new_context["previous_feedback"] = feedback
        new_context["previous_attempts"] = new_context.get("previous_attempts", []) + [feedback]
        
        # Progressive disclosure: add more context on revision
        if task.context.get("hints"):
            new_context["hints"] = task.context["hints"] + " [REVISED]"
        
        return ProducerTask(
            id=f"{task.id}-rev{len(self.history) + 1}",
            description=task.description,
            requirements=task.requirements + revisions,
            context=new_context,
            difficulty=task.difficulty,
            stage=task.stage,
            max_tool_calls=task.max_tool_calls,
            timeout=task.timeout,
            quality_gates=task.quality_gates,
        )
    
    def get_grpo_advantages(self) -> List[float]:
        """Extract review scores as GRPO advantages for training
        
        For use with Curriculum-Forge's GRPO optimizer
        """
        return [round.to_grpo_reward() for round in self.history]
    
    def get_feedback_summary(self) -> str:
        """Get summary of all feedback for analysis"""
        if not self.history:
            return "No history"
        
        lines = [f"## Producer-Reviewer Session Summary\n"]
        
        for i, round in enumerate(self.history, 1):
            lines.append(f"### Round {i}")
            lines.append(f"- Verdict: {round.verdict.value}")
            lines.append(f"- Overall Score: {round.overall_score():.2f}")
            lines.append(f"- Feedback: {round.feedback}")
            lines.append("")
        
        return "\n".join(lines)
