"""Expert Pool Protocol for Curriculum-Forge

Implements the Expert Pool architecture pattern (from Harness):
A registry of specialized training experts, dynamically selected based on
the learner's weak areas, performance history, and learning stage.

Instead of generating generic environments per stage, Agent A selects
the most relevant Expert to create targeted training scenarios.

Flow:
  Learner State (weak_areas + performance) 
    → ExpertSelector.score(experts) 
    → Best Expert 
    → Specialized TrainingEnvironment
"""

from .pool import ExpertPool, Expert, ExpertRegistry
from .selector import ExpertSelector, SelectionStrategy, SelectionResult
from .experts import (
    ToolMasteryExpert,
    ErrorRecoveryExpert,
    OptimizationExpert,
    MultiToolExpert,
    EdgeCaseExpert,
    CodeReviewExpert,
)
from .integration import ExpertPoolIntegration

__all__ = [
    "ExpertPool",
    "Expert",
    "ExpertRegistry",
    "ExpertSelector",
    "SelectionStrategy",
    "SelectionResult",
    "ToolMasteryExpert",
    "ErrorRecoveryExpert",
    "OptimizationExpert",
    "MultiToolExpert",
    "EdgeCaseExpert",
    "CodeReviewExpert",
    "ExpertPoolIntegration",
]
