"""测试 GRPO - Group Relative Policy Optimization

测试内容：
1. 组相对优势计算
2. 策略损失计算
3. 策略网络采样
4. KL 散度
"""

import pytest
import sys
import os
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rl.grpo import GRPO, GRPOConfig, PolicyNetwork, PolicyOutput, compute_grpo_loss


class TestGRPOConfig:
    """GRPO 配置测试"""
    
    def test_default_config(self):
        config = GRPOConfig()
        assert config.group_size == 4
        assert config.clip_ratio == 0.2
        assert config.entropy_coef == 0.01
    
    def test_custom_config(self):
        config = GRPOConfig(group_size=8, clip_ratio=0.3)
        assert config.group_size == 8
        assert config.clip_ratio == 0.3


class TestPolicyNetwork:
    """策略网络测试"""
    
    @pytest.fixture
    def policy(self):
        return PolicyNetwork(action_dim=5, state_dim=32)
    
    def test_get_action_probs(self, policy):
        probs = policy.get_action_probs({'test': 'state'})
        
        assert len(probs) == 5
        assert all(isinstance(p, float) for p in probs)
        # 概率和为 1
        assert abs(sum(probs) - 1.0) < 0.01
    
    def test_sample_action(self, policy):
        output = policy.sample_action({'test': 'state'})
        
        assert isinstance(output, PolicyOutput)
        assert 'index' in output.action
        assert 0 <= output.action['index'] < 5
        assert isinstance(output.log_prob, float)
        assert isinstance(output.entropy, float)
        assert output.entropy >= 0
    
    def test_sample_with_temperature(self, policy):
        # 低温应该更确定
        probs_low = policy.get_action_probs({'test': 'state'})
        output_low = policy.sample_action({'test': 'state'}, temperature=0.1)
        assert output_low.action['index'] is not None
    
    def test_evaluate_action(self, policy):
        action = {'index': 0}
        log_prob, entropy = policy.evaluate_action({'test': 'state'}, action)
        
        assert isinstance(log_prob, float)
        assert isinstance(entropy, float)
        assert entropy >= 0
    
    def test_different_states_different_probs(self, policy):
        probs1 = policy.get_action_probs({'id': 1})
        probs2 = policy.get_action_probs({'id': 999})
        # 不同状态可能有不同概率
        assert len(probs1) == len(probs2)


class TestGRPO:
    """GRPO 核心测试"""
    
    @pytest.fixture
    def grpo(self):
        return GRPO(GRPOConfig(group_size=4, normalize_advantage=False))
    
    def test_compute_group_advantages(self, grpo):
        rewards = [1.0, 2.0, 3.0, 4.0]
        
        advantages = grpo.compute_group_advantages(rewards)
        
        assert len(advantages) == 4
        # 优势之和应该为 0
        assert abs(sum(advantages)) < 0.01
    
    def test_compute_group_advantages_multiple_groups(self, grpo):
        rewards = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
        
        advantages = grpo.compute_group_advantages(rewards)
        
        assert len(advantages) == 8
        # 每组内优势之和应该为 0
        for i in range(0, 8, 4):
            group_adv = advantages[i:i+4]
            assert abs(sum(group_adv)) < 0.01
    
    def test_compute_group_advantages_custom_size(self, grpo):
        grpo.config.group_size = 2
        rewards = [1.0, 3.0, 2.0, 4.0]
        
        advantages = grpo.compute_group_advantages(rewards)
        
        assert len(advantages) == 4
        # 组 1: [1, 3] 组 2: [2, 4]
        assert abs(advantages[0] + advantages[1]) < 0.01
    
    def test_compute_group_advantages_equal_rewards(self, grpo):
        rewards = [5.0, 5.0, 5.0, 5.0]
        
        advantages = grpo.compute_group_advantages(rewards)
        
        # 所有优势应该为 0
        assert all(abs(a) < 0.01 for a in advantages)
    
    def test_update(self, grpo):
        states = [{'id': i} for i in range(4)]
        actions = [{'index': i % 5} for i in range(4)]
        rewards = [1.0, 2.0, 3.0, 4.0]
        
        result = grpo.update(states, actions, rewards)
        
        assert 'loss' in result
        assert 'mean_reward' in result
        assert result['mean_reward'] == 2.5
        assert result['updates'] == 1
    
    def test_sample_actions(self, grpo):
        states = [{'id': i} for i in range(3)]
        
        outputs = grpo.sample_actions(states)
        
        assert len(outputs) == 3
        assert all(isinstance(o, PolicyOutput) for o in outputs)
    
    def test_get_stats(self, grpo):
        states = [{'id': i} for i in range(4)]
        actions = [{'index': 0} for i in range(4)]
        rewards = [1.0, 2.0, 3.0, 4.0]
        
        grpo.update(states, actions, rewards)
        stats = grpo.get_stats()
        
        assert 'updates' in stats
        assert stats['updates'] == 1
        assert 'config' in stats
    
    def test_save_reference_policy(self, grpo):
        grpo.save_reference_policy()
        assert grpo.ref_policy is not None
    
    def test_compute_kl_divergence_no_ref(self, grpo):
        kl = grpo.compute_kl_divergence([{'id': 1}])
        assert kl == 0.0
    
    def test_compute_kl_divergence_with_ref(self, grpo):
        grpo.save_reference_policy()
        kl = grpo.compute_kl_divergence([{'id': 1}])
        assert isinstance(kl, float)
        assert kl >= 0.0


class TestGRPOConvenienceFunction:
    """便捷函数测试"""
    
    def test_compute_grpo_loss(self):
        rewards = [1.0, 2.0, 3.0, 4.0]
        log_probs = [-2.0, -1.5, -1.0, -0.5]
        
        loss = compute_grpo_loss(rewards, log_probs)
        
        assert isinstance(loss, float)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
