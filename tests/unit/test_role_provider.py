"""Tests for RoleRuntime Provider integration (Phase 2 Item 2)."""

import asyncio
import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from providers.base import RunState, TaskPhase, TaskProvider, TaskOutput
from roles.role_runtime import (
    RolePhase,
    RoleTask,
    RoleReport,
    TeacherRole,
    LearnerRole,
    ReviewerRole,
)
from services.coordinator import Coordinator, AgentRole


# ── Dummy Provider ────────────────────────────────────────────────────────────

class DummyProvider(TaskProvider):
    def __init__(self, phase=TaskPhase.CURRICULUM):
        self._phase = phase
        self.called = False

    @property
    def phase(self):
        return self._phase

    async def execute(self, config, runtime):
        self.called = True
        return TaskOutput(
            phase=self._phase,
            data={"status": "ok", "task": "dummy"},
        )


# ── Tests: TeacherRole with Provider ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_teacher_work_with_provider():
    """TeacherRole calls CurriculumProvider when bound."""
    provider = DummyProvider(TaskPhase.CURRICULUM)
    teacher = TeacherRole(provider=provider)

    task = RoleTask(id="t1", description="test topic", phase_hint=TaskPhase.CURRICULUM)
    await teacher.assign(task)
    report = await teacher.work(task)

    assert provider.called is True
    assert report.role == "Teacher"
    assert report.phase == RolePhase.REPORTING
    assert report.output["phase"] == "curriculum"


@pytest.mark.asyncio
async def test_teacher_work_without_provider():
    """TeacherRole works in degraded mode without provider."""
    teacher = TeacherRole()
    task = RoleTask(id="t1", description="test", phase_hint=TaskPhase.CURRICULUM)
    await teacher.assign(task)
    report = await teacher.work(task)

    assert report.metrics.get("degraded") is True


# ── Tests: LearnerRole with Provider ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_learner_work_with_providers():
    """LearnerRole calls Harness + Memory providers when bound."""
    harness = DummyProvider(TaskPhase.HARNESS)
    memory = DummyProvider(TaskPhase.MEMORY)
    learner = LearnerRole(
        harness_provider=harness,
        memory_provider=memory,
    )

    task = RoleTask(id="t1", description="test", phase_hint=TaskPhase.HARNESS)
    await learner.assign(task)
    report = await learner.work(task)

    assert harness.called is True
    assert memory.called is True
    assert "harness" in report.output
    assert "memory" in report.output


@pytest.mark.asyncio
async def test_learner_work_with_harness_only():
    """LearnerRole works with only harness provider."""
    harness = DummyProvider(TaskPhase.HARNESS)
    learner = LearnerRole(harness_provider=harness)

    task = RoleTask(id="t1", description="test", phase_hint=TaskPhase.HARNESS)
    await learner.assign(task)
    report = await learner.work(task)

    assert harness.called is True
    assert "harness" in report.output


# ── Tests: ReviewerRole with Provider ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_reviewer_work_with_provider():
    """ReviewerRole calls ReviewProvider when bound."""
    provider = DummyProvider(TaskPhase.REVIEW)
    reviewer = ReviewerRole(provider=provider)

    task = RoleTask(id="t1", description="review", phase_hint=TaskPhase.REVIEW)
    await reviewer.assign(task)
    report = await reviewer.work(task)

    assert provider.called is True
    assert report.output["phase"] == "review"


# ── Tests: to_agent_info ─────────────────────────────────────────────────────

def test_teacher_to_agent_info():
    teacher = TeacherRole()
    info = teacher.to_agent_info()
    assert info.id == "teacher"
    assert info.role == AgentRole.PRODUCER


def test_learner_to_agent_info():
    learner = LearnerRole()
    info = learner.to_agent_info()
    assert info.id == "learner"
    assert info.role == AgentRole.EXECUTOR


def test_reviewer_to_agent_info():
    reviewer = ReviewerRole()
    info = reviewer.to_agent_info()
    assert info.id == "reviewer"
    assert info.role == AgentRole.REVIEWER


# ── Tests: Coordinator role routing ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_coordinator_role_routing():
    """Coordinator routes tasks to RoleRuntime when registered."""
    coordinator = Coordinator()
    provider = DummyProvider(TaskPhase.CURRICULUM)
    teacher = TeacherRole(provider=provider)
    coordinator.register_role(teacher)

    # Teacher should be in the registry
    agents = coordinator.agents.list_all()
    assert len(agents) == 1
    assert agents[0].id == "teacher"

    # Role should be stored
    assert "teacher" in coordinator._roles


@pytest.mark.asyncio
async def test_coordinator_executes_via_role():
    """When a role is registered, task execution uses role.work()."""
    coordinator = Coordinator()
    provider = DummyProvider(TaskPhase.CURRICULUM)
    teacher = TeacherRole(provider=provider)
    coordinator.register_role(teacher)

    from services.coordinator import Task
    workflow = coordinator.create_workflow("test", "role test")

    # environment type maps to PRODUCER role → teacher
    task = Task(id="t1", type="environment", payload={"description": "test"})
    coordinator.add_task(workflow, task, "produce")

    result = await coordinator.run_workflow_async(workflow, timeout=10)
    assert result["statistics"]["completed"] == 1
    # The result should come from role execution
    task_result = result["tasks"]["t1"]
    assert task_result["result"]["role"] == "Teacher"
    assert provider.called is True


# ── Tests: Role status ───────────────────────────────────────────────────────

def test_role_status_with_provider():
    provider = DummyProvider(TaskPhase.CURRICULUM)
    teacher = TeacherRole(provider=provider)
    status = teacher.status
    assert status["has_provider"] is True
    assert status["role"] == "Teacher"


def test_role_status_without_provider():
    teacher = TeacherRole()
    status = teacher.status
    assert status["has_provider"] is False
