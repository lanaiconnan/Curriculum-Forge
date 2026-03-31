"""Progressive Disclosure Protocol for Curriculum-Forge

Fine-grained difficulty control that goes beyond the coarse 3-stage system.
Dynamically adjusts task difficulty, context richness, and tool constraints
based on real-time learner performance signals.

Core ideas from Harness Progressive Disclosure:
- Start minimal: fewest hints, hardest constraints
- Reveal gradually: performance drives context release
- Continuous difficulty: float 0.0-1.0, not 3 fixed levels
- Per-dimension control: separate knobs for complexity, hints, tools, time

Architecture:
    Performance Signals (score, keep_rate, time_used, error_count)
         |
    DifficultyController.adjust()
         |
    TaskConfig (difficulty, hints, tools, time, examples, scaffold)
         |
    Expert/Producer generates environment from TaskConfig
"""

from .controller import (
    DifficultyController,
    DifficultyConfig,
    DifficultyDimensions,
    PerformanceSignal,
    DifficultyAdjustment,
)
from .disclosure import (
    ContextDiscloser,
    ContextLayer,
    DisclosurePolicy,
)
from .task_config import (
    TaskConfig,
    TaskConfigBuilder,
)
from .integration import (
    ProgressiveDisclosureIntegration,
    DisclosureSession,
)

__all__ = [
    "DifficultyController",
    "DifficultyConfig",
    "DifficultyDimensions",
    "PerformanceSignal",
    "DifficultyAdjustment",
    "ContextDiscloser",
    "ContextLayer",
    "DisclosurePolicy",
    "TaskConfig",
    "TaskConfigBuilder",
    "ProgressiveDisclosureIntegration",
    "DisclosureSession",
]
