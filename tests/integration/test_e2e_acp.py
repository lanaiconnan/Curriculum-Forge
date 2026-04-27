"""
E2E Integration Test — ACP (Agent Control Protocol) Flows

Tests the full ACP lifecycle:
- Agent registration → heartbeat → task assignment → completion
- Agent deregistration and cleanup
- SSE event streaming for task notifications
- Multi-agent collaboration scenarios
"""

import asyncio
import json
import os
os.environ["CF_ENABLE_AUTH"] = "0"

import pytest
from fastapi.testclient import TestClient


class TestACPLifecycleE2E:
    """Full lifecycle E2E tests for ACP."""

    def _make_app(self):
        from runtimes.gateway import create_app
        return create_app()

    def test_register_and_list_agents(self):
        """Register an agent and verify it appears in the list."""
        app = self._make_app()
        with TestClient(app) as client:
            # Register
            resp = client.post("/acp/register", json={
                "agent_id": "e2e-agent-1",
                "name": "Test Agent 1",
                "role": "teacher",
                "capabilities": ["research", "code"],
            })
            assert resp.status_code == 201
            data = resp.json()
            assert data["agent_id"] == "e2e-agent-1"
            assert "session_id" in data
            assert "gateway_url" in data

            # Get individual agent (has full info including status)
            resp = client.get("/acp/e2e-agent-1")
            assert resp.status_code == 200
            agent_info = resp.json()
            assert agent_info["status"] == "idle"
            assert agent_info["name"] == "Test Agent 1"

            # List all agents
            resp = client.get("/acp")
            assert resp.status_code == 200
            list_data = resp.json()
            assert list_data["total"] >= 1
            agent_ids = [a["agent_id"] for a in list_data["agents"]]
            assert "e2e-agent-1" in agent_ids

    def test_register_duplicate_agent_reregisters(self):
        """Re-registering an existing agent should update status, not error."""
        app = self._make_app()
        with TestClient(app) as client:
            # First registration
            resp = client.post("/acp/register", json={
                "agent_id": "e2e-agent-dup",
                "name": "Dup Agent",
                "role": "learner",
                "capabilities": [],
            })
            assert resp.status_code == 201

            # Second registration (reconnect)
            resp = client.post("/acp/register", json={
                "agent_id": "e2e-agent-dup",
                "name": "Dup Agent Updated",
                "role": "learner",
                "capabilities": ["review"],
            })
            # Should succeed (re-register)
            assert resp.status_code in (200, 201)

    def test_deregister_agent(self):
        """Deregister an agent and verify it's removed."""
        app = self._make_app()
        with TestClient(app) as client:
            # Register first
            client.post("/acp/register", json={
                "agent_id": "e2e-agent-del",
                "name": "Delete Agent",
                "role": "reviewer",
                "capabilities": [],
            })

            # Deregister
            resp = client.delete("/acp/e2e-agent-del")
            assert resp.status_code == 200

            # Verify removed
            resp = client.get("/acp/e2e-agent-del")
            assert resp.status_code == 404

    def test_heartbeat_updates_last_seen(self):
        """Heartbeat should update agent's last_seen timestamp."""
        app = self._make_app()
        with TestClient(app) as client:
            # Register
            client.post("/acp/register", json={
                "agent_id": "e2e-agent-hb",
                "name": "Heartbeat Agent",
                "role": "general",
                "capabilities": [],
            })

            # Get initial agent info
            resp = client.get("/acp/e2e-agent-hb")
            assert resp.status_code == 200
            initial_last_seen = resp.json()["last_seen"]

            # Heartbeat
            resp = client.post("/acp/e2e-agent-hb/heartbeat", json={
                "progress_pct": 50,
                "message": "Working on it",
            })
            assert resp.status_code == 200

            # Verify last_seen updated
            resp = client.get("/acp/e2e-agent-hb")
            assert resp.status_code == 200
            assert resp.json()["last_seen"] >= initial_last_seen

    def test_heartbeat_nonexistent_agent(self):
        """Heartbeat for non-existent agent should return 404."""
        app = self._make_app()
        with TestClient(app) as client:
            resp = client.post("/acp/ghost-agent/heartbeat", json={})
            assert resp.status_code == 404

    def test_task_claim_and_complete(self):
        """Full task lifecycle: assign → claim → complete."""
        app = self._make_app()
        with TestClient(app) as client:
            # Register agent
            client.post("/acp/register", json={
                "agent_id": "e2e-task-agent",
                "name": "Task Agent",
                "role": "teacher",
                "capabilities": ["research"],
            })

            # Create a job first (provides task context)
            resp = client.post("/jobs", json={
                "profile": "rl_controller",
                "description": "ACP task test",
            })
            assert resp.status_code == 201
            job_id = resp.json()["job"]["id"]

            # List tasks for agent (should be empty initially)
            resp = client.get("/acp/e2e-task-agent/tasks")
            assert resp.status_code == 200
            tasks_data = resp.json()
            assert tasks_data["total"] == 0
            assert tasks_data["tasks"] == []

            # Create an ACP task via the registry directly
            # assign_task uses asyncio.create_task internally, so we need a running loop
            from acp.protocol import ACPSessionRegistry, ACPAgent, ACPTask
            registry = app.state.acp_registry
            task = ACPTask(
                task_id="e2e-task-1",
                agent_id="e2e-task-agent",
                task_type="research",
                payload={"query": "test query", "job_id": job_id},
            )
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(registry._push_event(task.agent_id, {
                    "type": "task_assigned", "task_id": task.task_id,
                }))
            except Exception:
                pass
            finally:
                loop.close()
            # assign_task stores the task synchronously, the event push is fire-and-forget
            # Just set it directly on the registry to avoid asyncio issues in sync test
            registry._tasks[task.task_id] = task
            registry._task_to_agent[task.task_id] = task.agent_id

            # Agent claims the task
            resp = client.post("/acp/e2e-task-agent/tasks/e2e-task-1/claim")
            assert resp.status_code == 200
            task_data = resp.json()["task"]
            assert task_data["status"] == "in_progress"

            # Agent completes the task
            resp = client.post("/acp/e2e-task-agent/tasks/e2e-task-1/complete", json={
                "result": {"answer": "test answer", "confidence": 0.95},
            })
            assert resp.status_code == 200
            task_data = resp.json()["task"]
            assert task_data["status"] == "done"
            assert task_data["result"]["answer"] == "test answer"

            # Agent should be idle again
            resp = client.get("/acp/e2e-task-agent")
            assert resp.status_code == 200
            assert resp.json()["status"] == "idle"


class TestACPMultiAgentE2E:
    """Multi-agent collaboration E2E tests."""

    def _make_app(self):
        from runtimes.gateway import create_app
        return create_app()

    def test_multiple_agents_register(self):
        """Multiple agents can register concurrently."""
        app = self._make_app()
        with TestClient(app) as client:
            agents = []
            for i in range(3):
                resp = client.post("/acp/register", json={
                    "agent_id": f"multi-agent-{i}",
                    "name": f"Agent {i}",
                    "role": ["teacher", "learner", "reviewer"][i],
                    "capabilities": ["research", "code", "review"],
                })
                assert resp.status_code == 201
                agents.append(f"multi-agent-{i}")

            # All should be listed
            resp = client.get("/acp")
            assert resp.status_code == 200
            list_data = resp.json()
            assert list_data["total"] >= 3
            agent_ids = [a["agent_id"] for a in list_data["agents"]]
            for aid in agents:
                assert aid in agent_ids

    def test_agent_deregister_cancels_pending_tasks(self):
        """When an agent deregisters, its pending tasks should be cancelled."""
        app = self._make_app()
        with TestClient(app) as client:
            # Register
            client.post("/acp/register", json={
                "agent_id": "e2e-cancel-agent",
                "name": "Cancel Agent",
                "role": "general",
                "capabilities": [],
            })

            # Assign a task (bypass asyncio in sync test by setting internals directly)
            from acp.protocol import ACPTask
            registry = app.state.acp_registry
            task = ACPTask(
                task_id="cancel-task-1",
                agent_id="e2e-cancel-agent",
                task_type="code",
                payload={},
            )
            registry._tasks[task.task_id] = task
            registry._task_to_agent[task.task_id] = task.agent_id

            # Deregister agent
            resp = client.delete("/acp/e2e-cancel-agent")
            assert resp.status_code == 200

            # Task should be cancelled
            stored_task = registry.get_task("cancel-task-1")
            assert stored_task is not None
            assert stored_task.status.value == "cancelled"

    def test_different_roles_registration(self):
        """Agents with different roles can coexist."""
        app = self._make_app()
        with TestClient(app) as client:
            roles = ["teacher", "learner", "reviewer", "general"]
            for i, role in enumerate(roles):
                resp = client.post("/acp/register", json={
                    "agent_id": f"role-agent-{role}",
                    "name": f"{role.title()} Agent",
                    "role": role,
                    "capabilities": [role],
                })
                assert resp.status_code == 201

            # Verify all roles present
            resp = client.get("/acp")
            list_data = resp.json()
            agents = list_data["agents"]
            registered_roles = {a["role"] for a in agents}
            for role in roles:
                assert role in registered_roles


class TestACPSSEEventsE2E:
    """ACP SSE event streaming E2E tests."""

    def _make_app(self):
        from runtimes.gateway import create_app
        return create_app()

    def test_sse_stream_nonexistent_agent(self):
        """SSE stream for non-existent agent should return 404."""
        app = self._make_app()
        with TestClient(app) as client:
            resp = client.get("/acp/ghost-sse/stream")
            assert resp.status_code == 404
