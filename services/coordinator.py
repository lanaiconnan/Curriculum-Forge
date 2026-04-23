"""Coordinator - Multi-Agent Task Coordination

Based on Claude Code's coordinator/ architecture.
Provides:
- Task queue management
- Agent message passing
- Parallel execution coordination
- Result aggregation

Key Design Patterns (from Claude Code):
1. Task -> Agent assignment with load balancing
2. Message queue for agent communication
3. Parallel execution with barrier synchronization
4. Result aggregation with timeout handling
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, Type, Set
from enum import Enum
from datetime import datetime
import uuid
import logging
import asyncio

from providers.base import RunState

# Backward-compatible alias: TaskStatus → RunState
TaskStatus = RunState

logger = logging.getLogger(__name__)


# ── Coordinator Event Bus ────────────────────────────────────────────────────

class CoordinatorEventBus:
    """Publish-subscribe event bus for Coordinator events.
    
    Enables Gateway and other subscribers to react to Coordinator
    state changes (task assignment, completion, agent status, etc.)
    without polling.
    
    Each subscriber gets its own asyncio.Queue. Events are broadcast
    to all subscribers.
    """
    
    def __init__(self):
        self._subscribers: Dict[str, asyncio.Queue] = {}
        self._counter: int = 0
    
    def subscribe(self, subscriber_id: Optional[str] = None) -> str:
        """Subscribe to events. Returns the subscriber_id."""
        if subscriber_id is None:
            self._counter += 1
            subscriber_id = f"sub_{self._counter}"
        self._subscribers[subscriber_id] = asyncio.Queue()
        logger.debug(f"EventBus subscriber added: {subscriber_id}")
        return subscriber_id
    
    def unsubscribe(self, subscriber_id: str) -> None:
        """Unsubscribe from events."""
        self._subscribers.pop(subscriber_id, None)
    
    async def emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Emit an event to all subscribers."""
        event = {
            "type": event_type,
            "payload": payload,
            "timestamp": datetime.now().isoformat(),
        }
        dead = []
        for sid, queue in self._subscribers.items():
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"EventBus subscriber {sid} queue full, dropping event")
                dead.append(sid)
        for sid in dead:
            self._subscribers.pop(sid, None)
    
    def emit_sync(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Emit an event synchronously (safe from sync or async context).
        
        Puts the event directly into subscriber queues without awaiting.
        This is safe because Queue.put_nowait() doesn't need an event loop.
        """
        event = {
            "type": event_type,
            "payload": payload,
            "timestamp": datetime.now().isoformat(),
        }
        dead = []
        for sid, queue in self._subscribers.items():
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"EventBus subscriber {sid} queue full, dropping event")
                dead.append(sid)
        for sid in dead:
            self._subscribers.pop(sid, None)
    
    def get_queue(self, subscriber_id: str) -> Optional[asyncio.Queue]:
        """Get the queue for a subscriber."""
        return self._subscribers.get(subscriber_id)
    
    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


class AgentRole(Enum):
    """Agent roles in the coordinator"""
    PRODUCER = "producer"      # Generates tasks
    EXECUTOR = "executor"      # Executes tasks
    REVIEWER = "reviewer"      # Reviews results
    ORCHESTRATOR = "orchestrator"  # Coordinates workflow


@dataclass
class AgentInfo:
    """Information about a registered agent"""
    id: str
    name: str
    role: AgentRole
    capabilities: List[str] = field(default_factory=list)
    status: str = "idle"  # idle, busy, offline
    current_task: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_available(self) -> bool:
        return self.status == "idle"


@dataclass
class Task:
    """
    A unit of work to be executed by an agent.
    
    This is the core abstraction for task distribution.
    """
    id: str
    type: str  # "environment", "experiment", "review", "training"
    payload: Dict[str, Any]
    priority: int = 0  # Higher = more urgent
    timeout: float = 300.0  # seconds
    
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent: Optional[str] = None
    
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    dependencies: List[str] = field(default_factory=list)  # Task IDs this depends on
    
    def duration(self) -> Optional[float]:
        """Calculate task duration in seconds"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    def is_blocked(self, completed_tasks: set) -> bool:
        """Check if task is blocked by dependencies"""
        return any(dep_id not in completed_tasks for dep_id in self.dependencies)


@dataclass
class Message:
    """
    Message passed between agents.
    
    Enables asynchronous communication and coordination.
    """
    id: str
    from_agent: str
    to_agent: str  # "*" for broadcast
    type: str  # "task", "result", "feedback", "status", "control"
    payload: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    reply_to: Optional[str] = None  # Message ID to reply to
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "from": self.from_agent,
            "to": self.to_agent,
            "type": self.type,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class DAGNode:
    """A node in a DAG workflow.
    
    Unlike linear stages, DAG nodes support arbitrary dependency
    relationships, enabling parallel execution where possible.
    """
    id: str
    name: str
    task_ids: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)  # Node IDs this depends on
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_ready(self, completed_nodes: set) -> bool:
        """Check if this node's dependencies are satisfied."""
        return all(dep in completed_nodes for dep in self.dependencies)


@dataclass
class Workflow:
    """
    A coordinated workflow involving multiple agents.
    
    Defines the execution plan and manages task dependencies.
    """
    id: str
    name: str
    description: str
    
    stages: List[str] = field(default_factory=list)  # Stage names (legacy, linear)
    stage_tasks: Dict[str, List[str]] = field(default_factory=dict)  # stage -> task IDs (legacy)
    
    # DAG support (Phase 2 Item 3)
    dag_nodes: Dict[str, DAGNode] = field(default_factory=dict)  # node_id → DAGNode
    _use_dag: bool = False  # Internal flag: True when add_dag_node() is used
    
    tasks: Dict[str, Task] = field(default_factory=dict)
    agents: Dict[str, AgentInfo] = field(default_factory=dict)
    
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    current_stage: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_task(self, task: Task, stage: str) -> None:
        """Add a task to a specific stage (linear, backward-compatible)."""
        self.tasks[task.id] = task
        if stage not in self.stage_tasks:
            self.stage_tasks[stage] = []
            self.stages.append(stage)
        self.stage_tasks[stage].append(task.id)
    
    def add_dag_node(self, node: DAGNode) -> None:
        """Add a DAG node to the workflow.
        
        When DAG nodes are used, get_ready_tasks() uses DAG topology
        instead of linear stage ordering.
        """
        self.dag_nodes[node.id] = node
        self._use_dag = True
        
        # Register tasks that belong to this node
        for task_id in node.task_ids:
            if task_id in self.tasks:
                # Add node-level dependencies as task-level dependencies
                for dep_node_id in node.dependencies:
                    dep_node = self.dag_nodes.get(dep_node_id)
                    if dep_node:
                        for dep_task_id in dep_node.task_ids:
                            if dep_task_id not in self.tasks[task_id].dependencies:
                                self.tasks[task_id].dependencies.append(dep_task_id)
    
    def get_ready_tasks(self, completed: set) -> List[Task]:
        """Get tasks that are ready to execute.
        
        If DAG nodes are defined, uses DAG topology.
        Otherwise, uses linear stage ordering.
        """
        ready = []
        for task in self.tasks.values():
            if task.status == TaskStatus.PENDING and not task.is_blocked(completed):
                ready.append(task)
        return sorted(ready, key=lambda t: -t.priority)
    
    def is_complete(self) -> bool:
        """Check if workflow is complete"""
        return all(
            t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
            for t in self.tasks.values()
        )


class MessageQueue:
    """
    Asynchronous message queue for agent communication.
    
    Supports:
    - Direct messages (to a specific agent)
    - Broadcast messages (to all agents)
    - Message filtering by type
    - Reply tracking
    """
    
    def __init__(self):
        self._messages: List[Message] = []
        self._by_recipient: Dict[str, List[Message]] = {}
        self._callbacks: Dict[str, List[Callable[[Message], None]]] = {}
    
    def send(self, message: Message) -> None:
        """Send a message"""
        self._messages.append(message)
        
        # Index by recipient
        if message.to_agent not in self._by_recipient:
            self._by_recipient[message.to_agent] = []
        self._by_recipient[message.to_agent].append(message)
        
        # Trigger callbacks
        for callback in self._callbacks.get(message.type, []):
            callback(message)
        
        logger.debug(f"Message {message.id}: {message.from_agent} -> {message.to_agent}")
    
    def broadcast(self, from_agent: str, msg_type: str, payload: Dict[str, Any]) -> Message:
        """Send a broadcast message to all agents"""
        message = Message(
            id=str(uuid.uuid4()),
            from_agent=from_agent,
            to_agent="*",
            type=msg_type,
            payload=payload,
        )
        self.send(message)
        return message
    
    def receive(self, agent_id: str, msg_type: Optional[str] = None) -> List[Message]:
        """Receive messages for an agent"""
        messages = self._by_recipient.get(agent_id, [])
        if msg_type:
            messages = [m for m in messages if m.type == msg_type]
        return messages
    
    def register_callback(self, msg_type: str, callback: Callable[[Message], None]) -> None:
        """Register a callback for a message type"""
        if msg_type not in self._callbacks:
            self._callbacks[msg_type] = []
        self._callbacks[msg_type].append(callback)
    
    def clear(self, agent_id: Optional[str] = None) -> None:
        """Clear messages for an agent or all"""
        if agent_id:
            self._by_recipient[agent_id] = []
        else:
            self._messages.clear()
            self._by_recipient.clear()


class AgentRegistry:
    """
    Registry for managing agents in the coordinator.
    
    Provides:
    - Agent registration
    - Capability-based matching
    - Load balancing
    - Health monitoring
    """
    
    def __init__(self):
        self._agents: Dict[str, AgentInfo] = {}
    
    def register(self, agent: AgentInfo) -> None:
        """Register an agent"""
        self._agents[agent.id] = agent
        logger.info(f"Registered agent: {agent.id} ({agent.role.value})")
    
    def unregister(self, agent_id: str) -> bool:
        """Unregister an agent"""
        if agent_id in self._agents:
            del self._agents[agent_id]
            return True
        return False
    
    def get(self, agent_id: str) -> Optional[AgentInfo]:
        """Get agent by ID"""
        return self._agents.get(agent_id)
    
    def find_available(self, role: Optional[AgentRole] = None, capability: Optional[str] = None) -> List[AgentInfo]:
        """Find available agents matching criteria"""
        available = []
        for agent in self._agents.values():
            if not agent.is_available():
                continue
            if role and agent.role != role:
                continue
            if capability and capability not in agent.capabilities:
                continue
            available.append(agent)
        return available
    
    def assign_task(self, agent_id: str, task_id: str) -> bool:
        """Assign a task to an agent"""
        agent = self._agents.get(agent_id)
        if agent and agent.is_available():
            agent.status = "busy"
            agent.current_task = task_id
            return True
        return False
    
    def release_agent(self, agent_id: str) -> bool:
        """Release agent from current task"""
        agent = self._agents.get(agent_id)
        if agent:
            agent.status = "idle"
            agent.current_task = None
            return True
        return False
    
    def list_all(self) -> List[AgentInfo]:
        """List all agents"""
        return list(self._agents.values())
    
    def get_load(self) -> Dict[str, int]:
        """Get current load per agent"""
        return {
            aid: 1 if a.status == "busy" else 0
            for aid, a in self._agents.items()
        }


class Coordinator:
    """
    Main coordinator for multi-agent task execution.
    
    Based on Claude Code's coordinator/ architecture.
    
    Responsibilities:
    1. Task queue management
    2. Agent registration and assignment
    3. Workflow orchestration
    4. Message passing
    5. Result aggregation
    
    Supports both synchronous and asynchronous execution:
    - run_workflow(): Sync wrapper for backward compatibility
    - run_workflow_async(): Native async, event-driven (preferred)
    
    Usage:
        coordinator = Coordinator()
        
        # Register agents
        coordinator.register_agent(AgentInfo(
            id="agent_a",
            name="Environment Generator",
            role=AgentRole.PRODUCER,
            capabilities=["generate", "analyze"],
        ))
        
        coordinator.register_agent(AgentInfo(
            id="agent_b", 
            name="Experiment Runner",
            role=AgentRole.EXECUTOR,
            capabilities=["execute", "train"],
        ))
        
        # Create and run workflow
        workflow = coordinator.create_workflow(
            name="dual_agent_training",
            description="Train with dual agent system",
        )
        
        # Add tasks
        workflow.add_task(Task(
            id="task_env",
            type="environment",
            payload={"stage": "beginner"},
        ), stage="produce")
        
        workflow.add_task(Task(
            id="task_exp", 
            type="experiment",
            payload={"env_id": "task_env"},
            dependencies=["task_env"],
        ), stage="execute")
        
        # Execute (async preferred)
        result = await coordinator.run_workflow_async(workflow)
    """
    
    def __init__(self):
        self._registry = AgentRegistry()
        self._queue = MessageQueue()
        self._workflows: Dict[str, Workflow] = {}
        
        # Task handlers registered by type
        self._handlers: Dict[str, Callable[[Task], Dict[str, Any]]] = {}
        
        # Role runtimes for direct execution
        self._roles: Dict[str, Any] = {}  # agent_id → RoleRuntime
        
        # Callbacks
        self._on_task_complete: Optional[Callable[[Task], None]] = None
        self._on_workflow_complete: Optional[Callable[[Workflow], None]] = None
        
        # Async coordination (lazily created to avoid Python 3.7 event-loop issues)
        self._condition: Optional[asyncio.Condition] = None
        self._running_async: Set[str] = set()  # task_ids currently executing in async mode
        
        # Event bus for SSE / external subscribers
        self.event_bus: CoordinatorEventBus = CoordinatorEventBus()
    
    @property
    def condition(self) -> asyncio.Condition:
        """Lazily create asyncio.Condition in the current event loop."""
        if self._condition is None:
            self._condition = asyncio.Condition()
        return self._condition
    
    @property
    def agents(self) -> AgentRegistry:
        return self._registry
    
    @property
    def message_queue(self) -> MessageQueue:
        return self._queue
    
    def register_agent(self, agent: AgentInfo) -> None:
        """Register an agent with the coordinator"""
        self._registry.register(agent)
    
    def register_role(self, role: Any) -> None:
        """Register a RoleRuntime as an agent.
        
        Converts the role to an AgentInfo, registers it,
        and stores the role for direct execution routing.
        """
        agent_info = role.to_agent_info()
        self._registry.register(agent_info)
        self._roles[agent_info.id] = role
        logger.info(f"Registered role: {role.name} → agent {agent_info.id}")
    
    def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent"""
        return self._registry.unregister(agent_id)
    
    def register_handler(self, task_type: str, handler: Callable[[Task], Dict[str, Any]]) -> None:
        """Register a handler for a task type"""
        self._handlers[task_type] = handler
        logger.info(f"Registered handler for task type: {task_type}")
    
    def set_callbacks(
        self,
        on_task_complete: Optional[Callable[[Task], None]] = None,
        on_workflow_complete: Optional[Callable[[Workflow], None]] = None,
    ) -> None:
        """Set event callbacks"""
        self._on_task_complete = on_task_complete
        self._on_workflow_complete = on_workflow_complete
    
    def create_workflow(self, name: str, description: str = "") -> Workflow:
        """Create a new workflow"""
        workflow = Workflow(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
        )
        self._workflows[workflow.id] = workflow
        logger.info(f"Created workflow: {workflow.name} ({workflow.id})")
        return workflow
    
    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """Get a workflow by ID (public accessor)."""
        return self._workflows.get(workflow_id)
    
    def add_task(self, workflow: Workflow, task: Task, stage: str) -> None:
        """Add a task to a workflow"""
        workflow.add_task(task, stage)
        
        # Try to assign immediately if agent available
        self._try_assign_task(workflow, task)
    
    def _try_assign_task(self, workflow: Workflow, task: Task) -> bool:
        """Try to assign a task to an available agent"""
        if task.status != TaskStatus.PENDING:
            return False
        
        # Determine required role based on task type
        role_map = {
            "environment": AgentRole.PRODUCER,
            "experiment": AgentRole.EXECUTOR,
            "review": AgentRole.PRODUCER,   # Agent A reviews (same as producer)
            "training": AgentRole.EXECUTOR,
        }
        
        required_role = role_map.get(task.type)
        
        # Find available agent
        available = self._registry.find_available(role=required_role)
        if not available:
            return False
        
        # Assign to first available
        agent = available[0]
        self._registry.assign_task(agent.id, task.id)
        
        task.status = TaskStatus.RUNNING
        task.assigned_agent = agent.id
        task.started_at = datetime.now()
        
        # Emit event
        self.event_bus.emit_sync("task_assigned", {
            "task_id": task.id, "agent_id": agent.id,
            "role": agent.role.value, "task_type": task.type,
        })
        
        # Send task message
        self._queue.send(Message(
            id=str(uuid.uuid4()),
            from_agent="coordinator",
            to_agent=agent.id,
            type="task",
            payload={
                "task_id": task.id,
                "task_type": task.type,
                "task_payload": task.payload,
            },
        ))
        
        logger.info(f"Assigned task {task.id} to agent {agent.id}")
        return True
    
    def _execute_task(self, task: Task) -> Dict[str, Any]:
        """Execute a task using registered handler (synchronous)"""
        handler = self._handlers.get(task.type)
        
        if not handler:
            raise ValueError(f"No handler registered for task type: {task.type}")
        
        return handler(task)
    
    async def _execute_task_async(self, task: Task) -> Dict[str, Any]:
        """Execute a task using registered handler (async-aware)
        
        Priority:
        1. If the assigned agent has a RoleRuntime, call role.work()
        2. If a handler is registered for the task type, use it
        3. Raise ValueError
        
        If the handler is a coroutine function, await it directly.
        If it's a regular function, run it in the default executor to avoid
        blocking the event loop.
        """
        # Priority 1: Role-based execution
        if task.assigned_agent and task.assigned_agent in self._roles:
            role = self._roles[task.assigned_agent]
            from roles.role_runtime import RoleTask, RolePhase
            role_task = RoleTask(
                id=task.id,
                description=task.payload.get("description", ""),
                phase_hint=task.type,
            )
            report = await role.work(role_task)
            return {
                "status": "ok",
                "role": role.name,
                "output": report.output,
                "metrics": report.metrics,
            }
        
        # Priority 2: Handler-based execution
        handler = self._handlers.get(task.type)
        
        if not handler:
            raise ValueError(f"No handler registered for task type: {task.type}")
        
        if asyncio.iscoroutinefunction(handler):
            return await handler(task)
        else:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, handler, task)
    
    def complete_task(self, task_id: str, result: Optional[Dict[str, Any]] = None, error: Optional[str] = None) -> None:
        """Mark a task as completed"""
        # Find task in workflows
        task = None
        workflow = None
        for wf in self._workflows.values():
            if task_id in wf.tasks:
                task = wf.tasks[task_id]
                workflow = wf
                break
        
        if not task:
            logger.warning(f"Task {task_id} not found in any workflow")
            return
        
        # Update task
        task.completed_at = datetime.now()
        
        if error:
            task.status = TaskStatus.FAILED
            task.error = error
        else:
            task.status = TaskStatus.COMPLETED
            task.result = result or {}
        
        # Release agent
        if task.assigned_agent:
            old_agent_id = task.assigned_agent
            self._registry.release_agent(task.assigned_agent)
            # Emit agent status changed
            self.event_bus.emit_sync("agent_status_changed", {
                "agent_id": old_agent_id, "old_status": "busy", "new_status": "idle",
            })
        
        # Emit task completion event
        event_type = "task_completed" if not error else "task_failed"
        self.event_bus.emit_sync(event_type, {
            "task_id": task.id,
            "agent_id": task.assigned_agent,
            "result": result if not error else None,
            "error": error,
        })
        
        # Notify
        if self._on_task_complete:
            self._on_task_complete(task)
        
        # Try to assign more tasks
        if workflow:
            completed = {t.id for t in workflow.tasks.values() if t.status == TaskStatus.COMPLETED}
            ready = workflow.get_ready_tasks(completed)
            for ready_task in ready:
                self._try_assign_task(workflow, ready_task)
            
            # Check workflow completion
            if workflow.is_complete():
                workflow.completed_at = datetime.now()
                self.event_bus.emit_sync("workflow_completed", {
                    "workflow_id": workflow.id,
                    "name": workflow.name,
                    "status": "completed",
                })
                if self._on_workflow_complete:
                    self._on_workflow_complete(workflow)
        
        # Notify any async waiters
        self._notify_condition()
    
    def _notify_condition(self):
        """Notify all coroutines waiting on the asyncio.Condition.
        
        Safe to call from both sync and async contexts.
        If no event loop is running, this is a no-op.
        """
        async def _do_notify():
            async with self.condition:
                self.condition.notify_all()
        
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_do_notify())
        except RuntimeError:
            # No running event loop — nothing to notify
            pass
    
    async def run_workflow_async(self, workflow: Workflow, timeout: float = 3600.0) -> Dict[str, Any]:
        """
        Execute a workflow to completion (asynchronous, event-driven).
        
        Tasks are executed in dependency order. Uses asyncio.Condition
        instead of time.sleep polling — waits efficiently for task completion.
        
        Args:
            workflow: The workflow to execute
            timeout: Maximum execution time in seconds
        
        Returns:
            Aggregated results dict
        """
        import time
        workflow.started_at = datetime.now()
        start = time.time()
        completed = set()
        
        # Emit workflow started event
        await self.event_bus.emit("workflow_started", {
            "workflow_id": workflow.id, "name": workflow.name,
            "task_count": len(workflow.tasks),
        })
        
        while True:
            # --- Check termination ---
            if len(completed) >= len(workflow.tasks):
                break
            
            remaining_timeout = timeout - (time.time() - start)
            if remaining_timeout <= 0:
                logger.warning(f"Workflow {workflow.id} timed out after {timeout}s")
                break
            
            # --- Find ready tasks ---
            ready_pending = workflow.get_ready_tasks(completed)
            
            running_unexecuted = [
                t for t in workflow.tasks.values()
                if t.status == TaskStatus.RUNNING and t.id not in completed
            ]
            
            tasks_to_execute = ready_pending + [
                t for t in running_unexecuted if t not in ready_pending
            ]
            
            if not tasks_to_execute:
                # Check for deadlock (all remaining tasks are blocked)
                remaining = [t for t in workflow.tasks.values() if t.id not in completed]
                if not remaining:
                    break
                
                # Wait for a task to complete instead of polling
                try:
                    async with self.condition:
                        await asyncio.wait_for(
                            self.condition.wait(),
                            timeout=min(remaining_timeout, 1.0),
                        )
                except asyncio.TimeoutError:
                    # No notification received within the wait window;
                    # loop back to re-check ready tasks and timeout.
                    pass
                continue
            
            # --- Execute ready tasks (potentially in parallel) ---
            coros = []
            for task in tasks_to_execute:
                # Assign if still PENDING
                if task.status == TaskStatus.PENDING:
                    assigned = self._try_assign_task(workflow, task)
                    if not assigned:
                        continue
                
                if task.status == TaskStatus.RUNNING:
                    coros.append(self._run_task_async(task))
            
            if coros:
                # Run tasks concurrently
                await asyncio.gather(*coros)
                
                # Update completed set
                for t in workflow.tasks.values():
                    if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED) and t.id not in completed:
                        completed.add(t.id)
        
        return self._aggregate_results(workflow)
    
    async def _run_task_async(self, task: Task) -> None:
        """Execute a single task asynchronously and mark it complete."""
        try:
            result = await self._execute_task_async(task)
            self.complete_task(task.id, result=result)
        except Exception as e:
            self.complete_task(task.id, error=str(e))
    
    def run_workflow(self, workflow: Workflow, timeout: float = 3600.0) -> Dict[str, Any]:
        """
        Execute a workflow to completion (synchronous wrapper).
        
        Delegates to run_workflow_async(). If an event loop is already
        running, runs in a separate thread; otherwise uses asyncio.run().
        
        Tasks are executed in dependency order. This is a blocking call.
        """
        try:
            asyncio.get_running_loop()
            # Already in an async context — run in a separate thread
            # to avoid blocking the existing loop
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    self.run_workflow_async(workflow, timeout),
                )
                return future.result(timeout=timeout + 10)
        except RuntimeError:
            # No running loop — safe to use asyncio.run()
            return asyncio.run(self.run_workflow_async(workflow, timeout))
    
    def _aggregate_results(self, workflow: Workflow) -> Dict[str, Any]:
        """Aggregate results from all tasks in a workflow"""
        results = {
            "workflow_id": workflow.id,
            "workflow_name": workflow.name,
            "status": "completed" if workflow.is_complete() else "timeout",
            "stages": {},
            "tasks": {},
            "statistics": {
                "total": len(workflow.tasks),
                "completed": sum(1 for t in workflow.tasks.values() if t.status == TaskStatus.COMPLETED),
                "failed": sum(1 for t in workflow.tasks.values() if t.status == TaskStatus.FAILED),
                "total_duration": sum(t.duration() or 0 for t in workflow.tasks.values()),
            },
        }
        
        # Group by stage
        for stage, task_ids in workflow.stage_tasks.items():
            stage_results = []
            for tid in task_ids:
                task = workflow.tasks.get(tid)
                if task:
                    stage_results.append({
                        "id": task.id,
                        "type": task.type,
                        "status": task.status.value,
                        "result": task.result,
                        "error": task.error,
                        "duration": task.duration(),
                    })
            results["stages"][stage] = stage_results
        
        # Individual task results
        for task_id, task in workflow.tasks.items():
            results["tasks"][task_id] = {
                "type": task.type,
                "status": task.status.value,
                "result": task.result,
                "error": task.error,
                "duration": task.duration(),
                "assigned_agent": task.assigned_agent,
            }
        
        return results
    
    def get_status(self) -> Dict[str, Any]:
        """Get coordinator status"""
        return {
            "agents": {
                aid: {
                    "name": a.name,
                    "role": a.role.value,
                    "status": a.status,
                    "current_task": a.current_task,
                }
                for aid, a in self._registry._agents.items()
            },
            "workflows": {
                wid: {
                    "name": wf.name,
                    "status": "complete" if wf.is_complete() else "running",
                    "tasks": len(wf.tasks),
                }
                for wid, wf in self._workflows.items()
            },
            "queues": {
                "messages": len(self._queue._messages),
            },
        }
