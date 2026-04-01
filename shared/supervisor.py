"""Multi-Agent 协作系统 - Supervisor 模式

来自 Flowise 的灵感：
- Supervisor (协调者) 负责任务分发和结果整合
- Worker (执行者) 专注单一职责
- 层级清晰，易于扩展

架构：
    Supervisor (Coordinator)
        ├── Analyst Worker (分析)
        ├── Generator Worker (生成)
        ├── Executor Worker (执行)
        └── Reflector Worker (反思)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from enum import Enum
import json
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class WorkerRole(Enum):
    """Worker 角色类型"""
    ANALYST = "analyst"       # 分析者
    GENERATOR = "generator"   # 生成者
    EXECUTOR = "executor"     # 执行者
    REFLECTOR = "reflector"   # 反思者


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class Task:
    """任务定义"""
    id: str
    name: str
    description: str
    role: WorkerRole
    input_data: Dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    output_data: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    created_at: datetime = None
    started_at: datetime = None
    completed_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'role': self.role.value,
            'input_data': self.input_data,
            'status': self.status.value,
            'output_data': self.output_data,
            'error': self.error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass
class Worker:
    """
    Worker 基类
    
    负责执行特定类型的任务
    """
    id: str
    role: WorkerRole
    name: str = ""
    description: str = ""
    capacity: int = 5                        # 并发容量
    current_tasks: List[Task] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.name:
            self.name = f"{self.role.value}_worker"
    
    def can_accept_task(self) -> bool:
        """是否可以接受新任务"""
        return len(self.current_tasks) < self.capacity
    
    def assign_task(self, task: Task) -> bool:
        """分配任务"""
        if not self.can_accept_task():
            return False
        
        self.current_tasks.append(task)
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        return True
    
    def execute(self, task: Task) -> Dict[str, Any]:
        """
        执行任务（子类实现）
        
        Returns:
            Dict[str, Any]: 执行结果
        """
        raise NotImplementedError("子类必须实现 execute 方法")
    
    def complete_task(self, task: Task, result: Dict[str, Any]):
        """完成任务"""
        task.output_data = result
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now()
        
        if task in self.current_tasks:
            self.current_tasks.remove(task)
    
    def fail_task(self, task: Task, error: str):
        """任务失败"""
        task.error = error
        task.status = TaskStatus.FAILED
        task.completed_at = datetime.now()
        
        if task in self.current_tasks:
            self.current_tasks.remove(task)


class AnalystWorker(Worker):
    """
    分析者 Worker
    
    负责分析训练进度、识别模式
    """
    
    def __init__(self, agent_a=None):
        super().__init__(
            id="analyst_1",
            role=WorkerRole.ANALYST,
            name="Analyst Worker",
            description="分析训练进度和识别模式",
        )
        self.agent_a = agent_a
    
    def execute(self, task: Task) -> Dict[str, Any]:
        """执行分析任务"""
        input_data = task.input_data
        
        # 分析进度
        results_tsv = input_data.get('results_tsv', '')
        
        if self.agent_a:
            try:
                progress = self.agent_a.analyze_progress(results_tsv)
                return {
                    'progress': {
                        'total_experiments': progress.total_experiments,
                        'keep_rate': progress.keep_rate,
                        'best_score': progress.best_score,
                        'weak_areas': progress.weak_areas,
                    }
                }
            except Exception as e:
                return {'error': str(e)}
        
        # 简化分析
        return {
            'progress': {
                'total_experiments': input_data.get('total_experiments', 0),
                'keep_rate': input_data.get('keep_rate', 0.0),
            }
        }


class GeneratorWorker(Worker):
    """
    生成者 Worker
    
    负责生成训练环境、任务
    """
    
    def __init__(self, agent_a=None):
        super().__init__(
            id="generator_1",
            role=WorkerRole.GENERATOR,
            name="Generator Worker",
            description="生成训练环境和任务",
        )
        self.agent_a = agent_a
    
    def execute(self, task: Task) -> Dict[str, Any]:
        """执行生成任务"""
        input_data = task.input_data
        
        progress_data = input_data.get('progress', {})
        
        if self.agent_a:
            try:
                # 导入 AgentBProgress
                from agent_a.generator import AgentBProgress
                progress = AgentBProgress(**progress_data)
                env = self.agent_a.generate_environment(progress)
                
                return {
                    'environment': {
                        'id': env.id,
                        'name': env.name,
                        'difficulty': env.difficulty,
                        'tasks': env.tasks[:5] if len(env.tasks) > 5 else env.tasks,
                    }
                }
            except Exception as e:
                return {'error': str(e)}
        
        # 简化生成
        return {
            'environment': {
                'id': 'env_default',
                'name': 'Default Environment',
                'difficulty': progress_data.get('difficulty', 0.5),
            }
        }


class ExecutorWorker(Worker):
    """
    执行者 Worker
    
    负责执行实验
    """
    
    def __init__(self, agent_b=None):
        super().__init__(
            id="executor_1",
            role=WorkerRole.EXECUTOR,
            name="Executor Worker",
            description="执行实验和收集结果",
            capacity=3,  # 执行者容量较低
        )
        self.agent_b = agent_b
    
    def execute(self, task: Task) -> Dict[str, Any]:
        """执行实验任务"""
        input_data = task.input_data
        
        experiment_idea = input_data.get('experiment_idea', {})
        env = input_data.get('environment', {})
        
        if self.agent_b:
            try:
                from agent_b.learner import ExperimentIdea
                idea = ExperimentIdea(**experiment_idea)
                result = self.agent_b.run_experiment(idea, env)
                
                return {
                    'result': {
                        'commit': result.commit,
                        'status': result.status,
                        'reward': result.reward,
                    }
                }
            except Exception as e:
                return {'error': str(e)}
        
        # 简化执行
        return {
            'result': {
                'status': 'completed',
                'reward': 0.5,
            }
        }


class ReflectorWorker(Worker):
    """
    反思者 Worker
    
    负责反思实验结果
    """
    
    def __init__(self, reflector=None):
        super().__init__(
            id="reflector_1",
            role=WorkerRole.REFLECTOR,
            name="Reflector Worker",
            description="反思实验结果并提出改进建议",
        )
        self.reflector = reflector
    
    def execute(self, task: Task) -> Dict[str, Any]:
        """执行反思任务"""
        input_data = task.input_data
        
        trajectories = input_data.get('trajectories', [])
        metrics = input_data.get('metrics', {})
        stage = input_data.get('stage', 'intermediate')
        
        if self.reflector:
            try:
                reflection = self.reflector.reflect(trajectories, metrics, stage)
                
                return {
                    'reflection': {
                        'timestamp': reflection.timestamp,
                        'stage': reflection.stage,
                        'recommendations': reflection.recommendations[:3] if reflection.recommendations else [],
                    }
                }
            except Exception as e:
                return {'error': str(e)}
        
        # 简化反思
        return {
            'reflection': {
                'summary': f"分析了 {len(trajectories)} 条轨迹",
                'recommendations': ["继续当前策略"],
            }
        }


class Supervisor:
    """
    Supervisor (协调者)
    
    来自 Flowise 的灵感：
    - 负责任务分发
    - 协调多个 Worker
    - 整合执行结果
    - 管理工作流状态
    
    工作流程：
    1. 接收任务请求
    2. 分解为子任务
    3. 分配给合适的 Worker
    4. 监控执行状态
    5. 整合结果并返回
    """
    
    def __init__(
        self,
        agent_a=None,
        agent_b=None,
        reflector=None,
        max_concurrent_tasks: int = 10,
    ):
        """
        初始化 Supervisor
        
        Args:
            agent_a: Agent A 实例（可选）
            agent_b: Agent B 实例（可选）
            reflector: Reflector 实例（可选）
            max_concurrent_tasks: 最大并发任务数
        """
        self.agent_a = agent_a
        self.agent_b = agent_b
        self.reflector = reflector
        self.max_concurrent_tasks = max_concurrent_tasks
        
        # 初始化 Workers
        self.workers: Dict[WorkerRole, List[Worker]] = {
            WorkerRole.ANALYST: [AnalystWorker(agent_a)],
            WorkerRole.GENERATOR: [GeneratorWorker(agent_a)],
            WorkerRole.EXECUTOR: [ExecutorWorker(agent_b)],
            WorkerRole.REFLECTOR: [ReflectorWorker(reflector)],
        }
        
        # 任务队列
        self.pending_tasks: List[Task] = []
        self.running_tasks: List[Task] = []
        self.completed_tasks: List[Task] = []
        
        # 统计
        self.stats = {
            'total_tasks': 0,
            'completed': 0,
            'failed': 0,
            'by_role': {role.value: 0 for role in WorkerRole},
        }
    
    def create_task(
        self,
        name: str,
        description: str,
        role: WorkerRole,
        input_data: Dict[str, Any],
    ) -> Task:
        """创建任务"""
        task = Task(
            id=f"task_{self.stats['total_tasks'] + 1}",
            name=name,
            description=description,
            role=role,
            input_data=input_data,
        )
        
        self.stats['total_tasks'] += 1
        return task
    
    def assign_task(self, task: Task) -> bool:
        """
        分配任务给合适的 Worker
        
        Returns:
            bool: 是否成功分配
        """
        role = task.role
        workers = self.workers.get(role, [])
        
        # 找到可用的 Worker
        for worker in workers:
            if worker.can_accept_task():
                worker.assign_task(task)
                self.running_tasks.append(task)
                return True
        
        # 没有可用的 Worker，加入待处理队列
        self.pending_tasks.append(task)
        return False
    
    def execute_task(self, task: Task) -> Dict[str, Any]:
        """
        执行单个任务
        
        Returns:
            Dict[str, Any]: 执行结果
        """
        role = task.role
        workers = self.workers.get(role, [])
        
        for worker in workers:
            if task in worker.current_tasks:
                try:
                    result = worker.execute(task)
                    worker.complete_task(task, result)
                    
                    # 更新统计
                    self.stats['completed'] += 1
                    self.stats['by_role'][role.value] += 1
                    
                    # 移动到已完成队列
                    if task in self.running_tasks:
                        self.running_tasks.remove(task)
                    self.completed_tasks.append(task)
                    
                    return result
                    
                except Exception as e:
                    worker.fail_task(task, str(e))
                    self.stats['failed'] += 1
                    
                    if task in self.running_tasks:
                        self.running_tasks.remove(task)
                    self.completed_tasks.append(task)
                    
                    return {'error': str(e)}
        
        return {'error': 'Task not found in any worker'}
    
    def run_workflow(
        self,
        results_tsv: str = "",
        trajectories: List[Dict] = None,
        metrics: Dict[str, float] = None,
    ) -> Dict[str, Any]:
        """
        运行完整工作流
        
        流程：
        1. 分析进度 (Analyst)
        2. 生成环境 (Generator)
        3. 执行实验 (Executor)
        4. 反思结果 (Reflector)
        
        Returns:
            Dict[str, Any]: 工作流结果
        """
        workflow_result = {
            'started_at': datetime.now().isoformat(),
            'steps': {},
        }
        
        trajectories = trajectories or []
        metrics = metrics or {}
        
        # Step 1: 分析进度
        analyst_task = self.create_task(
            name="Analyze Progress",
            description="分析训练进度",
            role=WorkerRole.ANALYST,
            input_data={'results_tsv': results_tsv},
        )
        self.assign_task(analyst_task)
        analyst_result = self.execute_task(analyst_task)
        workflow_result['steps']['analyst'] = analyst_result
        
        # Step 2: 生成环境
        progress_data = analyst_result.get('progress', {})
        generator_task = self.create_task(
            name="Generate Environment",
            description="生成训练环境",
            role=WorkerRole.GENERATOR,
            input_data={'progress': progress_data},
        )
        self.assign_task(generator_task)
        generator_result = self.execute_task(generator_task)
        workflow_result['steps']['generator'] = generator_result
        
        # Step 3: 执行实验（可选，有实验想法时执行）
        env_data = generator_result.get('environment', {})
        if env_data.get('tasks'):
            experiment_task = self.create_task(
                name="Execute Experiments",
                description="执行实验",
                role=WorkerRole.EXECUTOR,
                input_data={
                    'environment': env_data,
                    'experiment_idea': env_data['tasks'][0] if env_data['tasks'] else {},
                },
            )
            self.assign_task(experiment_task)
            executor_result = self.execute_task(experiment_task)
            workflow_result['steps']['executor'] = executor_result
        
        # Step 4: 反思结果
        reflector_task = self.create_task(
            name="Reflect on Results",
            description="反思实验结果",
            role=WorkerRole.REFLECTOR,
            input_data={
                'trajectories': trajectories,
                'metrics': metrics,
                'stage': progress_data.get('stage', 'intermediate'),
            },
        )
        self.assign_task(reflector_task)
        reflector_result = self.execute_task(reflector_task)
        workflow_result['steps']['reflector'] = reflector_result
        
        # 完成工作流
        workflow_result['completed_at'] = datetime.now().isoformat()
        workflow_result['stats'] = self.stats.copy()
        
        return workflow_result
    
    def get_status(self) -> Dict[str, Any]:
        """获取 Supervisor 状态"""
        return {
            'pending_tasks': len(self.pending_tasks),
            'running_tasks': len(self.running_tasks),
            'completed_tasks': len(self.completed_tasks),
            'workers': {
                role.value: len(workers)
                for role, workers in self.workers.items()
            },
            'stats': self.stats,
        }
    
    def add_worker(self, worker: Worker):
        """添加 Worker"""
        role = worker.role
        if role not in self.workers:
            self.workers[role] = []
        self.workers[role].append(worker)
    
    def process_pending_tasks(self):
        """处理待处理任务队列"""
        still_pending = []
        
        for task in self.pending_tasks:
            if not self.assign_task(task):
                still_pending.append(task)
        
        self.pending_tasks = still_pending
    
    def clear_completed(self):
        """清理已完成任务"""
        self.completed_tasks.clear()
