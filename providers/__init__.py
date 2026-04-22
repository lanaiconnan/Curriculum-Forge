"""
Curriculum-Forge Provider Layer

MoonClaw 风格的任务执行抽象层。
将 RL 训练 Pipeline 分为 4 个 Provider 阶段。

Usage:
    from providers import (
        TaskPhase, TaskProvider, ProviderRegistry,
        CurriculumProvider, HarnessProvider,
        MemoryProvider, ReviewProvider,
    )
    
    registry = ProviderRegistry()
    registry.register(CurriculumProvider())
    registry.register(HarnessProvider())
    registry.register(MemoryProvider())
    registry.register(ReviewProvider())
"""

from providers.base import (
    TaskPhase,        # Pipeline 阶段枚举
    RunState,         # 运行状态枚举
    TaskOutput,       # Provider 输出结构
    ProviderConfig,   # Provider 配置
    TaskProvider,     # Provider 基类（ABC）
    ProviderError,    # 执行错误
    ProviderRegistry, # Provider 注册中心
)

from providers.curriculum_provider import CurriculumProvider
from providers.harness_provider   import HarnessProvider
from providers.memory_provider    import MemoryProvider
from providers.review_provider    import ReviewProvider

__all__ = [
    # Base
    "TaskPhase",
    "RunState", 
    "TaskOutput",
    "ProviderConfig",
    "TaskProvider",
    "ProviderError",
    "ProviderRegistry",
    # Implementations
    "CurriculumProvider",
    "HarnessProvider",
    "MemoryProvider",
    "ReviewProvider",
]
