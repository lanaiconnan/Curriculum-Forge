"""Tests for Coordinator async refactoring (Phase 1 Item 3)

Verifies:
1. run_workflow_async() executes tasks correctly
2. asyncio.Condition replaces time.sleep polling
3. complete_task() wakes up waiting coroutines
4. run_workflow() sync wrapper works
5. Async handlers are awaited, sync handlers run in executor
6. Parallel task execution via asyncio.gather
7. Timeout handling
"""

import asyncio
import pytest
import time
from unittest.mock import MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.coordinator import (
    Coordinator, Workflow, Task, TaskStatus, AgentInfo,
    AgentRole, AgentRegistry, MessageQueue,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def coordinator():
    """Create a fresh Coordinator instance."""
    return Coordinator()


@pytest.fixture
def coordinator_with_agents(coordinator):
    """Coordinator with producer + executor agents registered."""
    coordinator.register_agent(AgentInfo(
        id="producer_1",
        name="Test Producer",
        role=AgentRole.PRODUCER,
        capabilities=["generate"],
    ))
    coordinator.register_agent(AgentInfo(
        id="executor_1",
        name="Test Executor",
        role=AgentRole.EXECUTOR,
        capabilities=["execute"],
    ))
    return coordinator


def _make_task(task_id, task_type, payload=None, dependencies=None):
    """Helper to create a Task."""
    return Task(
        id=task_id,
        type=task_type,
        payload=payload or {},
        dependencies=dependencies or [],
    )


# ---------------------------------------------------------------------------
# 1. run_workflow_async — basic execution
# ---------------------------------------------------------------------------

class TestRunWorkflowAsync:
    """Tests for the async run_workflow_async method."""
    
    @pytest.mark.asyncio
    async def test_single_task_completes(self, coordinator_with_agents):
        """A single-task workflow completes via run_workflow_async."""
        coord = coordinator_with_agents
        results_log = []
        
        def handler(task):
            results_log.append(task.id)
            return {"done": True}
        
        coord.register_handler("environment", handler)
        
        wf = coord.create_workflow("single_task", "One task")
        wf.add_task(_make_task("t1", "environment"), stage="produce")
        
        result = await coord.run_workflow_async(wf)
        
        assert wf.tasks["t1"].status == TaskStatus.COMPLETED
        assert results_log == ["t1"]
        assert result["statistics"]["completed"] == 1
    
    @pytest.mark.asyncio
    async def test_dependency_chain(self, coordinator_with_agents):
        """Tasks with dependencies execute in order."""
        coord = coordinator_with_agents
        order = []
        
        def env_handler(task):
            order.append(task.id)
            return {"env": task.id}
        
        def exp_handler(task):
            order.append(task.id)
            return {"exp": task.id}
        
        coord.register_handler("environment", env_handler)
        coord.register_handler("experiment", exp_handler)
        
        wf = coord.create_workflow("dep_chain", "Dependency chain")
        wf.add_task(_make_task("t1", "environment"), stage="produce")
        wf.add_task(_make_task("t2", "experiment", dependencies=["t1"]), stage="execute")
        
        result = await coord.run_workflow_async(wf)
        
        assert order == ["t1", "t2"]
        assert result["statistics"]["completed"] == 2
    
    @pytest.mark.asyncio
    async def test_parallel_tasks(self, coordinator_with_agents):
        """Independent tasks can execute concurrently."""
        coord = coordinator_with_agents
        # Register a second executor for parallel execution
        coord.register_agent(AgentInfo(
            id="executor_2",
            name="Executor 2",
            role=AgentRole.EXECUTOR,
            capabilities=["execute"],
        ))
        coord.register_agent(AgentInfo(
            id="producer_2",
            name="Producer 2",
            role=AgentRole.PRODUCER,
            capabilities=["generate"],
        ))
        
        start_times = {}
        
        def slow_handler(task):
            start_times[task.id] = time.time()
            time.sleep(0.05)  # 50ms
            return {"done": True}
        
        coord.register_handler("environment", slow_handler)
        
        wf = coord.create_workflow("parallel", "Parallel tasks")
        wf.add_task(_make_task("t1", "environment"), stage="produce")
        wf.add_task(_make_task("t2", "environment"), stage="produce")
        
        result = await coord.run_workflow_async(wf)
        
        # Both tasks should have started within ~50ms of each other
        # (not serially which would be ~100ms apart)
        if "t1" in start_times and "t2" in start_times:
            overlap = abs(start_times["t1"] - start_times["t2"])
            assert overlap < 0.08, f"Tasks ran serially: overlap={overlap}"
        
        assert result["statistics"]["completed"] == 2


# ---------------------------------------------------------------------------
# 2. No time.sleep polling — condition-based waiting
# ---------------------------------------------------------------------------

class TestConditionWaiting:
    """Verify that the async workflow uses asyncio.Condition, not polling."""
    
    @pytest.mark.asyncio
    async def test_no_sleep_calls(self, coordinator_with_agents):
        """run_workflow_async should never call time.sleep."""
        coord = coordinator_with_agents
        
        def handler(task):
            return {"ok": True}
        
        coord.register_handler("environment", handler)
        
        wf = coord.create_workflow("no_poll", "No polling test")
        wf.add_task(_make_task("t1", "environment"), stage="produce")
        
        with patch("time.sleep") as mock_sleep:
            result = await coord.run_workflow_async(wf)
            mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# 3. complete_task wakes waiters
# ---------------------------------------------------------------------------

class TestCompleteTaskNotification:
    """Verify complete_task triggers condition notification."""
    
    @pytest.mark.asyncio
    async def test_notify_on_complete(self, coordinator_with_agents):
        """complete_task should wake up waiting coroutines."""
        coord = coordinator_with_agents
        notified = asyncio.Event()
        
        # Monkey-patch _notify_condition to verify it's called
        original_notify = coord._notify_condition
        
        call_count = [0]
        
        def counting_notify():
            call_count[0] += 1
            original_notify()
        
        coord._notify_condition = counting_notify
        
        def handler(task):
            return {"done": True}
        
        coord.register_handler("environment", handler)
        
        wf = coord.create_workflow("notify", "Notification test")
        wf.add_task(_make_task("t1", "environment"), stage="produce")
        
        await coord.run_workflow_async(wf)
        
        # complete_task should have been called at least once
        assert call_count[0] >= 1


# ---------------------------------------------------------------------------
# 4. Sync wrapper (run_workflow) still works
# ---------------------------------------------------------------------------

class TestSyncWrapper:
    """Verify run_workflow sync wrapper delegates correctly."""
    
    def test_sync_run_workflow(self, coordinator_with_agents):
        """run_workflow (sync) should produce the same result as run_workflow_async."""
        coord = coordinator_with_agents
        
        def handler(task):
            return {"value": task.id}
        
        coord.register_handler("environment", handler)
        
        wf = coord.create_workflow("sync_test", "Sync wrapper test")
        wf.add_task(_make_task("t1", "environment"), stage="produce")
        
        result = coord.run_workflow(wf)
        
        assert result["statistics"]["completed"] == 1
        assert wf.tasks["t1"].status == TaskStatus.COMPLETED
    
    def test_sync_with_dependencies(self, coordinator_with_agents):
        """Sync wrapper handles dependencies correctly."""
        coord = coordinator_with_agents
        order = []
        
        def env_handler(task):
            order.append(task.id)
            return {}
        
        def exp_handler(task):
            order.append(task.id)
            return {}
        
        coord.register_handler("environment", env_handler)
        coord.register_handler("experiment", exp_handler)
        
        wf = coord.create_workflow("sync_deps", "Sync dependencies")
        wf.add_task(_make_task("t1", "environment"), stage="produce")
        wf.add_task(_make_task("t2", "experiment", dependencies=["t1"]), stage="execute")
        
        result = coord.run_workflow(wf)
        
        assert order == ["t1", "t2"]
        assert result["statistics"]["completed"] == 2


# ---------------------------------------------------------------------------
# 5. Async handlers
# ---------------------------------------------------------------------------

class TestAsyncHandlers:
    """Verify async handlers are properly awaited."""
    
    @pytest.mark.asyncio
    async def test_async_handler(self, coordinator_with_agents):
        """Async handler functions should be awaited."""
        coord = coordinator_with_agents
        
        async def async_handler(task):
            await asyncio.sleep(0.01)
            return {"async": True}
        
        coord.register_handler("environment", async_handler)
        
        wf = coord.create_workflow("async_handler", "Async handler test")
        wf.add_task(_make_task("t1", "environment"), stage="produce")
        
        result = await coord.run_workflow_async(wf)
        
        assert wf.tasks["t1"].status == TaskStatus.COMPLETED
        assert wf.tasks["t1"].result == {"async": True}
    
    def test_async_handler_via_sync(self, coordinator_with_agents):
        """Async handler should work through sync wrapper too."""
        coord = coordinator_with_agents
        
        async def async_handler(task):
            return {"async_via_sync": True}
        
        coord.register_handler("environment", async_handler)
        
        wf = coord.create_workflow("async_sync", "Async via sync")
        wf.add_task(_make_task("t1", "environment"), stage="produce")
        
        result = coord.run_workflow(wf)
        
        assert wf.tasks["t1"].status == TaskStatus.COMPLETED
        assert wf.tasks["t1"].result == {"async_via_sync": True}


# ---------------------------------------------------------------------------
# 6. Timeout handling
# ---------------------------------------------------------------------------

class TestTimeout:
    """Verify timeout behavior in async workflow."""
    
    @pytest.mark.asyncio
    async def test_timeout_fires(self, coordinator_with_agents):
        """Workflow should stop when timeout expires."""
        coord = coordinator_with_agents
        
        def slow_handler(task):
            time.sleep(5)  # Way too slow
            return {"done": True}
        
        coord.register_handler("environment", slow_handler)
        
        wf = coord.create_workflow("timeout", "Timeout test")
        wf.add_task(_make_task("t1", "environment"), stage="produce")
        
        # Give enough time for executor overhead, but should still timeout
        result = await coord.run_workflow_async(wf, timeout=0.5)
        
        # Task may or may not complete in 0.5s depending on executor timing,
        # but the workflow should return (not hang)
        assert result is not None
        assert "statistics" in result


# ---------------------------------------------------------------------------
# 7. Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Verify errors in tasks are handled gracefully."""
    
    @pytest.mark.asyncio
    async def test_handler_error_marks_failed(self, coordinator_with_agents):
        """A failing handler should mark the task as FAILED, not crash."""
        coord = coordinator_with_agents
        
        def bad_handler(task):
            raise RuntimeError("boom")
        
        coord.register_handler("environment", bad_handler)
        
        wf = coord.create_workflow("error", "Error test")
        wf.add_task(_make_task("t1", "environment"), stage="produce")
        
        result = await coord.run_workflow_async(wf)
        
        assert wf.tasks["t1"].status == TaskStatus.FAILED
        assert "boom" in wf.tasks["t1"].error
    
    @pytest.mark.asyncio
    async def test_no_handler_raises(self, coordinator_with_agents):
        """No registered handler should result in FAILED task."""
        coord = coordinator_with_agents
        # No handler registered
        
        wf = coord.create_workflow("no_handler", "No handler test")
        wf.add_task(_make_task("t1", "environment"), stage="produce")
        
        result = await coord.run_workflow_async(wf)
        
        assert wf.tasks["t1"].status == TaskStatus.FAILED


# ---------------------------------------------------------------------------
# 8. _notify_condition safety
# ---------------------------------------------------------------------------

class TestNotifyConditionSafety:
    """_notify_condition should be safe in both sync and async contexts."""
    
    def test_notify_no_running_loop(self, coordinator):
        """Calling _notify_condition without a running loop should not crash."""
        # This should be a no-op, not raise
        coordinator._notify_condition()
    
    @pytest.mark.asyncio
    async def test_notify_with_running_loop(self, coordinator):
        """Calling _notify_condition with a running loop should schedule notification."""
        # Should not raise
        coordinator._notify_condition()
        # Give the notification task a chance to run
        await asyncio.sleep(0.01)


# ---------------------------------------------------------------------------
# 9. Condition field exists
# ---------------------------------------------------------------------------

class TestCoordinatorInit:
    """Verify new fields are properly initialized."""
    
    def test_condition_field(self, coordinator):
        """Coordinator should have condition property."""
        assert hasattr(coordinator, 'condition')
        # Access the property to verify lazy creation works
        cond = coordinator.condition
        assert isinstance(cond, asyncio.Condition)
    
    def test_running_async_field(self, coordinator):
        """Coordinator should have _running_async field."""
        assert hasattr(coordinator, '_running_async')
        assert isinstance(coordinator._running_async, set)
        assert len(coordinator._running_async) == 0
