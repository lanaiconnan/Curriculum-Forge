"""Tests for Runtime ↔ Coordinator bridge integration."""

import asyncio
import pytest
import sys
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from providers.base import RunState, TaskPhase, TaskProvider, TaskOutput
from runtimes.adaptive_runtime import AdaptiveRuntime, PipelineConfig
from runtimes.checkpoint_store import CheckpointStore
from services.coordinator import (
    Coordinator,
    AgentInfo,
    AgentRole,
    Message,
    MessageQueue,
    Workflow,
    Task,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

class DummyProvider(TaskProvider):
    """Simple provider for testing."""
    def __init__(self, phase=TaskPhase.CURRICULUM, output_ok=True):
        self._phase = phase
        self._output_ok = output_ok
        self.executed = False

    @property
    def phase(self):
        return self._phase

    async def execute(self, config, runtime):
        self.executed = True
        return TaskOutput(
            phase=self._phase,
            data={"dummy": True, "status": "ok" if self._output_ok else "error"},
        )


def _make_runtime(coordinator=None, providers=None):
    """Create a minimal AdaptiveRuntime for testing."""
    if providers is None:
        providers = [DummyProvider(TaskPhase.CURRICULUM)]
    config = PipelineConfig(
        profile="test",
        providers=providers,
        auto_save=False,
    )
    store = CheckpointStore()
    return AdaptiveRuntime(
        config=config,
        checkpoint_store=store,
        coordinator=coordinator,
    )


# ── Tests: Coordinator notification ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_runtime_notifies_coordinator_on_provider_done():
    """When coordinator is attached, provider_done messages are broadcast."""
    coordinator = Coordinator()
    runtime = _make_runtime(coordinator=coordinator)

    await runtime.run({})

    # Broadcast messages are stored under "*" recipient
    messages = coordinator.message_queue.receive("*")
    # At least one provider_done message should be sent
    provider_done = [m for m in messages if m.type == "provider_done"]
    assert len(provider_done) >= 1
    assert provider_done[0].payload["phase"] == "curriculum"
    assert provider_done[0].payload["ok"] is True


@pytest.mark.asyncio
async def test_runtime_no_notification_without_coordinator():
    """Without coordinator, runtime still works fine (no crash)."""
    runtime = _make_runtime(coordinator=None)
    record = await runtime.run({})
    assert record.state == RunState.COMPLETED


@pytest.mark.asyncio
async def test_runtime_notifies_for_each_provider():
    """Each provider execution triggers a notification."""
    coordinator = Coordinator()
    providers = [
        DummyProvider(TaskPhase.CURRICULUM),
        DummyProvider(TaskPhase.HARNESS),
        DummyProvider(TaskPhase.MEMORY),
        DummyProvider(TaskPhase.REVIEW),
    ]
    runtime = _make_runtime(coordinator=coordinator, providers=providers)

    await runtime.run({})

    messages = coordinator.message_queue.receive("*")
    provider_done = [m for m in messages if m.type == "provider_done"]
    assert len(provider_done) == 4
    phases = [m.payload["phase"] for m in provider_done]
    assert "curriculum" in phases
    assert "harness" in phases
    assert "memory" in phases
    assert "review" in phases


@pytest.mark.asyncio
async def test_notification_contains_run_id():
    """Provider done notification includes the run_id."""
    coordinator = Coordinator()
    runtime = _make_runtime(coordinator=coordinator)
    record = await runtime.run({})

    messages = coordinator.message_queue.receive("*")
    provider_done = [m for m in messages if m.type == "provider_done"]
    assert provider_done[0].payload["run_id"] == record.id


@pytest.mark.asyncio
async def test_notification_includes_data_keys():
    """Provider done notification includes data keys from output."""
    coordinator = Coordinator()
    runtime = _make_runtime(coordinator=coordinator)
    await runtime.run({})

    messages = coordinator.message_queue.receive("*")
    provider_done = [m for m in messages if m.type == "provider_done"]
    assert "dummy" in provider_done[0].payload["data_keys"]


# ── Tests: Coordinator with handlers ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_coordinator_handler_execution():
    """Coordinator can execute tasks via registered handlers."""
    coordinator = Coordinator()

    # Register an agent so tasks can be assigned
    coordinator.register_agent(AgentInfo(
        id="test_executor",
        name="Test Executor",
        role=AgentRole.EXECUTOR,
        capabilities=["test"],
    ))

    results = []

    async def handler(task):
        results.append(task.id)
        return {"status": "ok", "task_id": task.id}

    coordinator.register_handler("test_type", handler)

    workflow = coordinator.create_workflow("test", "test workflow")
    task = Task(id="t1", type="test_type", payload={})
    coordinator.add_task(workflow, task, "default")

    result = await coordinator.run_workflow_async(workflow, timeout=10)
    assert result["statistics"]["completed"] == 1
    assert "t1" in results


# ── Tests: Pipeline factory coordinator ───────────────────────────────────────

def test_create_coordinator():
    """create_coordinator() returns a coordinator with 3 agents."""
    from runtimes.pipeline_factory import create_coordinator

    coordinator = create_coordinator()
    agents = coordinator.agents.list_all()
    assert len(agents) == 3

    roles = {a.role.value for a in agents}
    assert "producer" in roles
    assert "executor" in roles
    assert "reviewer" in roles


def test_create_coordinator_has_handlers():
    """create_coordinator() registers handlers for 4 task types."""
    from runtimes.pipeline_factory import create_coordinator

    coordinator = create_coordinator()
    # Handlers are stored internally
    assert "environment" in coordinator._handlers
    assert "experiment" in coordinator._handlers
    assert "review" in coordinator._handlers
    assert "training" in coordinator._handlers


def test_create_runtime_from_profile_with_coordinator():
    """create_runtime_from_profile() attaches coordinator by default."""
    from runtimes.pipeline_factory import create_runtime_from_profile

    runtime = create_runtime_from_profile("rl_controller", with_coordinator=True)
    assert runtime.coordinator is not None
    assert len(runtime.coordinator.agents.list_all()) == 3


def test_create_runtime_from_profile_without_coordinator():
    """create_runtime_from_profile() can skip coordinator."""
    from runtimes.pipeline_factory import create_runtime_from_profile

    runtime = create_runtime_from_profile("rl_controller", with_coordinator=False)
    assert runtime.coordinator is None
