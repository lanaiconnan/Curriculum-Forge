"""测试 Experience Buffer

测试内容：
1. 经验添加和采样
2. 优先级经验回放
3. 去重机制
4. 保存和加载
"""

import pytest
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.experience_buffer import (
    ExperienceBuffer,
    PrioritizedExperienceBuffer,
    Experience,
)


class TestExperience:
    """Experience 数据类测试"""
    
    def test_creation(self):
        exp = Experience(
            state={'task': 'test'},
            action={'tool': 'git'},
            reward=1.0,
            next_state={},
            done=False,
        )
        
        assert exp.reward == 1.0
        assert exp.done is False
        assert exp.timestamp is not None
    
    def test_to_dict(self):
        exp = Experience(
            state={'task': 'test'},
            action={'tool': 'git'},
            reward=1.0,
            next_state={},
            done=False,
        )
        
        data = exp.to_dict()
        assert data['reward'] == 1.0
        assert data['done'] is False
    
    def test_from_dict(self):
        data = {
            'state': {'task': 'test'},
            'action': {'tool': 'git'},
            'reward': 1.0,
            'next_state': {},
            'done': False,
        }
        
        exp = Experience.from_dict(data)
        assert exp.reward == 1.0
        assert exp.state == {'task': 'test'}


class TestExperienceBuffer:
    """ExperienceBuffer 测试套件"""
    
    @pytest.fixture
    def buffer(self):
        return ExperienceBuffer(capacity=100, use_priority=False)
    
    def test_add(self, buffer):
        exp = Experience(
            state={'d': 'task1'},
            action={'t': 'git'},
            reward=1.0,
            next_state={},
            done=False,
        )
        
        success = buffer.add(exp)
        assert success is True
        assert len(buffer.buffer) == 1
    
    def test_add_duplicate(self, buffer):
        exp = Experience(
            state={'description': 'unique task xyz'},
            action={'t': 'git'},
            reward=1.0,
            next_state={},
            done=False,
        )
        
        buffer.add(exp)
        success = buffer.add(exp)
        
        # 应该拒绝重复
        assert success is False
        assert len(buffer.buffer) == 1
        assert buffer.stats['duplicates_rejected'] == 1
    
    def test_add_without_dedup(self, buffer):
        exp = Experience(
            state={'d': 'task'},
            action={'t': 'git'},
            reward=1.0,
            next_state={},
            done=False,
        )
        
        buffer.add(exp)
        success = buffer.add(exp, check_duplicate=False)
        
        assert success is True
        assert len(buffer.buffer) == 2
    
    def test_add_batch(self, buffer):
        exps = [
            Experience(
                state={'d': f'task{i}'},
                action={'t': 'git'},
                reward=float(i),
                next_state={},
                done=False,
            )
            for i in range(10)
        ]
        
        added = buffer.add_batch(exps)
        assert added == 10
        assert len(buffer.buffer) == 10
    
    def test_sample_uniform(self, buffer):
        for i in range(20):
            buffer.add(Experience(
                state={'d': f'task{i}'},
                action={'t': 'git'},
                reward=float(i),
                next_state={},
                done=False,
            ), check_duplicate=False)
        
        samples = buffer.sample(5, use_priority=False)
        
        assert len(samples) == 5
    
    def test_sample_empty(self, buffer):
        samples = buffer.sample(5)
        assert samples == []
    
    def test_sample_exceeds_size(self, buffer):
        for i in range(5):
            buffer.add(Experience(
                state={'d': f'task{i}'},
                action={'t': 'git'},
                reward=float(i),
                next_state={},
                done=False,
            ), check_duplicate=False)
        
        samples = buffer.sample(10, use_priority=False)
        assert len(samples) == 5
    
    def test_get_recent(self, buffer):
        for i in range(10):
            buffer.add(Experience(
                state={'d': f'task{i}'},
                action={'t': 'git'},
                reward=float(i),
                next_state={},
                done=False,
            ), check_duplicate=False)
        
        recent = buffer.get_recent(3)
        assert len(recent) == 3
        # 最新的应该有最高的 reward
        assert recent[-1].reward == 9.0
    
    def test_get_by_reward(self, buffer):
        for i in range(10):
            buffer.add(Experience(
                state={'d': f'task{i}'},
                action={'t': 'git'},
                reward=float(i),
                next_state={},
                done=False,
            ), check_duplicate=False)
        
        top = buffer.get_by_reward(3)
        assert len(top) == 3
        assert top[0].reward == 9.0
    
    def test_capacity_limit(self):
        buf = ExperienceBuffer(capacity=5)
        for i in range(10):
            buf.add(Experience(
                state={'d': f'task{i}'},
                action={'t': 'git'},
                reward=float(i),
                next_state={},
                done=False,
            ), check_duplicate=False)
        
        assert len(buf.buffer) == 5
    
    def test_clear(self, buffer):
        buffer.add(Experience(
            state={'d': 'task'},
            action={'t': 'git'},
            reward=1.0,
            next_state={},
            done=False,
        ))
        
        buffer.clear()
        assert len(buffer.buffer) == 0
    
    def test_save_and_load(self, tmp_path):
        buf = ExperienceBuffer(capacity=100)
        buf.add(Experience(
            state={'d': 'task1'},
            action={'t': 'git'},
            reward=1.5,
            next_state={},
            done=False,
        ), check_duplicate=False)
        buf.add(Experience(
            state={'d': 'task2'},
            action={'t': 'moon'},
            reward=2.5,
            next_state={},
            done=False,
        ), check_duplicate=False)
        
        filepath = str(tmp_path / "buffer.json")
        buf.save(filepath)
        
        # 加载
        new_buf = ExperienceBuffer(capacity=100)
        new_buf.load(filepath)
        
        assert len(new_buf.buffer) == 2
    
    def test_get_stats(self, buffer):
        for i in range(5):
            buffer.add(Experience(
                state={'d': f'task{i}'},
                action={'t': 'git'},
                reward=float(i),
                next_state={},
                done=False,
            ), check_duplicate=False)
        
        stats = buffer.get_stats()
        
        assert stats['buffer_size'] == 5
        assert stats['capacity'] == 100
        assert stats['total_added'] == 5
        assert stats['fill_ratio'] == 0.05


class TestPrioritizedExperienceBuffer:
    """优先级经验回放测试"""
    
    @pytest.fixture
    def per(self):
        return PrioritizedExperienceBuffer(capacity=100, alpha=0.6, beta=0.4)
    
    def test_auto_priority(self, per):
        exp = Experience(
            state={'d': 'task1'},
            action={'t': 'git'},
            reward=1.0,
            next_state={},
            done=False,
        )
        
        success = per.add(exp)
        assert success is True
        assert exp.priority == per.max_priority
    
    def test_sample_with_weights(self, per):
        for i in range(10):
            per.add(Experience(
                state={'d': f'task{i}'},
                action={'t': 'git'},
                reward=float(i),
                next_state={},
                done=False,
            ), check_duplicate=False)
        
        samples, weights = per.sample_with_weights(5)
        
        assert len(samples) == 5
        assert len(weights) == 5
        assert all(w >= 0 for w in weights)
    
    def test_beta_increment(self, per):
        initial_beta = per.beta
        
        per.add(Experience(
            state={'d': 'task'},
            action={'t': 'git'},
            reward=1.0,
            next_state={},
            done=False,
        ), check_duplicate=False)
        
        per.sample_with_weights(1)
        
        # beta 应该增加
        assert per.beta >= initial_beta
    
    def test_beta_capped_at_one(self):
        per = PrioritizedExperienceBuffer(beta=0.999, beta_increment=0.01)
        
        for i in range(5):
            per.add(Experience(
                state={'d': f'task{i}'},
                action={'t': 'git'},
                reward=float(i),
                next_state={},
                done=False,
            ), check_duplicate=False)
        
        per.sample_with_weights(1)
        
        assert per.beta <= 1.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
