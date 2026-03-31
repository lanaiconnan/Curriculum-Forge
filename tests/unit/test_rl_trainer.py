"""测试 RL Trainer

测试内容：
1. RLExperience / RLConfig
2. RewardCalculator
3. RLTrainer 训练流程
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rl.trainer import RLExperience, RLConfig, RewardCalculator, RLTrainer


class TestRLExperience:
    """RLExperience 测试"""
    
    def test_creation(self):
        exp = RLExperience(
            state="initial",
            action="git commit",
            reward=1.0,
            next_state="committed",
            done=False,
            tool_calls=[{"tool": "git", "args": {}}],
        )
        assert exp.state == "initial"
        assert exp.reward == 1.0
        assert len(exp.tool_calls) == 1


class TestRLConfig:
    """RLConfig 测试"""
    
    def test_default_config(self):
        config = RLConfig()
        assert config.learning_rate == 3e-4
        assert config.gamma == 0.99
        assert config.epsilon == 0.2
    
    def test_custom_config(self):
        config = RLConfig(learning_rate=1e-3, gamma=0.95)
        assert config.learning_rate == 1e-3
        assert config.gamma == 0.95


class TestRewardCalculator:
    """RewardCalculator 测试"""
    
    @pytest.fixture
    def calc(self):
        return RewardCalculator()
    
    def test_calculate_format_reward(self, calc):
        traj = {"formatted": True, "output": "Valid"}
        reward = calc.calculate_format_reward(traj)
        assert isinstance(reward, float)
    
    def test_calculate_tool_name_match(self, calc):
        predicted = ["git", "moon"]
        actual = ["git", "memory"]
        reward = calc.calculate_tool_name_match(predicted, actual)
        assert 0.0 <= reward <= 1.0
    
    def test_calculate_tool_name_match_perfect(self, calc):
        tools = ["git", "moon"]
        reward = calc.calculate_tool_name_match(tools, tools)
        assert reward == 1.0
    
    def test_calculate_tool_name_match_empty(self, calc):
        # 空预测和真实都返回 0（根据实现）
        reward = calc.calculate_tool_name_match([], [])
        assert reward == 0.0
    
    def test_calculate_param_name_match(self, calc):
        predicted = {"message": "hi", "branch": "main"}
        actual = {"message": "hello", "tag": "v1"}
        reward = calc.calculate_param_name_match(predicted, actual)
        assert 0.0 <= reward <= 1.0
    
    def test_calculate_param_value_match(self, calc):
        predicted = {"branch": "main"}
        actual = {"branch": "main"}
        reward = calc.calculate_param_value_match(predicted, actual)
        assert reward == 1.0
    
    def test_calculate_correctness_reward(self, calc):
        traj = {
            "expected": "success",
            "actual": "success",
            "score": 0.9,
        }
        reward = calc.calculate_correctness_reward(traj)
        assert isinstance(reward, float)
    
    def test_calculate_full(self, calc):
        trajectory = {
            "formatted": True,
            "predicted_tools": ["git"],
            "actual_tools": ["git"],
            "predicted_params": {"m": "msg"},
            "actual_params": {"m": "msg"},
            "expected": "success",
            "actual": "success",
        }
        reward = calc.calculate(trajectory)
        assert isinstance(reward, float)


class TestRLTrainer:
    """RLTrainer 核心测试"""
    
    @pytest.fixture
    def trainer(self):
        return RLTrainer()
    
    def test_initialization(self, trainer):
        assert trainer is not None
        assert hasattr(trainer, 'add_experience')
        assert hasattr(trainer, 'update')
    
    def test_add_experience(self, trainer):
        exp = RLExperience(
            state="s1", action="a1", reward=1.0,
            next_state="s2", done=False, tool_calls=[]
        )
        trainer.add_experience(exp)
        # 应该不报错
    
    def test_compute_advantages(self, trainer):
        rewards = [1.0, 2.0, 3.0, 4.0]
        advantages = trainer.compute_advantages(rewards)
        assert len(advantages) == 4
        assert all(isinstance(a, float) for a in advantages)
    
    def test_compute_group_normalized_advantages(self, trainer):
        rewards = [1.0, 2.0, 3.0, 4.0]
        advantages = trainer.compute_group_normalized_advantages(rewards)
        assert len(advantages) == 4
    
    def test_update_empty(self, trainer):
        result = trainer.update()
        # update 返回 None 当经验不足时
        assert result is None or isinstance(result, dict)
    
    def test_train_step_empty(self, trainer):
        result = trainer.train_step([])
        assert isinstance(result, dict)
    
    def test_train_step_with_data(self, trainer):
        results = [
            {"score": 0.8, "verdict": "keep"},
            {"score": 0.3, "verdict": "discard"},
        ]
        result = trainer.train_step(results)
        assert isinstance(result, dict)
        assert "avg_reward" in result or "updates" in result


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
