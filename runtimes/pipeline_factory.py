"""
Pipeline Factory

创建完整的 Pipeline 配置：
- PipelineConfig（providers 链）
- ServiceContainer（已初始化服务）
- CheckpointStore（持久化）

Usage:
    config, container, store = create_pipeline(
        profile_name="rl_controller",
        checkpoint_dir=None,
    )
    runtime = AdaptiveRuntime(config=config, service_container=container, checkpoint_store=store)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from providers.base import TaskProvider

# Import services for container initialization
from services.environment import EnvironmentService, EnvironmentServiceConfig
from services.learner import LearnerService, LearnerServiceConfig
from services.container import ServiceContainer, ServiceRegistry, ServiceProvider
from runtimes.adaptive_runtime import AdaptiveRuntime, PipelineConfig
from runtimes.checkpoint_store import CheckpointStore, CheckpointRecord
from runtimes.workspace import RunWorkspace, WORKSPACE_BASE

logger = logging.getLogger(__name__)


# ── Provider Registry ─────────────────────────────────────────────────────────

_PROVIDER_REGISTRY: List[TaskProvider] = []


def _build_provider_chain() -> List[TaskProvider]:
    """Build the default provider chain (curriculum → harness → memory → review)."""
    from providers.curriculum_provider import CurriculumProvider
    from providers.harness_provider import HarnessProvider
    from providers.memory_provider import MemoryProvider
    from providers.review_provider import ReviewProvider

    # Return cached if already built
    if _PROVIDER_REGISTRY:
        return _PROVIDER_REGISTRY

    providers = [
        CurriculumProvider(),
        HarnessProvider(),
        MemoryProvider(),
        ReviewProvider(),
    ]
    _PROVIDER_REGISTRY.extend(providers)
    return _PROVIDER_REGISTRY


# ── Service Container Builder ─────────────────────────────────────────────────

def _build_service_container(workspace_dir: str = ".") -> ServiceContainer:
    """Build and initialize a service container with core services."""
    container = ServiceContainer()

    # EnvironmentService (Agent A - Producer)
    env_config = EnvironmentServiceConfig(
        name="environment",
        workspace=workspace_dir,
        max_tasks_beginner=2,
        max_tasks_intermediate=3,
        max_tasks_advanced=5,
    )
    container.add(EnvironmentService, env_config)

    # LearnerService (Agent B - Executor)
    learner_config = LearnerServiceConfig(
        name="learner",
        workspace=workspace_dir,
        max_iterations=3,
        llm_backend="mock",  # Use mock backend for provider execution
        llm_model="mock",
    )
    container.add(LearnerService, learner_config)

    # Initialize and start (mimics ServiceProvider lifecycle)
    container.initialize_all()
    container.start_all()

    return container


# ── Profile Loading ──────────────────────────────────────────────────────────

def _load_profile(profile_name: str) -> Dict[str, Any]:
    """Load a profile JSON from profiles/ directory."""
    import json

    project_root = Path(__file__).resolve().parent.parent
    profile_path = project_root / "profiles" / f"{profile_name}.json"

    if not profile_path.exists():
        # Return minimal default profile
        logger.warning(f"Profile '{profile_name}' not found, using default")
        return {
            "topic": "general",
            "difficulty": "beginner",
            "max_iterations": 10,
        }

    with open(profile_path, encoding="utf-8") as f:
        return json.load(f)


# ── Main Factory ──────────────────────────────────────────────────────────────

def create_pipeline(
    profile_name: str = "rl_controller",
    checkpoint_dir: Optional[Path] = None,
    providers: Optional[List[TaskProvider]] = None,
    run_id: Optional[str] = None,
) -> Tuple[PipelineConfig, ServiceContainer, CheckpointStore, RunWorkspace]:
    """
    Create a fully-wired pipeline with per-run workspace isolation.

    Returns:
        (PipelineConfig, ServiceContainer, CheckpointStore, RunWorkspace)

    The returned AdaptiveRuntime can be used directly:
        runtime = AdaptiveRuntime(
            config=config,
            service_container=container,
            checkpoint_store=store,
            workspace=workspace,
        )
    """
    # Generate run_id if not provided
    if run_id is None:
        run_id = CheckpointStore.new_id()

    # Build components
    provider_chain = providers or _build_provider_chain()

    # Create per-run workspace
    workspace = RunWorkspace(run_id=run_id)

    # Build service container with workspace isolation
    container = _build_service_container(workspace_dir=workspace.workspace_path())

    store = CheckpointStore(base_dir=checkpoint_dir)

    # Load profile for config
    profile = _load_profile(profile_name)

    # Build PipelineConfig
    config = PipelineConfig(
        profile=profile_name,
        providers=provider_chain,
        checkpoint_dir=checkpoint_dir,
        auto_save=True,
        interactive=False,
    )

    # Inject services into container
    config._service_container = container
    config._profile = profile

    logger.info(f"Pipeline created: profile={profile_name}, run_id={run_id}, workspace={workspace.root}")

    return config, container, store, workspace


# ── Convenience: Run a single job end-to-end ──────────────────────────────────

async def run_job(
    profile_name: str = "rl_controller",
    checkpoint_dir: Optional[Path] = None,
    extra_config: Optional[Dict[str, Any]] = None,
) -> CheckpointRecord:
    """
    Convenience function: create pipeline and run end-to-end.

    Returns the final CheckpointRecord.
    """
    config, container, store, workspace = create_pipeline(profile_name, checkpoint_dir)

    runtime = AdaptiveRuntime(
        config=config,
        service_container=container,
        checkpoint_store=store,
        workspace=workspace,
    )

    run_config = {**(config._profile or {}), **(extra_config or {})}

    result = await runtime.run(run_config)
    return result


# ── CLI Integration ──────────────────────────────────────────────────────────

def create_runtime_from_profile(
    profile_name: str,
    checkpoint_store: Optional[CheckpointStore] = None,
    run_id: Optional[str] = None,
) -> AdaptiveRuntime:
    """
    Create an AdaptiveRuntime for a given profile.
    Used by Gateway's _run_job_background().
    """
    config, container, store, workspace = create_pipeline(
        profile_name,
        run_id=run_id,
    )

    return AdaptiveRuntime(
        config=config,
        service_container=container,
        checkpoint_store=checkpoint_store or store,
        workspace=workspace,
    )