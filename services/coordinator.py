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
from typing import Any, Dict, List, Optional, Callable, Type
from enum import Enum
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Task execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


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
class Workflow:
    """
    A coordinated workflow involving multiple agents.
    
    Defines the execution plan and manages task dependencies.
    """
    id: str
    name: str
    description: str
    
    stages: List[str] = field(default_factory=list)  # Stage names
    stage_tasks: Dict[str, List[str]] = field(default_factory=dict)  # stage -> task IDs
    
    tasks: Dict[str, Task] = field(default_factory=dict)
    agents: Dict[str, AgentInfo] = field(default_factory=dict)
    
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    current_stage: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_task(self, task: Task, stage: str) -> None:
        """Add a task to a specific stage"""
        self.tasks[task.id] = task
        if stage not in self.stage_tasks:
            self.stage_tasks[stage] = []
            self.stages.append(stage)
        self.stage_tasks[stage].append(task.id)
    
    def get_ready_tasks(self, completed: set) -> List[Task]:
        """Get tasks that are ready to execute"""
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
        
        # Execute
        result = coordinator.run_workflow(workflow)
    """
    
    def __init__(self):
        self._registry = AgentRegistry()
        self._queue = MessageQueue()
        self._workflows: Dict[str, Workflow] = {}
        
        # Task handlers registered by type
        self._handlers: Dict[str, Callable[[Task], Dict[str, Any]]] = {}
        
        # Callbacks
        self._on_task_complete: Optional[Callable[[Task], None]] = None
        self._on_workflow_complete: Optional[Callable[[Workflow], None]] = None
    
    @property
    def agents(self) -> AgentRegistry:
        return self._registry
    
    @property
    def message_queue(self) -> MessageQueue:
        return self._queue
    
    def register_agent(self, agent: AgentInfo) -> None:
        """Register an agent with the coordinator"""
        self._registry.register(agent)
    
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
        """Execute a task using registered handler"""
        handler = self._handlers.get(task.type)
        
        if not handler:
            raise ValueError(f"No handler registered for task type: {task.type}")
        
        return handler(task)
    
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
            self._registry.release_agent(task.assigned_agent)
        
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
                if self._on_workflow_complete:
                    self._on_workflow_complete(workflow)
    
    def run_workflow(self, workflow: Workflow, timeout: float = 3600.0) -> Dict[str, Any]:
        """
        Execute a workflow to completion (synchronous).
        
        Tasks are executed in dependency order. This is a blocking call.
        """
        workflow.started_at = datetime.now()
        
        import time
        start = time.time()
        completed = set()
        
        # Keep processing until all tasks are done or timeout
        while len(completed) < len(workflow.tasks):
            if time.time() - start > timeout:
                logger.warning(f"Workflow {workflow.id} timed out after {timeout}s")
                break
            
            # Find tasks that are PENDING and ready (deps satisfied)
            ready_pending = workflow.get_ready_tasks(completed)
            
            # Also find tasks that are RUNNING but not yet executed
            # (assigned by complete_task's internal _try_assign_task call)
            running_unexecuted = [
                t for t in workflow.tasks.values()
                if t.status == TaskStatus.RUNNING and t.id not in completed
            ]
            
            tasks_to_execute = ready_pending + [
                t for t in running_unexecuted if t not in ready_pending
            ]
            
            if not tasks_to_execute:
                # Check for deadlock
                remaining = [t for t in workflow.tasks.values() if t.id not in completed]
                if not remaining:
                    break
                time.sleep(0.01)
                continue
            
            for task in tasks_to_execute:
                # Assign if still PENDING
                if task.status == TaskStatus.PENDING:
                    assigned = self._try_assign_task(workflow, task)
                    if not assigned:
                        continue
                
                # Execute (task is now RUNNING)
                if task.status == TaskStatus.RUNNING:
                    try:
                        result = self._execute_task(task)
                        self.complete_task(task.id, result=result)
                    except Exception as e:
                        self.complete_task(task.id, error=str(e))
                    
                    if task.status == TaskStatus.COMPLETED:
                        completed.add(task.id)
        
        return self._aggregate_results(workflow)
        
        # Aggregate results
        return self._aggregate_results(workflow)
    
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
