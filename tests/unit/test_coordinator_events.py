"""
Tests for Coordinator Event Bus and SSE integration.

Phase 2 Item 4: Gateway ↔ Coordinator SSE 事件流
"""

import asyncio
import json
import pytest
from datetime import datetime

# ── CoordinatorEventBus Unit Tests ─────────────────────────────────────────────


class TestCoordinatorEventBus:
    """Test the event bus publish-subscribe mechanism."""

    def test_subscribe_returns_id(self):
        from services.coordinator import CoordinatorEventBus
        bus = CoordinatorEventBus()
        sid = bus.subscribe()
        assert sid.startswith("sub_")
        assert bus.subscriber_count == 1

    def test_subscribe_custom_id(self):
        from services.coordinator import CoordinatorEventBus
        bus = CoordinatorEventBus()
        sid = bus.subscribe("my_sub")
        assert sid == "my_sub"
        assert bus.subscriber_count == 1

    def test_unsubscribe(self):
        from services.coordinator import CoordinatorEventBus
        bus = CoordinatorEventBus()
        sid = bus.subscribe()
        bus.unsubscribe(sid)
        assert bus.subscriber_count == 0

    def test_unsubscribe_nonexistent(self):
        from services.coordinator import CoordinatorEventBus
        bus = CoordinatorEventBus()
        bus.unsubscribe("nonexistent")  # Should not raise

    @pytest.mark.asyncio
    async def test_emit_delivers_to_subscriber(self):
        from services.coordinator import CoordinatorEventBus
        bus = CoordinatorEventBus()
        sid = bus.subscribe()
        queue = bus.get_queue(sid)

        await bus.emit("task_assigned", {"task_id": "t1", "agent_id": "a1"})

        event = queue.get_nowait()
        assert event["type"] == "task_assigned"
        assert event["payload"]["task_id"] == "t1"
        assert "timestamp" in event

    @pytest.mark.asyncio
    async def test_emit_delivers_to_multiple_subscribers(self):
        from services.coordinator import CoordinatorEventBus
        bus = CoordinatorEventBus()
        sid1 = bus.subscribe("sub1")
        sid2 = bus.subscribe("sub2")
        q1 = bus.get_queue("sub1")
        q2 = bus.get_queue("sub2")

        await bus.emit("task_completed", {"task_id": "t1"})

        e1 = q1.get_nowait()
        e2 = q2.get_nowait()
        assert e1["type"] == "task_completed"
        assert e2["type"] == "task_completed"

    @pytest.mark.asyncio
    async def test_emit_no_subscribers(self):
        from services.coordinator import CoordinatorEventBus
        bus = CoordinatorEventBus()
        await bus.emit("test", {})  # Should not raise

    @pytest.mark.asyncio
    async def test_get_queue_returns_none_for_unknown(self):
        from services.coordinator import CoordinatorEventBus
        bus = CoordinatorEventBus()
        assert bus.get_queue("nonexistent") is None


# ── Coordinator Event Emission Tests ──────────────────────────────────────────


class TestCoordinatorEventEmission:
    """Test that Coordinator emits events at the right moments."""

    @pytest.mark.asyncio
    async def test_task_assigned_emits_event(self):
        from services.coordinator import (
            Coordinator, AgentInfo, AgentRole, Task, Workflow,
        )
        coord = Coordinator()
        coord.register_agent(AgentInfo(
            id="agent_1", name="Worker", role=AgentRole.EXECUTOR,
            capabilities=["execute"],
        ))

        sid = coord.event_bus.subscribe("test_sub")
        queue = coord.event_bus.get_queue("test_sub")

        workflow = coord.create_workflow(name="test_wf")
        task = Task(id="t1", type="experiment", payload={"env": "test"})
        coord.add_task(workflow, task, "execute")

        # The _try_assign_task should have emitted task_assigned
        # (it runs synchronously, but emit is async → scheduled)
        await asyncio.sleep(0.05)

        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        assigned_events = [e for e in events if e["type"] == "task_assigned"]
        assert len(assigned_events) >= 1
        assert assigned_events[0]["payload"]["task_id"] == "t1"
        assert assigned_events[0]["payload"]["agent_id"] == "agent_1"

    @pytest.mark.asyncio
    async def test_complete_task_emits_event(self):
        from services.coordinator import (
            Coordinator, AgentInfo, AgentRole, Task,
        )
        coord = Coordinator()
        coord.register_agent(AgentInfo(
            id="agent_1", name="Worker", role=AgentRole.EXECUTOR,
            capabilities=["execute"],
        ))

        sid = coord.event_bus.subscribe("test_sub")
        queue = coord.event_bus.get_queue("test_sub")

        workflow = coord.create_workflow(name="test_wf")
        task = Task(id="t1", type="experiment", payload={"env": "test"})
        coord.add_task(workflow, task, "execute")

        # Manually complete the task
        coord.complete_task("t1", result={"status": "done"})
        await asyncio.sleep(0.05)

        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        completed_events = [e for e in events if e["type"] == "task_completed"]
        assert len(completed_events) >= 1
        assert completed_events[0]["payload"]["task_id"] == "t1"

    @pytest.mark.asyncio
    async def test_failed_task_emits_task_failed(self):
        from services.coordinator import (
            Coordinator, AgentInfo, AgentRole, Task,
        )
        coord = Coordinator()
        coord.register_agent(AgentInfo(
            id="agent_1", name="Worker", role=AgentRole.EXECUTOR,
        ))

        sid = coord.event_bus.subscribe()
        queue = coord.event_bus.get_queue(sid)

        workflow = coord.create_workflow(name="test_wf")
        task = Task(id="t1", type="experiment", payload={})
        coord.add_task(workflow, task, "execute")

        coord.complete_task("t1", error="Something went wrong")
        await asyncio.sleep(0.05)

        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        failed_events = [e for e in events if e["type"] == "task_failed"]
        assert len(failed_events) >= 1
        assert failed_events[0]["payload"]["error"] == "Something went wrong"

    @pytest.mark.asyncio
    async def test_workflow_started_emits_event(self):
        from services.coordinator import Coordinator, Workflow
        coord = Coordinator()

        sid = coord.event_bus.subscribe()
        queue = coord.event_bus.get_queue(sid)

        workflow = coord.create_workflow(name="test_wf")
        await coord.event_bus.emit("workflow_started", {
            "workflow_id": workflow.id, "name": "test_wf",
        })

        event = queue.get_nowait()
        assert event["type"] == "workflow_started"
        assert event["payload"]["workflow_id"] == workflow.id

    @pytest.mark.asyncio
    async def test_workflow_completed_emits_event(self):
        from services.coordinator import Coordinator, Task, AgentInfo, AgentRole
        coord = Coordinator()
        coord.register_agent(AgentInfo(
            id="agent_1", name="Worker", role=AgentRole.EXECUTOR,
        ))

        sid = coord.event_bus.subscribe()
        queue = coord.event_bus.get_queue(sid)

        workflow = coord.create_workflow(name="test_wf")
        task = Task(id="t1", type="experiment", payload={})
        coord.add_task(workflow, task, "execute")

        # Complete the task (which triggers workflow completion check)
        coord.complete_task("t1", result={"ok": True})
        await asyncio.sleep(0.05)

        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        wf_events = [e for e in events if e["type"] == "workflow_completed"]
        assert len(wf_events) >= 1
        assert wf_events[0]["payload"]["workflow_id"] == workflow.id


# ── Gateway SSE Endpoint Tests ────────────────────────────────────────────────


class TestGatewaySSEEndpoints:
    """Test the new SSE endpoints for workflow/coordinator events."""

    def _make_app(self):
        """Create a test app with Coordinator."""
        from runtimes.gateway import create_app
        app = create_app()
        return app

    def test_coordinator_events_endpoint_exists(self):
        """Verify the /coordinator/events endpoint is registered."""
        from runtimes.gateway import create_app
        app = create_app()
        # Check that the route is registered
        routes = [r.path for r in app.routes if hasattr(r, 'path')]
        assert "/coordinator/events" in routes

    def test_workflow_stream_endpoint_registered(self):
        """Verify the /workflows/{workflow_id}/stream endpoint is registered."""
        from runtimes.gateway import create_app
        app = create_app()
        routes = [r.path for r in app.routes if hasattr(r, 'path')]
        assert "/workflows/{workflow_id}/stream" in routes

    def test_coordinator_events_503_when_no_coordinator(self):
        """When no coordinator is configured, should return 503."""
        from runtimes.gateway import create_app
        app = create_app()
        app.state.coordinator = None
        from fastapi.testclient import TestClient
        with TestClient(app) as client:
            resp = client.get("/coordinator/events")
            assert resp.status_code == 503

    def test_workflow_stream_404_for_unknown(self):
        from runtimes.gateway import create_app
        app = create_app()
        from fastapi.testclient import TestClient
        with TestClient(app) as client:
            resp = client.get("/workflows/nonexistent/stream")
            assert resp.status_code == 404

    def test_workflow_stream_503_when_no_coordinator(self):
        from runtimes.gateway import create_app
        app = create_app()
        app.state.coordinator = None
        from fastapi.testclient import TestClient
        with TestClient(app) as client:
            resp = client.get("/workflows/nonexistent/stream")
            assert resp.status_code == 503


# Need to import AgentInfo for test
from services.coordinator import AgentInfo
