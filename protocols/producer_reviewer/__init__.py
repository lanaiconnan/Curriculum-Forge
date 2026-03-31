"""Producer-Reviewer Protocol for Curriculum-Forge

Implements a structured collaboration loop between Agent A (Producer) and Agent B (Learner),
inspired by Harness's Producer-Reviewer architecture pattern.

The protocol adds:
- Review-driven feedback loop (Agent A reviews Agent B's output before accepting)
- Iterative refinement with configurable max rounds
- Quality gates between production and acceptance
- Structured review scores that feed into GRPO advantage estimation
- Progressive context disclosure based on review performance
"""

from .protocol import (
    ProducerReviewerProtocol,
    ReviewRound,
    ReviewVerdict,
    ProducerTask,
    QualityGate,
)
from .reviewer import ReviewerAgent, ReviewCriteria, ReviewScore
from .producer import ProducerAgent, ProductionPlan
from .feedback_loop import FeedbackLoop, FeedbackHistory

__all__ = [
    "ProducerReviewerProtocol",
    "ReviewRound",
    "ReviewVerdict",
    "ProducerTask",
    "QualityGate",
    "ReviewerAgent",
    "ReviewCriteria",
    "ReviewScore",
    "ProducerAgent",
    "ProductionPlan",
    "FeedbackLoop",
    "FeedbackHistory",
]
