"""TEST 阶段 - 单元测试和集成测试"""

import unittest
import sys
import os
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from rl.trainer import RewardCalculator, RLTrainer, RLConfig
from agent_a.generator import AgentA, AgentBProgress
from tools.base import Tool, ToolResult


class TestRewardCalculator(unittest.TestCase):
    """测试 ToolRL 风格的奖励计算"""
    
    def setUp(self):
        self.calc = RewardCalculator()
    
    def test_format_reward_valid(self):
        """测试格式奖励 - 有效轨迹"""
        trajectory = {
            'think': 'thinking',
            'tool_call': 'calling',
            'response': 'responding',
            'think_idx': 0,
            'tool_call_idx': 1,
            'response_idx': 2,
        }
        r_format = self.calc.calculate_format_reward(trajectory)
        self.assertEqual(r_format, 1.0)
    
    def test_format_reward_invalid_order(self):
        """测试格式奖励 - 无效顺序"""
        trajectory = {
            'think_idx': 2,
            'tool_call_idx': 1,
            'response_idx': 0,
        }
        r_format = self.calc.calculate_format_reward(trajectory)
        self.assertEqual(r_format, 0.0)
    
    def test_tool_name_match_perfect(self):
        """测试工具名称匹配 - 完美匹配"""
        predicted = ['git', 'moon']
        ground_truth = ['git', 'moon']
        r_name = self.calc.calculate_tool_name_match(predicted, ground_truth)
        self.assertEqual(r_name, 1.0)
    
    def test_tool_name_match_partial(self):
        """测试工具名称匹配 - 部分匹配"""
        predicted = ['git', 'moon']
        ground_truth = ['git', 'curl']
        r_name = self.calc.calculate_tool_name_match(predicted, ground_truth)
        self.assertAlmostEqual(r_name, 1/3)  # 1 交集 / 3 并集
    
    def test_param_value_match(self):
        """测试参数值匹配"""
        predicted = {'branch': 'feature-x', 'message': 'fix bug'}
        ground_truth = {'branch': 'feature-x', 'message': 'optimize'}
        r_value = self.calc.calculate_param_value_match(predicted, ground_truth)
        self.assertAlmostEqual(r_value, 0.5)  # 1 匹配 / 2 总数
    
    def test_total_reward(self):
        """测试总奖励计算"""
        trajectory = {
            'think': 'thinking',
            'tool_call': 'calling',
            'response': 'responding',
            'think_idx': 0,
            'tool_call_idx': 1,
            'response_idx': 2,
            'predicted_tools': ['git'],
            'ground_truth_tools': ['git'],
            'predicted_params': {'branch': 'main'},
            'ground_truth_params': {'branch': 'main'},
        }
        r_total = self.calc.calculate(trajectory)
        # r_format=1.0 + r_correct=(1.0+1.0+1.0)*3/3=1.0 + 1.0 = 2.0
        # 但实际上 r_correct = (1.0 + 1.0 + 1.0) * 3.0 / 3.0 = 3.0
        # 所以 r_total = 1.0 + 3.0 = 4.0
        self.assertAlmostEqual(r_total, 4.0)


class TestRLTrainer(unittest.TestCase):
    """测试 GRPO 训练器"""
    
    def setUp(self):
        self.trainer = RLTrainer(RLConfig())
    
    def test_group_normalized_advantages(self):
        """测试组归一化优势计算"""
        rewards = [1.0, 2.0, 3.0]
        advantages = self.trainer.compute_group_normalized_advantages(rewards)
        
        # 平均值 = 2.0
        # 标准差 = sqrt((1+0+1)/3) = sqrt(2/3)
        # A1 = (1-2) / sqrt(2/3) = -sqrt(3/2)
        # A2 = (2-2) / sqrt(2/3) = 0
        # A3 = (3-2) / sqrt(2/3) = sqrt(3/2)
        
        self.assertLess(advantages[0], 0)
        self.assertAlmostEqual(advantages[1], 0)
        self.assertGreater(advantages[2], 0)
    
    def test_train_step_grpo(self):
        """测试 GRPO 训练步骤"""
        results = [
            {
                'id': 'exp1',
                'description': 'test1',
                'predicted_tools': ['git'],
                'ground_truth_tools': ['git'],
                'predicted_params': {},
                'ground_truth_params': {},
            },
            {
                'id': 'exp2',
                'description': 'test2',
                'predicted_tools': ['moon'],
                'ground_truth_tools': ['moon'],
                'predicted_params': {},
                'ground_truth_params': {},
            },
        ]
        
        stats = self.trainer.train_step(results, use_grpo=True)
        
        self.assertEqual(stats['method'], 'GRPO')
        self.assertGreater(stats['total_reward'], 0)
        self.assertEqual(len(self.trainer.experiences), 2)


class TestAgentA(unittest.TestCase):
    """测试环境生成器"""
    
    def setUp(self):
        self.agent_a = AgentA()
    
    def test_learning_stage_beginner(self):
        """测试学习阶段 - 新手期"""
        progress = AgentBProgress(total_experiments=5, keep_rate=0.2)
        stage = self.agent_a.get_learning_stage(progress)
        self.assertEqual(stage, 'beginner')
    
    def test_learning_stage_intermediate(self):
        """测试学习阶段 - 成长期"""
        progress = AgentBProgress(total_experiments=20, keep_rate=0.45)
        stage = self.agent_a.get_learning_stage(progress)
        self.assertEqual(stage, 'intermediate')
    
    def test_learning_stage_advanced(self):
        """测试学习阶段 - 成熟期"""
        progress = AgentBProgress(total_experiments=50, keep_rate=0.75)
        stage = self.agent_a.get_learning_stage(progress)
        self.assertEqual(stage, 'advanced')
    
    def test_dynamic_reward_scale(self):
        """测试动态奖励尺度"""
        self.assertEqual(self.agent_a.get_dynamic_reward_scale('beginner'), 1.0)
        self.assertEqual(self.agent_a.get_dynamic_reward_scale('intermediate'), 0.7)
        self.assertEqual(self.agent_a.get_dynamic_reward_scale('advanced'), 0.5)
    
    def test_generate_environment_beginner(self):
        """测试环境生成 - 新手期"""
        progress = AgentBProgress(total_experiments=5, keep_rate=0.2)
        env = self.agent_a.generate_environment(progress)
        
        self.assertEqual(env.difficulty, 0.3)
        self.assertEqual(len(env.tasks), 2)
        self.assertEqual(env.reward_config['stage'], 'beginner')
        self.assertEqual(env.tool_constraints['max_tool_calls'], 10)
    
    def test_generate_environment_advanced(self):
        """测试环境生成 - 成熟期"""
        progress = AgentBProgress(total_experiments=50, keep_rate=0.75)
        env = self.agent_a.generate_environment(progress)
        
        self.assertEqual(env.difficulty, 0.7)
        self.assertEqual(len(env.tasks), 4)
        self.assertEqual(env.reward_config['stage'], 'advanced')
        self.assertEqual(env.tool_constraints['max_tool_calls'], 20)


class TestIntegration(unittest.TestCase):
    """集成测试"""
    
    def test_full_pipeline(self):
        """测试完整流程：Agent A → 奖励计算 → Agent A 升级"""
        agent_a = AgentA()
        trainer = RLTrainer()
        
        # 初始状态：新手期
        progress = AgentBProgress(total_experiments=5, keep_rate=0.2)
        env1 = agent_a.generate_environment(progress)
        self.assertEqual(env1.reward_config['stage'], 'beginner')
        
        # 模拟实验结果
        results = [
            {
                'id': f'exp{i}',
                'description': f'test{i}',
                'predicted_tools': ['git'],
                'ground_truth_tools': ['git'],
                'predicted_params': {},
                'ground_truth_params': {},
            }
            for i in range(5)
        ]
        
        stats = trainer.train_step(results, use_grpo=True)
        self.assertGreater(stats['total_reward'], 0)
        
        # 升级到成长期
        progress = AgentBProgress(total_experiments=20, keep_rate=0.45)
        env2 = agent_a.generate_environment(progress)
        self.assertEqual(env2.reward_config['stage'], 'intermediate')
        self.assertGreater(env2.difficulty, env1.difficulty)


def run_tests():
    """运行所有测试"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试类
    suite.addTests(loader.loadTestsFromTestCase(TestRewardCalculator))
    suite.addTests(loader.loadTestsFromTestCase(TestRLTrainer))
    suite.addTests(loader.loadTestsFromTestCase(TestAgentA))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
