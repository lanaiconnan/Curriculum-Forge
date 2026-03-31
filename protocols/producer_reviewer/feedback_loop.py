"""Feedback Loop - Tracks and analyzes review feedback history

Provides feedback pattern analysis to improve both Producer and Reviewer.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import defaultdict


@dataclass
class FeedbackEntry:
    """Single feedback entry"""
    timestamp: str
    task_id: str
    round: int
    verdict: str
    score: float
    feedback: str
    issues: List[str] = field(default_factory=list)
    revisions_applied: List[str] = field(default_factory=list)


@dataclass
class FeedbackPattern:
    """Identified feedback pattern"""
    pattern_type: str          # e.g., "format", "completeness", "accuracy"
    frequency: int             # How often this issue appears
    avg_score_drop: float      # Average score impact
    typical_resolution: str    # Common fix approach
    examples: List[str] = field(default_factory=list)


@dataclass
class FeedbackHistory:
    """Complete feedback history with pattern analysis"""
    entries: List[FeedbackEntry] = field(default_factory=list)
    patterns: List[FeedbackPattern] = field(default_factory=list)
    
    def add(
        self,
        task_id: str,
        round: int,
        verdict: str,
        score: float,
        feedback: str,
        issues: List[str] = None,
        revisions: List[str] = None,
    ):
        """Add a new feedback entry"""
        entry = FeedbackEntry(
            timestamp=datetime.now().isoformat(),
            task_id=task_id,
            round=round,
            verdict=verdict,
            score=score,
            feedback=feedback,
            issues=issues or [],
            revisions_applied=revisions or [],
        )
        self.entries.append(entry)
        self._recompute_patterns()
    
    def _recompute_patterns(self):
        """Analyze patterns in feedback history"""
        # Group issues by type
        issue_counts = defaultdict(list)
        
        for entry in self.entries:
            for issue in entry.issues:
                # Normalize issue type
                issue_type = self._normalize_issue_type(issue)
                issue_counts[issue_type].append(entry.score)
        
        # Build patterns
        self.patterns = []
        for issue_type, scores in issue_counts.items():
            if len(scores) >= 2:  # Need at least 2 occurrences
                avg_score = sum(scores) / len(scores)
                pattern = FeedbackPattern(
                    pattern_type=issue_type,
                    frequency=len(scores),
                    avg_score_drop=1.0 - avg_score,
                    typical_resolution=self._suggest_resolution(issue_type),
                    examples=self._get_examples(issue_type),
                )
                self.patterns.append(pattern)
        
        # Sort by frequency
        self.patterns.sort(key=lambda p: p.frequency, reverse=True)
    
    def _normalize_issue_type(self, issue: str) -> str:
        """Normalize issue description to type"""
        issue_lower = issue.lower()
        
        if any(w in issue_lower for w in ["format", "structure", "parse"]):
            return "format"
        elif any(w in issue_lower for w in ["missing", "incomplete", "lack"]):
            return "completeness"
        elif any(w in issue_lower for w in ["wrong", "incorrect", "error", "bug"]):
            return "accuracy"
        elif any(w in issue_lower for w in ["slow", "performance", "optimize"]):
            return "performance"
        elif any(w in issue_lower for w in ["style", "readable", "convention"]):
            return "style"
        else:
            return "other"
    
    def _suggest_resolution(self, issue_type: str) -> str:
        """Suggest resolution approach for issue type"""
        resolutions = {
            "format": "Review output format specification and use templating",
            "completeness": "Add checklist for required elements before submission",
            "accuracy": "Add validation step with test cases",
            "performance": "Add profiling and benchmark requirements",
            "style": "Apply linter/formatter before submission",
        }
        return resolutions.get(issue_type, "Review and revise based on feedback")
    
    def _get_examples(self, issue_type: str) -> List[str]:
        """Get example issues of this type"""
        examples = []
        for entry in self.entries:
            for issue in entry.issues:
                if self._normalize_issue_type(issue) == issue_type:
                    examples.append(issue)
                    if len(examples) >= 3:
                        return examples
        return examples
    
    def get_improvement_suggestions(self) -> List[str]:
        """Get actionable improvement suggestions based on patterns"""
        suggestions = []
        
        for pattern in self.patterns[:5]:  # Top 5 patterns
            if pattern.frequency >= 2:
                suggestions.append(
                    f"[{pattern.pattern_type.upper()}] {pattern.frequency}x issues: "
                    f"{pattern.typical_resolution}"
                )
        
        return suggestions
    
    def get_rejection_rate(self) -> float:
        """Calculate overall rejection rate"""
        if not self.entries:
            return 0.0
        
        rejected = sum(1 for e in self.entries if e.verdict == "reject")
        return rejected / len(self.entries)
    
    def get_average_score_by_round(self) -> Dict[int, float]:
        """Get average score by round number"""
        round_scores = defaultdict(list)
        
        for entry in self.entries:
            round_scores[entry.round].append(entry.score)
        
        return {
            round_num: sum(scores) / len(scores)
            for round_num, scores in round_scores.items()
        }


class FeedbackLoop:
    """
    Feedback Loop Manager
    
    Manages the feedback cycle between Producer-Reviewer rounds
    and provides analytics for continuous improvement.
    """
    
    def __init__(self):
        self.history = FeedbackHistory()
        self.current_session: List[FeedbackEntry] = []
    
    def start_session(self):
        """Start a new feedback session"""
        self.current_session.clear()
    
    def record_feedback(
        self,
        task_id: str,
        round: int,
        verdict: str,
        score: float,
        feedback: str,
        issues: List[str] = None,
        revisions: List[str] = None,
    ):
        """Record feedback from a round"""
        entry = FeedbackEntry(
            timestamp=datetime.now().isoformat(),
            task_id=task_id,
            round=round,
            verdict=verdict,
            score=score,
            feedback=feedback,
            issues=issues or [],
            revisions_applied=revisions or [],
        )
        
        self.current_session.append(entry)
        self.history.add(
            task_id=task_id,
            round=round,
            verdict=verdict,
            score=score,
            feedback=feedback,
            issues=issues,
            revisions=revisions,
        )
    
    def end_session(self) -> Dict[str, Any]:
        """End session and return summary"""
        if not self.current_session:
            return {"message": "No feedback in session"}
        
        # Session statistics
        total_rounds = len(self.current_session)
        accepted = sum(1 for e in self.current_session if e.verdict == "accept")
        rejected = sum(1 for e in self.current_session if e.verdict == "reject")
        revised = sum(1 for e in self.current_session if e.verdict == "revise")
        
        avg_score = sum(e.score for e in self.current_session) / total_rounds
        final_score = self.current_session[-1].score
        
        return {
            "session_rounds": total_rounds,
            "accepted": accepted,
            "rejected": rejected,
            "revised": revised,
            "acceptance_rate": accepted / total_rounds,
            "average_score": avg_score,
            "final_score": final_score,
            "improvement_suggestions": self.history.get_improvement_suggestions(),
            "patterns": [
                {"type": p.pattern_type, "freq": p.frequency, "resolution": p.typical_resolution}
                for p in self.history.patterns[:3]
            ],
        }
    
    def should_escalate(self) -> bool:
        """Determine if session should escalate (e.g., to human review)"""
        if len(self.current_session) >= 3:
            # Check if scores are declining
            scores = [e.score for e in self.current_session]
            if scores[-1] < scores[0] - 0.2:
                return True
        
        # Check for repeated same issue
        if len(self.current_session) >= 2:
            last_issues = set(self.current_session[-1].issues)
            prev_issues = set(self.current_session[-2].issues)
            if last_issues == prev_issues and last_issues:
                return True
        
        return False
    
    def get_grpo_training_data(self) -> List[Dict[str, Any]]:
        """Extract training data for GRPO from feedback history
        
        Formats feedback scores for use in Curriculum-Forge's GRPO optimizer.
        """
        training_data = []
        
        for entry in self.history.entries:
            training_data.append({
                "task_id": entry.task_id,
                "round": entry.round,
                "reward": entry.score,
                "verdict": entry.verdict,
                "feedback": entry.feedback,
            })
        
        return training_data
    
    def export_for_analysis(self) -> Dict[str, Any]:
        """Export full feedback data for external analysis"""
        return {
            "total_entries": len(self.history.entries),
            "rejection_rate": self.history.get_rejection_rate(),
            "patterns": [
                {
                    "type": p.pattern_type,
                    "frequency": p.frequency,
                    "avg_score_drop": p.avg_score_drop,
                    "resolution": p.typical_resolution,
                }
                for p in self.history.patterns
            ],
            "score_by_round": self.history.get_average_score_by_round(),
        }
