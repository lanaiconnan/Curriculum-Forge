"""
ACP Core Data Model and Session Registry

Data model:
- ACPAgent: registered external agent
- ACPTask: task assigned to an agent
- ACPSessionRegistry: in-memory registry + SSE management
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("acp")

# ── Enums ──────────────────────────────────────────────────────────────────────


class ACPTaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class ACPAgentStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    OFFLINE = "offline"


# ── Data Models ────────────────────────────────────────────────────────────────


@dataclass
class ACPAgent:
    agent_id: str
    name: str
    role: str
    capabilities: List[str] = field(default_factory=list)
    status: ACPAgentStatus = ACPAgentStatus.IDLE
    current_task_id: Optional[str] = None
    registered_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "capabilities": self.capabilities,
            "status": self.status.value,
            "current_task_id": self.current_task_id,
            "registered_at": self.registered_at,
            "last_seen": self.last_seen,
        }


@dataclass
class ACPTask:
    task_id: str
    agent_id: str
    task_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    assigned_at: float = field(default_factory=time.time)
    status: ACPTaskStatus = ACPTaskStatus.PENDING
    progress_pct: int = 0
    message: str = ""
    result: Optional[Dict[str, Any]] = None
    completed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "task_type": self.task_type,
            "payload": self.payload,
            "assigned_at": self.assigned_at,
            "status": self.status.value,
            "progress_pct": self.progress_pct,
            "message": self.message,
            "result": self.result,
            "completed_at": self.completed_at,
        }


# ── Session Registry ───────────────────────────────────────────────────────────


class ACPSessionRegistry:
    """
    In-memory registry for external ACP agents and their tasks.
    Manages SSE queues for real-time event delivery.
    """

    def __init__(self, heartbeat_ttl: float = 60.0):
        # agent_id → ACPAgent
        self._agents: Dict[str, ACPAgent] = {}
        # agent_id → asyncio.Queue for SSE stream
        self._sse_queues: Dict[str, asyncio.Queue] = {}
        # task_id → ACPTask
        self._tasks: Dict[str, ACPTask] = {}
        # task_id → Set[agent_id] for quick reverse lookup
        self._task_to_agent: Dict[str, str] = {}
        # heartbeat TTL in seconds
        self._heartbeat_ttl = heartbeat_ttl
        self._lock = asyncio.Lock()

    # ── Agent Management ────────────────────────────────────────────────────────

    def register(self, agent: ACPAgent) -> str:
        """Register a new external agent. Returns session_id."""
        if agent.agent_id in self._agents:
            # Re-register (reconnect) — keep existing tasks
            self._agents[agent.agent_id].status = ACPAgentStatus.IDLE
            self._agents[agent.agent_id].last_seen = time.time()
            logger.info(f"ACP agent re-registered: {agent.agent_id}")
            return agent.agent_id

        self._agents[agent.agent_id] = agent
        self._sse_queues[agent.agent_id] = asyncio.Queue()
        logger.info(
            f"ACP agent registered: {agent.agent_id} role={agent.role} "
            f"capabilities={agent.capabilities}"
        )
        return agent.agent_id

    def unregister(self, agent_id: str) -> bool:
        """Unregister an agent. Returns True if found."""
        if agent_id not in self._agents:
            return False
        del self._agents[agent_id]
        # Cancel SSE queue
        if agent_id in self._sse_queues:
            q = self._sse_queues.pop(agent_id)
            q.put_nowait(None)  # Signal stream to close
        # Remove agent from tasks
        for task in self._tasks.values():
            if task.agent_id == agent_id and task.status == ACPTaskStatus.PENDING:
                task.status = ACPTaskStatus.CANCELLED
        logger.info(f"ACP agent unregistered: {agent_id}")
        return True

    def get_agent(self, agent_id: str) -> Optional[ACPAgent]:
        return self._agents.get(agent_id)

    def list_agents(self) -> List[ACPAgent]:
        return list(self._agents.values())

    def heartbeat(self, agent_id: str, progress_pct: Optional[int] = None, message: str = "") -> bool:
        """Update agent last_seen and optionally task progress. Returns True if agent found."""
        agent = self._agents.get(agent_id)
        if not agent:
            return False
        agent.last_seen = time.time()
        if progress_pct is not None and agent.current_task_id:
            task = self._tasks.get(agent.current_task_id)
            if task:
                task.progress_pct = min(100, max(0, progress_pct))
                if message:
                    task.message = message
        return True

    def get_stale_agents(self) -> List[str]:
        """Return agent_ids that have missed heartbeat TTL."""
        now = time.time()
        return [
            aid for aid, a in self._agents.items()
            if now - a.last_seen > self._heartbeat_ttl and a.status != ACPAgentStatus.OFFLINE
        ]

    def mark_offline(self, agent_id: str) -> None:
        if agent_id in self._agents:
            self._agents[agent_id].status = ACPAgentStatus.OFFLINE

    # ── Task Management ───────────────────────────────────────────────────────

    def assign_task(self, task: ACPTask) -> None:
        """Assign a task to an agent."""
        self._tasks[task.task_id] = task
        self._task_to_agent[task.task_id] = task.agent_id
        agent = self._agents.get(task.agent_id)
        if agent:
            agent.current_task_id = task.task_id
            agent.status = ACPAgentStatus.BUSY
        # Push SSE event
        asyncio.create_task(self._push_event(task.agent_id, {
            "type": "task_assigned",
            "task_id": task.task_id,
            "task_type": task.task_type,
            "payload": task.payload,
        }))
        logger.info(f"ACP task assigned: {task.task_id} → {task.agent_id}")

    async def _push_event(self, agent_id: str, event: Dict[str, Any]) -> None:
        """Push an event to an agent's SSE queue."""
        q = self._sse_queues.get(agent_id)
        if q:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"ACP SSE queue full for {agent_id}, dropping event")

    def claim_task(self, agent_id: str, task_id: str) -> Optional[ACPTask]:
        """Agent claims a pending task."""
        task = self._tasks.get(task_id)
        if not task or task.status != ACPTaskStatus.PENDING:
            return None
        if task.agent_id != agent_id:
            # Allow any registered agent to claim any pending task (role-free for v1)
            task.agent_id = agent_id
            task._original_assigned = task.agent_id
        task.status = ACPTaskStatus.IN_PROGRESS
        agent = self._agents.get(agent_id)
        if agent:
            agent.current_task_id = task_id
            agent.status = ACPAgentStatus.BUSY
        logger.info(f"ACP task claimed: {task_id} by {agent_id}")
        return task

    def complete_task(self, agent_id: str, task_id: str, result: Dict[str, Any]) -> Optional[ACPTask]:
        """Mark task as done with result."""
        task = self._tasks.get(task_id)
        if not task:
            return None
        task.status = ACPTaskStatus.DONE
        task.result = result
        task.completed_at = time.time()
        task.progress_pct = 100
        agent = self._agents.get(agent_id)
        if agent:
            agent.current_task_id = None
            agent.status = ACPAgentStatus.IDLE
        # Push SSE event
        asyncio.create_task(self._push_event(agent_id, {
            "type": "task_completed",
            "task_id": task_id,
            "result": result,
        }))
        logger.info(f"ACP task completed: {task_id} by {agent_id}")
        return task

    def abort_task(self, task_id: str) -> bool:
        """Abort a pending/in-progress task and notify agent."""
        task = self._tasks.get(task_id)
        if not task:
            return False
        task.status = ACPTaskStatus.CANCELLED
        # Notify agent via SSE
        asyncio.create_task(self._push_event(task.agent_id, {
            "type": "task_aborted",
            "task_id": task_id,
        }))
        agent = self._agents.get(task.agent_id)
        if agent:
            if agent.current_task_id == task_id:
                agent.current_task_id = None
                agent.status = ACPAgentStatus.IDLE
        logger.info(f"ACP task aborted: {task_id}")
        return True

    def get_tasks_for_agent(self, agent_id: str, status: Optional[ACPTaskStatus] = None) -> List[ACPTask]:
        """List tasks for an agent, optionally filtered by status."""
        tasks = [t for t in self._tasks.values() if t.agent_id == agent_id]
        if status:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    def get_task(self, task_id: str) -> Optional[ACPTask]:
        return self._tasks.get(task_id)

    # ── SSE Stream ───────────────────────────────────────────────────────────

    async def get_event_queue(self, agent_id: str) -> asyncio.Queue:
        """Get or create the SSE queue for an agent."""
        if agent_id not in self._sse_queues:
            self._sse_queues[agent_id] = asyncio.Queue(maxsize=64)
        return self._sse_queues[agent_id]

    async def stream_events(self, agent_id: str):
        """
        Async generator for SSE. Yields dicts as SSE-formatted strings.
        Yields None when stream should close.
        """
        q = await self.get_event_queue(agent_id)
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=60.0)
                if event is None:
                    break
                yield f"data: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                # Keepalive
                yield f": keepalive {int(time.time())}\n\n"

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_agents": len(self._agents),
            "total_tasks": len(self._tasks),
            "pending_tasks": sum(1 for t in self._tasks.values() if t.status == ACPTaskStatus.PENDING),
            "done_tasks": sum(1 for t in self._tasks.values() if t.status == ACPTaskStatus.DONE),
            "idle_agents": sum(1 for a in self._agents.values() if a.status == ACPAgentStatus.IDLE),
            "busy_agents": sum(1 for a in self._agents.values() if a.status == ACPAgentStatus.BUSY),
        }


# ── Helpers ──────────────────────────────────────────────────────────────────

import json


def new_task_id() -> str:
    return f"acp-task-{uuid.uuid4().hex[:12]}"
