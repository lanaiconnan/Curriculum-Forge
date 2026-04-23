"""扩展 Task 类型系统

来自 Claude Code 灵感：
- LocalShellTask: Shell 命令任务
- LocalAgentTask: 本地 Agent 任务
- RemoteAgentTask: 远程 Agent 任务
- DreamTask: 梦幻任务（后台推理）
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from enum import Enum
import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TaskType(Enum):
    """Task 类型（Claude Code 风格）"""
    LOCAL_SHELL = "local_shell"       # Shell 命令
    LOCAL_AGENT = "local_agent"       # 本地 Agent
    REMOTE_AGENT = "remote_agent"     # 远程 Agent
    DREAM = "dream"                   # 梦幻任务（后台推理）
    WORKFLOW = "workflow"             # 工作流任务
    MONITOR = "monitor"               # 监控任务


class TaskPriority(Enum):
    """Task 优先级"""
    LOW = 1
    NORMAL = 5
    HIGH = 10
    CRITICAL = 20


class TaskState(Enum):
    """Task 状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class BaseTask:
    """
    Task 基类
    
    所有 Task 类型的基类
    """
    id: str
    name: str
    task_type: TaskType
    state: TaskState = TaskState.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    created_at: datetime = None
    started_at: datetime = None
    completed_at: datetime = None
    result: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
    
    def execute(self) -> Dict[str, Any]:
        """执行任务（子类实现）"""
        raise NotImplementedError("子类必须实现 execute 方法")
    
    def cancel(self):
        """取消任务"""
        self.state = TaskState.CANCELLED
    
    def get_duration_ms(self) -> float:
        """获取执行时长（毫秒）"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds() * 1000
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'task_type': self.task_type.value,
            'state': self.state.value,
            'priority': self.priority.value,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'duration_ms': self.get_duration_ms(),
            'result': self.result,
            'error': self.error,
        }


@dataclass
class LocalShellTask(BaseTask):
    """
    Shell 命令任务（Claude Code 风格）
    
    执行 Shell 命令并返回结果
    """
    command: str = ""
    cwd: str = ""
    timeout: int = 60                          # 超时秒数
    capture_output: bool = True
    env: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        super().__post_init__()
        self.task_type = TaskType.LOCAL_SHELL
    
    def execute(self) -> Dict[str, Any]:
        """执行 Shell 命令"""
        self.state = TaskState.RUNNING
        self.started_at = datetime.now()
        
        try:
            # 合并环境变量
            env = os.environ.copy()
            env.update(self.env)
            
            # 执行命令
            result = subprocess.run(
                self.command,
                shell=True,
                cwd=self.cwd or None,
                capture_output=self.capture_output,
                text=True,
                timeout=self.timeout,
                env=env,
            )
            
            self.completed_at = datetime.now()
            
            if result.returncode == 0:
                self.state = TaskState.COMPLETED
                self.result = {
                    'stdout': result.stdout,
                    'stderr': result.stderr,
                    'returncode': result.returncode,
                }
            else:
                self.state = TaskState.FAILED
                self.error = result.stderr or f"Exit code: {result.returncode}"
                self.result = {
                    'stdout': result.stdout,
                    'stderr': result.stderr,
                    'returncode': result.returncode,
                }
        
        except subprocess.TimeoutExpired:
            self.state = TaskState.TIMEOUT
            self.completed_at = datetime.now()
            self.error = f"Timeout after {self.timeout}s"
        
        except Exception as e:
            self.state = TaskState.FAILED
            self.completed_at = datetime.now()
            self.error = str(e)
        
        return self.result


@dataclass
class LocalAgentTask(BaseTask):
    """
    本地 Agent 任务（Claude Code 风格）
    
    在本地运行 Agent
    """
    agent_id: str = ""
    input_data: Dict[str, Any] = field(default_factory=dict)
    max_iterations: int = 10
    agent_callable: Callable = None
    
    def __post_init__(self):
        super().__post_init__()
        self.task_type = TaskType.LOCAL_AGENT
    
    def execute(self) -> Dict[str, Any]:
        """执行 Agent 任务"""
        self.state = TaskState.RUNNING
        self.started_at = datetime.now()
        
        try:
            if self.agent_callable:
                # 调用 Agent
                result = self.agent_callable(self.input_data)
                
                self.state = TaskState.COMPLETED
                self.completed_at = datetime.now()
                self.result = result if isinstance(result, dict) else {'output': result}
            else:
                # 没有 Agent，返回模拟结果
                self.state = TaskState.COMPLETED
                self.completed_at = datetime.now()
                self.result = {'output': f"Agent {self.agent_id} executed"}
        
        except Exception as e:
            self.state = TaskState.FAILED
            self.completed_at = datetime.now()
            self.error = str(e)
        
        return self.result


@dataclass
class RemoteAgentTask(BaseTask):
    """
    远程 Agent 任务（Claude Code 风格）
    
    在远程服务器运行 Agent
    """
    remote_url: str = ""
    agent_id: str = ""
    input_data: Dict[str, Any] = field(default_factory=dict)
    auth_token: str = ""
    timeout: int = 300
    
    def __post_init__(self):
        super().__post_init__()
        self.task_type = TaskType.REMOTE_AGENT
    
    def execute(self) -> Dict[str, Any]:
        """执行远程 Agent 任务（简化版）"""
        self.state = TaskState.RUNNING
        self.started_at = datetime.now()
        
        # 简化实现：返回模拟结果
        # 实际实现需要 HTTP 请求
        self.state = TaskState.COMPLETED
        self.completed_at = datetime.now()
        self.result = {
            'remote_url': self.remote_url,
            'agent_id': self.agent_id,
            'output': 'Remote agent executed (simulated)',
        }
        
        return self.result


@dataclass
class DreamTask(BaseTask):
    """
    梦幻任务（Claude Code 风格）
    
    后台推理任务，不阻塞主流程
    """
    prompt: str = ""
    max_iterations: int = 5
    is_backgrounded: bool = True
    
    def __post_init__(self):
        super().__post_init__()
        self.task_type = TaskType.DREAM
    
    def execute(self) -> Dict[str, Any]:
        """执行梦幻任务"""
        self.state = TaskState.RUNNING
        self.started_at = datetime.now()
        
        # 简化实现：返回模拟结果
        # 实际实现需要调用 LLM 进行推理
        self.state = TaskState.COMPLETED
        self.completed_at = datetime.now()
        self.result = {
            'prompt': self.prompt,
            'thoughts': ['Thinking...', 'Reasoning...', 'Concluding...'],
            'output': 'Dream task completed',
        }
        
        return self.result


class TaskFactory:
    """
    Task 工厂
    
    创建各种类型的 Task
    """
    
    @staticmethod
    def create_shell_task(
        command: str,
        name: str = None,
        cwd: str = "",
        timeout: int = 60,
    ) -> LocalShellTask:
        """创建 Shell 任务"""
        task_id = f"shell_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        return LocalShellTask(
            id=task_id,
            name=name or f"Shell: {command[:30]}",
            task_type=TaskType.LOCAL_SHELL,
            command=command,
            cwd=cwd,
            timeout=timeout,
        )
    
    @staticmethod
    def create_agent_task(
        agent_id: str,
        input_data: Dict[str, Any],
        name: str = None,
        agent_callable: Callable = None,
    ) -> LocalAgentTask:
        """创建 Agent 任务"""
        task_id = f"agent_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        return LocalAgentTask(
            id=task_id,
            name=name or f"Agent: {agent_id}",
            task_type=TaskType.LOCAL_AGENT,
            agent_id=agent_id,
            input_data=input_data,
            agent_callable=agent_callable,
        )
    
    @staticmethod
    def create_remote_task(
        remote_url: str,
        agent_id: str,
        input_data: Dict[str, Any],
        name: str = None,
    ) -> RemoteAgentTask:
        """创建远程任务"""
        task_id = f"remote_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        return RemoteAgentTask(
            id=task_id,
            name=name or f"Remote: {agent_id}",
            task_type=TaskType.REMOTE_AGENT,
            remote_url=remote_url,
            agent_id=agent_id,
            input_data=input_data,
        )
    
    @staticmethod
    def create_dream_task(
        prompt: str,
        name: str = None,
    ) -> DreamTask:
        """创建梦幻任务"""
        task_id = f"dream_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        return DreamTask(
            id=task_id,
            name=name or "Dream Task",
            task_type=TaskType.DREAM,
            prompt=prompt,
        )


class TaskRunner:
    """
    Task 执行器
    
    管理和执行多个 Task
    """
    
    def __init__(self, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent
        self.tasks: Dict[str, BaseTask] = {}
        self.results: Dict[str, Dict[str, Any]] = {}
    
    def submit(self, task: BaseTask) -> str:
        """提交任务"""
        self.tasks[task.id] = task
        return task.id
    
    def run(self, task_id: str) -> Dict[str, Any]:
        """运行单个任务"""
        task = self.tasks.get(task_id)
        if not task:
            return {'error': f'Task not found: {task_id}'}
        
        result = task.execute()
        self.results[task_id] = result
        return result
    
    def run_all(self) -> Dict[str, Dict[str, Any]]:
        """运行所有待处理任务"""
        results = {}
        for task_id, task in self.tasks.items():
            if task.state == TaskState.PENDING:
                results[task_id] = self.run(task_id)
        return results
    
    def get_task(self, task_id: str) -> Optional[BaseTask]:
        """获取任务"""
        return self.tasks.get(task_id)
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        by_state = {}
        for state in TaskState:
            by_state[state.value] = 0
        
        for task in self.tasks.values():
            by_state[task.state.value] += 1
        
        return {
            'total': len(self.tasks),
            'by_state': by_state,
        }
