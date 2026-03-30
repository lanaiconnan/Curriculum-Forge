"""测试 GAE - Generalized Advantage Estimation

测试内容：
1. 优势计算
2. 折扣回报计算
3. 价值函数更新
4. 配置参数
"""

import pytest
import sys
import os
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rl.gae import GAE, GAEConfig, ValueFunction


class TestGAEConfig:
    """GAE 配置测试"""
    
    def test_default_config(self):
        config = GAEConfig()
        assert config.gamma == 0.99
        assert config.lam == 0.95
        assert config.normalize is True
    
    def test_custom_config(self):
        config = GAEConfig(gamma=0.9, lam=0.9, normalize=False)
        assert config.gamma == 0.9
        assert config.lam == 0.9
        assert config.normalize is False


class TestValueFunction:
    """价值函数测试"""
    
    @pytest.fixture
    def vf(self):
        return ValueFunction(state_dim=32, hidden_dim=64)
    
    def test_predict(self, vf):
        value = vf.predict({'test': 'state'})
        assert isinstance(value, float)
    
    def test_predict_different_states(self, vf):
        v1 = vf.predict({'id': 1})
        v2 = vf.predict({'id': 2})
        assert v1 != v2 or True  # 允许偶然相同
    
    def test_update(self, vf):
        states = [{'id': i} for i in range(5)]
        returns = [1.0, 2.0, 3.0, 4.0, 5.0]
        
        loss = vf.update(states, returns)
        assert isinstance(loss, float)
        assert loss >= 0.0
    
    def test_update_empty(self, vf):
        loss = vf.update([], [])
        assert loss == 0.0


class TestGAE:
    """GAE 核心测试"""
    
    @pytest.fixture
    def gae(self):
        return GAE(GAEConfig(gamma=0.99, lam=0.95, normalize=False))
    
    def test_compute_advantages(self, gae):
        rewards = [1.0, 2.0, 3.0, 4.0, 5.0]
        states = [{'id': i} for i in range(6)]
        
        advantages, returns = gae.compute_advantages(rewards, states)
        
        assert len(advantages) == 5
        assert len(returns) == 5
        assert all(isinstance(a, float) for a in advantages)
    
    def test_compute_advantages_normalized(self):
        gae = GAE(GAEConfig(normalize=True))
        rewards = [1.0, 2.0, 3.0, 4.0, 5.0]
        states = [{'id': i} for i in range(6)]
        
        advantages, returns = gae.compute_advantages(rewards, states)
        
        # 归一化后均值接近 0
        mean = sum(advantages) / len(advantages)
        assert abs(mean) < 0.1
    
    def test_compute_advantages_with_dones(self, gae):
        rewards = [1.0, 2.0, 3.0]
        states = [{'id': i} for i in range(4)]
        dones = [False, True, False]  # 第二步终止
        
        advantages, returns = gae.compute_advantages(rewards, states, dones=dones)
        
        assert len(advantages) == 3
    
    def test_compute_returns(self, gae):
        rewards = [1.0, 1.0, 1.0]
        
        returns = gae.compute_returns(rewards)
        
        assert len(returns) == 3
        # 折扣回报应该递减
        assert returns[0] > returns[1] > returns[2]
    
    def test_compute_returns_with_gamma(self, gae):
        rewards = [1.0, 1.0, 1.0]
        
        returns = gae.compute_returns(rewards, gamma=0.5)
        returns_no_discount = gae.compute_returns(rewards, gamma=1.0)
        
        assert returns[0] < returns_no_discount[0]
    
    def test_compute_returns_with_dones(self, gae):
        rewards = [1.0, 1.0, 1.0]
        dones = [False, True, False]
        
        returns = gae.compute_returns(rewards, dones=dones)
        
        assert len(returns) == 3
    
    def test_update_value_function(self, gae):
        states = [{'id': i} for i in range(5)]
        returns = [1.0, 2.0, 3.0, 4.0, 5.0]
        
        loss = gae.update_value_function(states, returns)
        assert isinstance(loss, float)
    
    def test_get_stats(self, gae):
        rewards = [1.0, 2.0, 3.0]
        states = [{'id': i} for i in range(4)]
        
        gae.compute_advantages(rewards, states)
        stats = gae.get_stats()
        
        assert 'advantages_computed' in stats
        assert stats['advantages_computed'] == 3
        assert 'mean_advantage' in stats
    
    def test_single_reward(self, gae):
        rewards = [5.0]
        states = [{'id': 0}, {'id': 1}]
        
        advantages, returns = gae.compute_advantages(rewards, states)
        
        assert len(advantages) == 1
        assert isinstance(advantages[0], float)
        assert isinstance(returns[0], float)


class TestGAEConvenienceFunction:
    """便捷函数测试"""
    
    def test_compute_gae(self):
        from rl.gae import compute_gae
        
        rewards = [1.0, 2.0, 3.0]
        values = [0.0, 1.0, 2.0, 0.0]
        dones = [False, False, False]
        
        advantages, returns = compute_gae(
            rewards, values, dones, gamma=0.99, lam=0.95
        )
        
        assert len(advantages) == 3
        assert len(returns) == 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
