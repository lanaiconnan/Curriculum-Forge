"""Reviewer Agent - Quality evaluation for Producer-Reviewer loop

Integrates with Agent A (Analyst) to provide structured quality assessment.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime


class ReviewCriteria(Enum):
    """Quality assessment dimensions"""
    FORMAT = "format"
    COMPLETENESS = "completeness"
    ACCURACY = "accuracy"
    PERFORMANCE = "performance"
    STYLE = "style"


@dataclass
class ReviewScore:
    """Individual score for one criteria"""
    criteria: str
    score: float              # 0-1
    max_score: float = 1.0
    justification: str = ""
    issues: List[str] = field(default_factory=list)
    
    def percentage(self) -> float:
        return (self.score / self.max_score) * 100


@dataclass
class ReviewOutput:
    """Structured review output from Agent A"""
    scores: List[ReviewScore]
    verdict: str              # accept/revise/reject
    feedback: str             # Human-readable summary
    detailed_analysis: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    revisions_needed: List[str] = field(default_factory=list)


class ReviewerAgent:
    """
    Reviewer Agent - Quality gate evaluator
    
    Integrates with Agent A's Analyst capabilities to provide
    structured quality assessment of Agent B's outputs.
    
    Can operate in:
    - LLM mode: Uses LLM to generate nuanced reviews
    - Heuristic mode: Rule-based automatic scoring
    - Hybrid mode: LLM with heuristic validation
    """
    
    def __init__(
        self,
        use_llm: bool = True,
        llm_model: str = "claude-3-5-sonnet-20241022",
        strict_mode: bool = False,
    ):
        self.use_llm = use_llm
        self.llm_model = llm_model
        self.strict_mode = strict_mode
        self.review_history: List[ReviewOutput] = []
        
        # Thresholds
        self.accept_threshold = 0.7
        self.revise_threshold = 0.5
    
    def review(
        self,
        task_description: str,
        learner_output: Any,
        criteria: List[ReviewCriteria] = None,
        context: Dict[str, Any] = None,
    ) -> ReviewOutput:
        """
        Perform comprehensive review of Agent B's output
        
        Args:
            task_description: Original task from Producer
            learner_output: Agent B's output to review
            criteria: Which criteria to evaluate
            context: Additional context (previous attempts, etc.)
        
        Returns:
            ReviewOutput with scores and verdict
        """
        criteria = criteria or [
            ReviewCriteria.FORMAT,
            ReviewCriteria.COMPLETENESS,
            ReviewCriteria.ACCURACY,
            ReviewCriteria.PERFORMANCE,
            ReviewCriteria.STYLE,
        ]
        
        if self.use_llm:
            return self._llm_review(task_description, learner_output, criteria, context)
        else:
            return self._heuristic_review(task_description, learner_output, criteria)
    
    def _llm_review(
        self,
        task_description: str,
        learner_output: Any,
        criteria: List[ReviewCriteria],
        context: Dict[str, Any],
    ) -> ReviewOutput:
        """LLM-powered review with structured prompting"""
        # Build review prompt
        prompt = self._build_review_prompt(task_description, learner_output, criteria, context)
        
        # Call LLM (placeholder - integrate with your LLM client)
        # In production, this would call Claude, GPT, etc.
        llm_response = self._call_llm(prompt)
        
        # Parse response into structured scores
        return self._parse_llm_response(llm_response, criteria)
    
    def _build_review_prompt(
        self,
        task_description: str,
        learner_output: Any,
        criteria: List[ReviewCriteria],
        context: Dict[str, Any],
    ) -> str:
        """Build prompt for LLM reviewer"""
        criteria_str = "\n".join(f"- {c.value}: {self._criteria_description(c)}" for c in criteria)
        
        context_str = ""
        if context:
            if context.get("previous_attempts"):
                context_str += f"\nPrevious failed attempts: {len(context['previous_attempts'])}"
            if context.get("hints"):
                context_str += f"\nHints provided: {context['hints']}"
        
        return f"""
## Review Task

You are a quality reviewer evaluating Agent B's output for the following task:

### Task
{task_description}

### Context
{context_str}

### Evaluation Criteria
{criteria_str}

### Agent B's Output
```
{learner_output}
```

### Output Format
Provide your review in JSON format:
{{
  "scores": [
    {{"criteria": "format", "score": 0.0-1.0, "justification": "...", "issues": [...]}},
    ...
  ],
  "verdict": "accept|revise|reject",
  "feedback": "Human-readable summary",
  "revisions_needed": ["issue 1", "issue 2", ...]
}}

Be strict but fair. A score of 1.0 means perfect, 0.0 means completely failed.
"""
    
    def _criteria_description(self, criteria: ReviewCriteria) -> str:
        """Get description for each criteria"""
        descriptions = {
            ReviewCriteria.FORMAT: "Output follows required format and structure",
            ReviewCriteria.COMPLETENESS: "All required elements and requirements are present",
            ReviewCriteria.ACCURACY: "Technical correctness and accuracy of solution",
            ReviewCriteria.PERFORMANCE: "Performance meets benchmarks and efficiency goals",
            ReviewCriteria.STYLE: "Code style, readability, and best practices followed",
        }
        return descriptions.get(criteria, "")
    
    def _call_llm(self, prompt: str) -> str:
        """Call LLM - placeholder for actual integration"""
        # In production, integrate with your LLM client
        # This is where you'd call Claude, GPT, etc.
        raise NotImplementedError("LLM integration not configured")
    
    def _parse_llm_response(self, response: str, criteria: List[ReviewCriteria]) -> ReviewOutput:
        """Parse LLM response into structured ReviewOutput"""
        import json
        
        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            # Fallback to heuristic if parsing fails
            return self._heuristic_review_simple()
        
        scores = [
            ReviewScore(
                criteria=s["criteria"],
                score=s.get("score", 0.5),
                justification=s.get("justification", ""),
                issues=s.get("issues", []),
            )
            for s in data.get("scores", [])
        ]
        
        return ReviewOutput(
            scores=scores,
            verdict=data.get("verdict", "revise"),
            feedback=data.get("feedback", ""),
            recommendations=data.get("recommendations", []),
            revisions_needed=data.get("revisions_needed", []),
        )
    
    def _heuristic_review(
        self,
        task_description: str,
        learner_output: Any,
        criteria: List[ReviewCriteria],
    ) -> ReviewOutput:
        """Rule-based automatic review"""
        scores = []
        
        for crit in criteria:
            score = self._heuristic_score(crit, task_description, learner_output)
            scores.append(score)
        
        # Determine verdict
        avg_score = sum(s.score for s in scores) / len(scores)
        
        if avg_score >= self.accept_threshold:
            verdict = "accept"
        elif avg_score >= self.revise_threshold:
            verdict = "revise"
        else:
            verdict = "reject"
        
        return ReviewOutput(
            scores=scores,
            verdict=verdict,
            feedback=f"Auto-reviewed: average score {avg_score:.2f}",
            revisions_needed=[s.issues[0] for s in scores if s.score < self.accept_threshold],
        )
    
    def _heuristic_score(
        self,
        criteria: ReviewCriteria,
        task_description: str,
        output: Any,
    ) -> ReviewScore:
        """Calculate heuristic score for a criteria"""
        # Simple heuristics - expand as needed
        issues = []
        
        if criteria == ReviewCriteria.FORMAT:
            # Check for basic structure
            if output is None or output == "":
                score = 0.0
                issues.append("Empty output")
            elif isinstance(output, dict):
                score = 0.8
            elif isinstance(output, str):
                score = 0.7
            else:
                score = 0.6
                
        elif criteria == ReviewCriteria.COMPLETENESS:
            # Check if output seems complete
            output_str = str(output)
            if len(output_str) > 100:
                score = 0.8
            elif len(output_str) > 50:
                score = 0.6
            else:
                score = 0.4
                issues.append("Output too short")
                
        else:
            # Default for other criteria
            score = 0.6
            issues.append("Automatic review - limited analysis")
        
        return ReviewScore(
            criteria=criteria.value,
            score=score,
            justification=f"Heuristic score: {score:.2f}",
            issues=issues,
        )
    
    def _heuristic_review_simple(self) -> ReviewOutput:
        """Fallback simple review"""
        return ReviewOutput(
            scores=[
                ReviewScore("format", 0.7),
                ReviewScore("completeness", 0.7),
                ReviewScore("accuracy", 0.7),
                ReviewScore("performance", 0.7),
                ReviewScore("style", 0.7),
            ],
            verdict="revise",
            feedback="Review parsing failed, using default",
        )
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get review statistics"""
        if not self.review_history:
            return {"total_reviews": 0}
        
        verdicts = {}
        avg_scores = []
        
        for review in self.review_history:
            verdicts[review.verdict] = verdicts.get(review.verdict, 0) + 1
            avg_scores.append(sum(s.score for s in review.scores) / len(review.scores))
        
        return {
            "total_reviews": len(self.review_history),
            "verdict_distribution": verdicts,
            "average_score": sum(avg_scores) / len(avg_scores),
        }
