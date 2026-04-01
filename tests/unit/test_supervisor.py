"""测试 Supervisor 多 Agent 协作

测试内容：
1. Worker 基础功能
2. AnalystWorker / GeneratorWorker / ExecutorWorker / ReflectorWorker
3. Supervisor 任务分发
4. 完整工作流
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.supervisor import (
    Supervisor,
    Worker,
    AnalystWorker,
    GeneratorWorker,
    ExecutorWorker,
    ReflectorWorker,
    Task,
    WorkerRole,
    TaskStatus,
)


class TestTask:
    """Task 测试"""
    
    def test_creation(self):
        task = Task(
            id="t1", name="Test", description="desc",
            role=WorkerRole.ANALYST, input_data={"key": "val"},
        )
        assert task.id == "t1"
        assert task.status == TaskStatus.PENDING
        assert task.created_at is not None
    
    def test_to_dict(self):
        task = Task(
            id="t1", name="Test", description="desc",
            role=WorkerRole.ANALYST, input_data={},
        )
        d = task.to_dict()
        assert d['role'] == 'analyst'
        assert d['status'] == 'pending'


class TestWorker:
    """Worker 基础测试"""
    
    @pytest.fixture
    def worker(self):
        return Worker(id="w1", role=WorkerRole.ANALYST, capacity=2)
    
    def test_can_accept_task(self, worker):
        assert worker.can_accept_task() is True
    
    def test_assign_task(self, worker):
        task = Task(id="t1", name="T", description="d", role=WorkerRole.ANALYST, input_data={})
        success = worker.assign_task(task)
        assert success is True
        assert task.status == TaskStatus.RUNNING
        assert len(worker.current_tasks) == 1
    
    def test_assign_task_full(self, worker):
        t1 = Task(id="t1", name="T1", description="d", role=WorkerRole.ANALYST, input_data={})
        t2 = Task(id="t2", name="T2", description="d", role=WorkerRole.ANALYST, input_data={})
        worker.assign_task(t1)
        worker.assign_task(t2)
        
        t3 = Task(id="t3", name="T3", description="d", role=WorkerRole.ANALYST, input_data={})
        assert worker.assign_task(t3) is False
    
    def test_complete_task(self, worker):
        task = Task(id="t1", name="T", description="d", role=WorkerRole.ANALYST, input_data={})
        worker.assign_task(task)
        
        result = {"score": 0.8}
        worker.complete_task(task, result)
        
        assert task.status == TaskStatus.COMPLETED
        assert task.output_data == result
        assert len(worker.current_tasks) == 0
    
    def test_fail_task(self, worker):
        task = Task(id="t1", name="T", description="d", role=WorkerRole.ANALYST, input_data={})
        worker.assign_task(task)
        
        worker.fail_task(task, "Timeout")
        assert task.status == TaskStatus.FAILED
        assert task.error == "Timeout"


class TestAnalystWorker:
    """AnalystWorker 测试"""
    
    def test_execute_standalone(self):
        worker = AnalystWorker()
        task = Task(
            id="t1", name="Analyze", description="d",
            role=WorkerRole.ANALYST,
            input_data={'results_tsv': '', 'total_experiments': 10, 'keep_rate': 0.6},
        )
        worker.assign_task(task)
        result = worker.execute(task)
        
        assert 'progress' in result
        assert result['progress']['total_experiments'] == 10


class TestGeneratorWorker:
    """GeneratorWorker 测试"""
    
    def test_execute_standalone(self):
        worker = GeneratorWorker()
        task = Task(
            id="t1", name="Generate", description="d",
            role=WorkerRole.GENERATOR,
            input_data={'progress': {'difficulty': 0.5}},
        )
        worker.assign_task(task)
        result = worker.execute(task)
        
        assert 'environment' in result
        assert 'difficulty' in result['environment']


class TestExecutorWorker:
    """ExecutorWorker 测试"""
    
    def test_execute_standalone(self):
        worker = ExecutorWorker()
        task = Task(
            id="t1", name="Execute", description="d",
            role=WorkerRole.EXECUTOR,
            input_data={'experiment_idea': {}, 'environment': {}},
        )
        worker.assign_task(task)
        result = worker.execute(task)
        
        assert 'result' in result
        assert result['result']['status'] == 'completed'


class TestReflectorWorker:
    """ReflectorWorker 测试"""
    
    def test_execute_standalone(self):
        worker = ReflectorWorker()
        task = Task(
            id="t1", name="Reflect", description="d",
            role=WorkerRole.REFLECTOR,
            input_data={
                'trajectories': [{'id': 't1', 'status': 'keep', 'reward': 0.8}],
                'metrics': {'reward': 1.0},
                'stage': 'intermediate',
            },
        )
        worker.assign_task(task)
        result = worker.execute(task)
        
        assert 'reflection' in result


class TestSupervisor:
    """Supervisor 核心测试"""
    
    @pytest.fixture
    def supervisor(self):
        return Supervisor()
    
    def test_initialization(self, supervisor):
        status = supervisor.get_status()
        assert status['pending_tasks'] == 0
        assert status['running_tasks'] == 0
        assert status['workers']['analyst'] == 1
        assert status['workers']['executor'] == 1
    
    def test_create_task(self, supervisor):
        task = supervisor.create_task(
            name="Test", description="d",
            role=WorkerRole.ANALYST, input_data={},
        )
        assert task.id == "task_1"
        assert task.role == WorkerRole.ANALYST
    
    def test_assign_task(self, supervisor):
        task = supervisor.create_task(
            name="Test", description="d",
            role=WorkerRole.ANALYST, input_data={},
        )
        success = supervisor.assign_task(task)
        assert success is True
        assert len(supervisor.running_tasks) == 1
    
    def test_execute_task(self, supervisor):
        task = supervisor.create_task(
            name="Analyze", description="d",
            role=WorkerRole.ANALYST,
            input_data={'total_experiments': 5, 'keep_rate': 0.5},
        )
        supervisor.assign_task(task)
        result = supervisor.execute_task(task)
        
        assert 'progress' in result
        assert len(supervisor.completed_tasks) == 1
    
    def test_execute_task_error_handling(self, supervisor):
        # 无效任务也能处理
        task = supervisor.create_task(
            name="Bad", description="d",
            role=WorkerRole.EXECUTOR,
            input_data={},
        )
        supervisor.assign_task(task)
        result = supervisor.execute_task(task)
        
        assert result is not None  # 不应该崩溃
    
    def test_run_workflow(self, supervisor):
        result = supervisor.run_workflow(
            results_tsv='',
            trajectories=[{'id': 't1', 'status': 'keep', 'reward': 0.9}],
            metrics={'reward': 1.0},
        )
        
        assert 'started_at' in result
        assert 'completed_at' in result
        assert 'steps' in result
        assert 'analyst' in result['steps']
        assert 'generator' in result['steps']
        assert 'reflector' in result['steps']
    
    def test_run_workflow_empty(self, supervisor):
        result = supervisor.run_workflow()
        
        assert 'steps' in result
        assert len(result['steps']) >= 3
    
    def test_add_worker(self, supervisor):
        new_worker = AnalystWorker()
        supervisor.add_worker(new_worker)
        
        status = supervisor.get_status()
        assert status['workers']['analyst'] == 2
    
    def test_stats_after_workflow(self, supervisor):
        supervisor.run_workflow()
        
        stats = supervisor.stats
        assert stats['total_tasks'] >= 3
        assert stats['completed'] >= 3
        assert stats['failed'] == 0
    
    def test_clear_completed(self, supervisor):
        supervisor.run_workflow()
        assert len(supervisor.completed_tasks) > 0
        
        supervisor.clear_completed()
        assert len(supervisor.completed_tasks) == 0
    
    def test_pending_queue_when_full(self, supervisor):
        """Worker 满时进入待处理队列"""
        # Executor 容量为 3
        tasks = []
        for i in range(5):
            t = supervisor.create_task(
                name=f"Exec {i}", description="d",
                role=WorkerRole.EXECUTOR, input_data={},
            )
            tasks.append(t)
        
        for t in tasks:
            supervisor.assign_task(t)
        
        status = supervisor.get_status()
        # 应该有部分在 pending
        assert status['running_tasks'] + status['pending_tasks'] == 5


class TestSupervisorIntegration:
    """集成测试"""
    
    def test_supervisor_with_real_agents(self, tmp_path):
        """测试与真实 Agent 集成"""
        from agent_a.generator import AgentA
        from agent_b.reflector import Reflector
        
        agent_a = AgentA(workspace=str(tmp_path))
        reflector = Reflector()
        
        supervisor = Supervisor(agent_a=agent_a, reflector=reflector)
        result = supervisor.run_workflow(
            trajectories=[{'id': 't1', 'status': 'keep', 'reward': 0.8}],
            metrics={'reward': 0.8},
        )
        
        assert 'steps' in result
        assert result['steps']['analyst'].get('progress') is not None
        assert result['steps']['reflector'].get('reflection') is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
