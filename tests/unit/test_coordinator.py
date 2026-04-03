"""Unit tests for Coordinator and DualAgentCoordinator

Run: pytest tests/unit/test_coordinator.py -v
"""

import pytest
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.coordinator import (
    Coordinator,
    Task,
    TaskStatus,
    AgentRole,
    AgentInfo,
    Message,
    Workflow,
    MessageQueue,
    AgentRegistry,
)
from services.dual_agent import (
    DualAgentCoordinator,
    DualAgentConfig,
    EpisodeResult,
)
from services.environment import EnvironmentService, EnvironmentServiceConfig
from services.learner import LearnerService, LearnerServiceConfig
from services.trainer import RLTrainerService, RLConfig


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def services():
    env = EnvironmentService(EnvironmentServiceConfig(name='env'))
    env.initialize(); env.start()

    learner = LearnerService(LearnerServiceConfig(name='learner', max_iterations=1))
    learner.initialize(); learner.start()

    trainer = RLTrainerService(RLConfig(name='trainer'))
    trainer.initialize(); trainer.start()

    yield env, learner, trainer

    env.stop(); learner.stop(); trainer.stop()


@pytest.fixture
def coordinator(services):
    env, learner, trainer = services
    return DualAgentCoordinator(
        env_service=env,
        learner_service=learner,
        trainer_service=trainer,
        config=DualAgentConfig(max_iterations=1),
    )


# ─── MessageQueue ─────────────────────────────────────────────────────────────

class TestMessageQueue:
    def test_send_and_receive(self):
        mq = MessageQueue()
        msg = Message(id='m1', from_agent='a', to_agent='b', type='task', payload={'x': 1})
        mq.send(msg)
        received = mq.receive('b')
        assert len(received) == 1
        assert received[0].id == 'm1'

    def test_broadcast(self):
        mq = MessageQueue()
        mq.broadcast('a', 'status', {'state': 'ok'})
        received = mq.receive('*')
        assert len(received) == 1

    def test_filter_by_type(self):
        mq = MessageQueue()
        mq.send(Message(id='m1', from_agent='a', to_agent='b', type='task', payload={}))
        mq.send(Message(id='m2', from_agent='a', to_agent='b', type='result', payload={}))
        tasks = mq.receive('b', msg_type='task')
        assert len(tasks) == 1
        assert tasks[0].id == 'm1'

    def test_callback(self):
        mq = MessageQueue()
        received = []
        mq.register_callback('alert', lambda m: received.append(m))
        mq.send(Message(id='m1', from_agent='a', to_agent='b', type='alert', payload={}))
        assert len(received) == 1

    def test_clear(self):
        mq = MessageQueue()
        mq.send(Message(id='m1', from_agent='a', to_agent='b', type='task', payload={}))
        mq.clear('b')
        assert mq.receive('b') == []


# ─── AgentRegistry ────────────────────────────────────────────────────────────

class TestAgentRegistry:
    def test_register_and_get(self):
        reg = AgentRegistry()
        agent = AgentInfo(id='a1', name='Agent A', role=AgentRole.PRODUCER)
        reg.register(agent)
        assert reg.get('a1') is agent

    def test_find_available_by_role(self):
        reg = AgentRegistry()
        reg.register(AgentInfo(id='a', name='A', role=AgentRole.PRODUCER))
        reg.register(AgentInfo(id='b', name='B', role=AgentRole.EXECUTOR))
        producers = reg.find_available(role=AgentRole.PRODUCER)
        assert len(producers) == 1
        assert producers[0].id == 'a'

    def test_assign_and_release(self):
        reg = AgentRegistry()
        reg.register(AgentInfo(id='a', name='A', role=AgentRole.PRODUCER))
        reg.assign_task('a', 'task_1')
        assert reg.get('a').status == 'busy'
        assert not reg.find_available(role=AgentRole.PRODUCER)
        reg.release_agent('a')
        assert reg.get('a').status == 'idle'
        assert len(reg.find_available(role=AgentRole.PRODUCER)) == 1

    def test_unregister(self):
        reg = AgentRegistry()
        reg.register(AgentInfo(id='a', name='A', role=AgentRole.PRODUCER))
        assert reg.unregister('a')
        assert reg.get('a') is None


# ─── Task & Workflow ──────────────────────────────────────────────────────────

class TestTask:
    def test_default_status(self):
        t = Task(id='t1', type='env', payload={})
        assert t.status == TaskStatus.PENDING

    def test_is_blocked(self):
        t = Task(id='t2', type='exp', payload={}, dependencies=['t1'])
        assert t.is_blocked(set())
        assert not t.is_blocked({'t1'})

    def test_duration(self):
        t = Task(id='t1', type='env', payload={})
        assert t.duration() is None
        t.started_at = datetime.now()
        t.completed_at = datetime.now()
        assert t.duration() is not None


class TestWorkflow:
    def test_add_task(self):
        wf = Workflow(id='w1', name='test', description='')
        t = Task(id='t1', type='env', payload={})
        wf.add_task(t, 'stage1')
        assert 't1' in wf.tasks
        assert 'stage1' in wf.stages

    def test_get_ready_tasks(self):
        wf = Workflow(id='w1', name='test', description='')
        t1 = Task(id='t1', type='env', payload={})
        t2 = Task(id='t2', type='exp', payload={}, dependencies=['t1'])
        wf.add_task(t1, 's1')
        wf.add_task(t2, 's2')
        
        # Initially only t1 is ready (t2 blocked by t1)
        ready = wf.get_ready_tasks(set())
        assert len(ready) == 1
        assert ready[0].id == 't1'
        
        # After t1 completes, t2 becomes ready
        t1.status = TaskStatus.COMPLETED
        ready2 = wf.get_ready_tasks({'t1'})
        assert len(ready2) == 1
        assert ready2[0].id == 't2'

    def test_is_complete(self):
        wf = Workflow(id='w1', name='test', description='')
        t = Task(id='t1', type='env', payload={})
        wf.add_task(t, 's1')
        assert not wf.is_complete()
        t.status = TaskStatus.COMPLETED
        assert wf.is_complete()


# ─── Coordinator ─────────────────────────────────────────────────────────────

class TestCoordinator:
    def test_register_handler_and_run(self):
        coord = Coordinator()
        coord.register_agent(AgentInfo(id='a', name='A', role=AgentRole.PRODUCER))
        coord.register_handler('env', lambda t: {'result': 'ok'})

        wf = coord.create_workflow('test', '')
        wf.add_task(Task(id='t1', type='env', payload={}), 's1')

        result = coord.run_workflow(wf, timeout=5.0)
        assert result['status'] == 'completed'
        assert result['statistics']['completed'] == 1

    def test_dependency_chain(self):
        coord = Coordinator()
        coord.register_agent(AgentInfo(id='a', name='A', role=AgentRole.PRODUCER))
        coord.register_agent(AgentInfo(id='b', name='B', role=AgentRole.EXECUTOR))
        coord.register_handler('env', lambda t: {'env': 'ok'})
        coord.register_handler('exp', lambda t: {'exp': 'ok'})

        wf = coord.create_workflow('test', '')
        wf.add_task(Task(id='t1', type='env', payload={}), 's1')
        wf.add_task(Task(id='t2', type='exp', payload={}, dependencies=['t1']), 's2')

        result = coord.run_workflow(wf, timeout=5.0)
        assert result['status'] == 'completed'
        assert result['statistics']['completed'] == 2
        assert result['tasks']['t1']['result'] == {'env': 'ok'}
        assert result['tasks']['t2']['result'] == {'exp': 'ok'}

    def test_failed_task(self):
        coord = Coordinator()
        coord.register_agent(AgentInfo(id='a', name='A', role=AgentRole.PRODUCER))
        coord.register_handler('env', lambda t: (_ for _ in ()).throw(ValueError('fail')))

        wf = coord.create_workflow('test', '')
        wf.add_task(Task(id='t1', type='env', payload={}), 's1')

        result = coord.run_workflow(wf, timeout=5.0)
        assert result['tasks']['t1']['status'] == 'failed'
        assert 'fail' in result['tasks']['t1']['error']

    def test_get_status(self):
        coord = Coordinator()
        coord.register_agent(AgentInfo(id='a', name='A', role=AgentRole.PRODUCER))
        status = coord.get_status()
        assert 'agents' in status
        assert 'a' in status['agents']


# ─── DualAgentCoordinator ────────────────────────────────────────────────────

class TestDualAgentCoordinator:
    def test_run_episode(self, coordinator):
        ep = coordinator.run_episode(stage='beginner')
        assert ep.episode_id == 'ep_0001'
        assert ep.stage == 'beginner'
        assert ep.tasks_completed == 3
        assert ep.tasks_failed == 0
        assert ep.review_verdict in ('accept', 'revise', 'reject')
        assert ep.duration > 0

    def test_run_training(self, coordinator):
        results = coordinator.run_training(episodes=3)
        assert len(results) == 3
        for r in results:
            assert r.tasks_completed == 3

    def test_statistics(self, coordinator):
        coordinator.run_training(episodes=2)
        stats = coordinator.get_statistics()
        assert stats['episodes'] == 2
        assert 'average_keep_rate' in stats
        assert 'verdict_distribution' in stats

    def test_callback(self, coordinator):
        called = []
        coordinator.set_callbacks(on_episode_complete=lambda ep: called.append(ep.episode_id))
        coordinator.run_training(episodes=2)
        assert len(called) == 2

    def test_stage_determination(self, coordinator):
        assert coordinator._determine_stage(0.1).value == 'beginner'
        assert coordinator._determine_stage(0.4).value == 'intermediate'
        assert coordinator._determine_stage(0.8).value == 'advanced'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
