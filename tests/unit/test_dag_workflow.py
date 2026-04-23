"""Tests for DAG Workflow support (Phase 2 Item 3)."""

import asyncio
import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from services.coordinator import (
    Coordinator,
    AgentInfo,
    AgentRole,
    DAGNode,
    Task,
    TaskStatus,
    Workflow,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_coordinator_with_agents():
    """Create a coordinator with agents for all roles."""
    coordinator = Coordinator()
    coordinator.register_agent(AgentInfo(
        id="producer", name="P", role=AgentRole.PRODUCER,
    ))
    coordinator.register_agent(AgentInfo(
        id="executor", name="E", role=AgentRole.EXECUTOR,
    ))
    coordinator.register_agent(AgentInfo(
        id="reviewer", name="R", role=AgentRole.REVIEWER,
    ))
    return coordinator


# ── Tests: DAGNode ────────────────────────────────────────────────────────────

def test_dag_node_is_ready_no_deps():
    """Node with no dependencies is always ready."""
    node = DAGNode(id="n1", name="start")
    assert node.is_ready(set()) is True


def test_dag_node_is_ready_with_deps():
    """Node is ready only when all dependencies are completed."""
    node = DAGNode(id="n2", name="after", dependencies=["n1"])
    assert node.is_ready(set()) is False
    assert node.is_ready({"n1"}) is True


def test_dag_node_is_ready_partial_deps():
    """Node with multiple deps needs all completed."""
    node = DAGNode(id="n3", name="multi", dependencies=["n1", "n2"])
    assert node.is_ready({"n1"}) is False
    assert node.is_ready({"n1", "n2"}) is True


# ── Tests: Workflow DAG ───────────────────────────────────────────────────────

def test_workflow_add_dag_node():
    """Workflow accepts DAG nodes."""
    workflow = Coordinator().create_workflow("test", "dag test")
    node = DAGNode(id="n1", name="produce", task_ids=["t1"])
    task = Task(id="t1", type="environment", payload={})
    workflow.tasks["t1"] = task
    workflow.add_dag_node(node)
    
    assert "n1" in workflow.dag_nodes
    assert workflow._use_dag is True


def test_workflow_dag_auto_wires_task_deps():
    """add_dag_node() automatically wires task-level dependencies from node deps."""
    workflow = Coordinator().create_workflow("test", "dag test")
    
    # Node 1: produce
    t1 = Task(id="t1", type="environment", payload={})
    workflow.tasks["t1"] = t1
    n1 = DAGNode(id="n1", name="produce", task_ids=["t1"])
    workflow.add_dag_node(n1)
    
    # Node 2: execute (depends on produce)
    t2 = Task(id="t2", type="experiment", payload={}, dependencies=[])
    workflow.tasks["t2"] = t2
    n2 = DAGNode(id="n2", name="execute", task_ids=["t2"], dependencies=["n1"])
    workflow.add_dag_node(n2)
    
    # t2 should now have t1 as a dependency
    assert "t1" in t2.dependencies


def test_workflow_dag_multi_dep():
    """DAG node with multiple dependencies auto-wires correctly."""
    workflow = Coordinator().create_workflow("test", "dag test")
    
    t1 = Task(id="t1", type="environment", payload={})
    t2 = Task(id="t2", type="environment", payload={})
    t3 = Task(id="t3", type="review", payload={}, dependencies=[])
    
    workflow.tasks["t1"] = t1
    workflow.tasks["t2"] = t2
    workflow.tasks["t3"] = t3
    
    n1 = DAGNode(id="n1", name="env_a", task_ids=["t1"])
    n2 = DAGNode(id="n2", name="env_b", task_ids=["t2"])
    n3 = DAGNode(id="n3", name="review", task_ids=["t3"], dependencies=["n1", "n2"])
    
    workflow.add_dag_node(n1)
    workflow.add_dag_node(n2)
    workflow.add_dag_node(n3)
    
    # t3 should depend on both t1 and t2
    assert "t1" in t3.dependencies
    assert "t2" in t3.dependencies


# ── Tests: DAG Workflow Execution ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dag_linear_execution():
    """Linear DAG (A → B → C) executes in order."""
    coordinator = _make_coordinator_with_agents()
    
    execution_order = []
    
    async def track_handler(task_type):
        async def handler(task):
            execution_order.append(task.id)
            return {"status": "ok", "task_id": task.id}
        return handler
    
    coordinator.register_handler("environment", await track_handler("environment"))
    coordinator.register_handler("experiment", await track_handler("experiment"))
    coordinator.register_handler("review", await track_handler("review"))
    
    workflow = coordinator.create_workflow("linear_dag", "linear DAG test")
    
    t1 = Task(id="t1", type="environment", payload={})
    t2 = Task(id="t2", type="experiment", payload={}, dependencies=["t1"])
    t3 = Task(id="t3", type="review", payload={}, dependencies=["t2"])
    
    workflow.tasks["t1"] = t1
    workflow.tasks["t2"] = t2
    workflow.tasks["t3"] = t3
    
    n1 = DAGNode(id="n1", name="produce", task_ids=["t1"])
    n2 = DAGNode(id="n2", name="execute", task_ids=["t2"], dependencies=["n1"])
    n3 = DAGNode(id="n3", name="review", task_ids=["t3"], dependencies=["n2"])
    
    workflow.add_dag_node(n1)
    workflow.add_dag_node(n2)
    workflow.add_dag_node(n3)
    
    result = await coordinator.run_workflow_async(workflow, timeout=10)
    
    assert result["statistics"]["completed"] == 3
    assert execution_order == ["t1", "t2", "t3"]


@pytest.mark.asyncio
async def test_dag_parallel_execution():
    """Diamond DAG (A → B, A → C, B+C → D) allows B and C parallel."""
    coordinator = _make_coordinator_with_agents()
    
    # Need enough agents for parallel tasks
    coordinator.register_agent(AgentInfo(
        id="executor2", name="E2", role=AgentRole.EXECUTOR,
    ))
    
    execution_order = []
    
    async def handler(task):
        execution_order.append(task.id)
        return {"status": "ok", "task_id": task.id}
    
    coordinator.register_handler("environment", handler)
    coordinator.register_handler("experiment", handler)
    coordinator.register_handler("review", handler)
    coordinator.register_handler("training", handler)
    
    workflow = coordinator.create_workflow("diamond_dag", "diamond DAG test")
    
    t1 = Task(id="t1", type="environment", payload={})
    t2 = Task(id="t2", type="experiment", payload={}, dependencies=["t1"])
    t3 = Task(id="t3", type="training", payload={}, dependencies=["t1"])
    t4 = Task(id="t4", type="review", payload={}, dependencies=["t2", "t3"])
    
    workflow.tasks["t1"] = t1
    workflow.tasks["t2"] = t2
    workflow.tasks["t3"] = t3
    workflow.tasks["t4"] = t4
    
    n1 = DAGNode(id="n1", name="env", task_ids=["t1"])
    n2 = DAGNode(id="n2", name="exp", task_ids=["t2"], dependencies=["n1"])
    n3 = DAGNode(id="n3", name="train", task_ids=["t3"], dependencies=["n1"])
    n4 = DAGNode(id="n4", name="review", task_ids=["t4"], dependencies=["n2", "n3"])
    
    workflow.add_dag_node(n1)
    workflow.add_dag_node(n2)
    workflow.add_dag_node(n3)
    workflow.add_dag_node(n4)
    
    result = await coordinator.run_workflow_async(workflow, timeout=10)
    
    assert result["statistics"]["completed"] == 4
    # t1 must be first, t4 must be last
    assert execution_order[0] == "t1"
    assert execution_order[-1] == "t4"
    # t2 and t3 can be in either order (parallel)
    assert set(execution_order[1:3]) == {"t2", "t3"}


@pytest.mark.asyncio
async def test_dag_backward_compat_add_task():
    """Workflow.add_task() still works (backward compat, no DAG)."""
    coordinator = _make_coordinator_with_agents()
    
    async def handler(task):
        return {"status": "ok"}
    
    coordinator.register_handler("environment", handler)
    coordinator.register_handler("experiment", handler)
    
    workflow = coordinator.create_workflow("compat", "backward compat")
    
    t1 = Task(id="t1", type="environment", payload={})
    t2 = Task(id="t2", type="experiment", payload={}, dependencies=["t1"])
    
    coordinator.add_task(workflow, t1, "produce")
    coordinator.add_task(workflow, t2, "execute")
    
    assert workflow._use_dag is False
    assert "produce" in workflow.stages
    assert "execute" in workflow.stages
    
    result = await coordinator.run_workflow_async(workflow, timeout=10)
    assert result["statistics"]["completed"] == 2


# ── Tests: DAGNode in API response ────────────────────────────────────────────

def test_dag_node_metadata():
    """DAGNode supports arbitrary metadata."""
    node = DAGNode(
        id="n1",
        name="custom",
        metadata={"timeout": 30, "retry": 3},
    )
    assert node.metadata["timeout"] == 30
    assert node.metadata["retry"] == 3
