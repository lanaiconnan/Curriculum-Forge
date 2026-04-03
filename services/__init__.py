"""Curriculum-Forge Service Layer

This module provides a service-oriented architecture for Curriculum-Forge,
enabling:
- Dependency injection
- Lifecycle management (init/start/stop)
- Service discovery and registration
- Clean separation of concerns

Architecture:
    ServiceProvider (Container)
         |
    ├─ EnvironmentService (Agent A)
    ├─ LearnerService (Agent B)
    ├─ RLTrainerService (RL Trainer)
    └─ PluginService (Plugin Manager)

Usage:
    from services import ServiceProvider, EnvironmentService, LearnerService

    # Initialize service container
    provider = ServiceProvider()
    provider.configure(EnvironmentService, env_config)
    provider.configure(LearnerService, learner_config)
    provider.configure(RLTrainerService, rl_config)
    
    # Start all services
    provider.start()

    # Get services
    env_service = provider.get(EnvironmentService)
    learner_service = provider.get(LearnerService)

    # Use services
    env = env_service.generate_environment(progress)
    results = learner_service.run_experiments(env)
    
    # Stop all services
    provider.stop()
"""

from .base import (
    ServiceBase,
    ServiceConfig,
    ServiceState,
    ServiceMetrics,
    ServiceError,
)
from .container import (
    ServiceRegistry,
    ServiceContainer,
    ServiceProvider,
)
from .models import (
    TrainingEnvironment,
    TaskConfig,
    ExperimentRecord,
    ExperimentStatus,
    LearningStage,
    ProgressMetrics,
    RewardBreakdown,
    ServiceHealth,
)
from .environment import (
    EnvironmentService,
    EnvironmentServiceConfig,
)
from .learner import (
    LearnerService,
    LearnerServiceConfig,
    ExperimentResult,
)
from .trainer import (
    RLTrainerService,
    RLConfig,
    Experience,
    TrainingStats,
)
from .coordinator import (
    Coordinator,
    Task,
    TaskStatus,
    AgentRole,
    AgentInfo,
    Message,
    Workflow,
    MessageQueue,
    AgentRegistry,
)
from .dual_agent import (
    DualAgentCoordinator,
    DualAgentConfig,
    EpisodeResult,
)
from .tools import (
    ManagedToolRegistry,
    ToolPermission,
    PermissionResult,
    PermissionBehavior,
    RateLimit,
    ToolResultFormatter,
    ToolStats,
    StatsTracker,
    ToolCallRecord,
)
from .harness import (
    HarnessCase,
    CaseResult,
    HarnessReport,
    HarnessRunner,
    HarnessSuite,
    HarnessScorer,
    Verdict,
    build_tool_basics_suite,
    build_curriculum_suite,
)
from .compact import (
    CompactEngine,
    ImportanceScorer,
    ImportanceScore,
    MicroCompactor,
    CompactArchive,
    ArchivedCompact,
)

__all__ = [
    # Base
    "ServiceBase",
    "ServiceConfig",
    "ServiceState",
    "ServiceMetrics",
    "ServiceError",
    # Container
    "ServiceRegistry",
    "ServiceContainer",
    "ServiceProvider",
    # Models
    "TrainingEnvironment",
    "TaskConfig",
    "ExperimentRecord",
    "ExperimentStatus",
    "LearningStage",
    "ProgressMetrics",
    "RewardBreakdown",
    "ServiceHealth",
    # Services
    "EnvironmentService",
    "EnvironmentServiceConfig",
    "LearnerService",
    "LearnerServiceConfig",
    "ExperimentResult",
    "RLTrainerService",
    "RLConfig",
    "Experience",
    "TrainingStats",
    # Coordinator
    "Coordinator",
    "Task",
    "TaskStatus",
    "AgentRole",
    "AgentInfo",
    "Message",
    "Workflow",
    "MessageQueue",
    "AgentRegistry",
    # Dual Agent
    "DualAgentCoordinator",
    "DualAgentConfig",
    "EpisodeResult",
    # Query Engine
    "QueryEngine",
    "QueryConfig",
    "QueryResult",
    "ToolRegistry",
    "ToolDefinition",
    "LLMBackend",
    "MockBackend",
    "AnthropicBackend",
    "TokenUsage",
    "create_backend",
    # Tools (permission + formatting + stats)
    "ManagedToolRegistry",
    "ToolPermission",
    "PermissionResult",
    "PermissionBehavior",
    "RateLimit",
    "ToolResultFormatter",
    "ToolStats",
    "StatsTracker",
    "ToolCallRecord",
    # Harness
    "HarnessCase",
    "CaseResult",
    "HarnessReport",
    "HarnessRunner",
    "HarnessSuite",
    "HarnessScorer",
    "Verdict",
    "build_tool_basics_suite",
    "build_curriculum_suite",
    # Compact
    "CompactEngine",
    "ImportanceScorer",
    "ImportanceScore",
    "MicroCompactor",
    "CompactArchive",
    "ArchivedCompact",
]