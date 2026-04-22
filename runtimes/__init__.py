"""
Curriculum-Forge Runtime Layer

MoonClaw 风格的任务执行引擎：
- CheckpointStore: 持久化运行状态
- AdaptiveRuntime: Pipeline 执行引擎
"""

# NOTE: CheckpointStore is NOT exported from __init__.py here to avoid
# circular import: adaptive_runtime.py needs CheckpointStore, but it lives in
# the same package whose __init__ imports adaptive_runtime.
#
# Tests must use one of:
#   from runtimes import CheckpointStore          # ❌ circular
#   from runtimes.checkpoint_store import ...     # ✅ direct
#   from runtimes import CheckpointRecord         # ✅ only CheckpointRecord is safe
#
# The fix: only import CheckpointRecord (no dep) in __init__.py,
# and let tests import CheckpointStore from the submodule.

from runtimes.checkpoint_store import CheckpointRecord  # safe — no circular dep
from runtimes.adaptive_runtime import AdaptiveRuntime, PipelineConfig

__all__ = [
    "CheckpointRecord",
    "AdaptiveRuntime",
    "PipelineConfig",
]
