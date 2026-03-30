"""测试验证机制

测试 SelfVerifier、ConfidenceTracker 和 EnhancedRewardCalculator
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rl.self_verifier import (
    SelfVerifier,
    ConfidenceTracker,
    VerificationContext,
    VerificationResult,
)
from rl.enhanced_reward_calculator import EnhancedRewardCalculator, EnhancedReward


class TestSelfVerifier:
    """SelfVerifier 测试套件"""
    
    @pytest.fixture
    def verifier(self):
        """创建测试用验证器"""
        return SelfVerifier()
    
    @pytest.fixture
    def sample_trajectory(self):
        """创建示例轨迹"""
        return {
            'id': 'test_001',
            'description': 'Test trajectory',
            'predicted_tools': ['git', 'moon'],
            'ground_truth_tools': ['git', 'moon'],
            'predicted_params': {'repo': 'test/repo', 'branch': 'main'},
            'ground_truth_params': {'repo': 'test/repo', 'branch': 'main'},
        }
    
    def test_verifier_initialization(self, verifier):
        """测试验证器初始化"""
        assert verifier is not None
        assert hasattr(verifier, 'verify')
    
    def test_verify_exact_match(self, verifier, sample_trajectory):
        """测试完全匹配验证"""
        context = VerificationContext(
            trajectory=sample_trajectory,
            expected={
                'tools': sample_trajectory['ground_truth_tools'],
                'params': sample_trajectory['ground_truth_params'],
            },
            actual={
                'tools': sample_trajectory['predicted_tools'],
                'params': sample_trajectory['predicted_params'],
            }
        )
        
        result = verifier.verify(context)
        
        assert result is not None
        assert isinstance(result, VerificationResult)
        assert result.exact_match is True
        assert result.confidence >= 0.9
    
    def test_verify_partial_match(self, verifier):
        """测试部分匹配验证"""
        trajectory = {
            'id': 'test_002',
            'predicted_tools': ['git', 'moon'],
            'predicted_params': {'repo': 'test/repo'},
        }
        
        context = VerificationContext(
            trajectory=trajectory,
            expected={
                'tools': ['git', 'docker'],
                'params': {'repo': 'other/repo'},
            },
            actual={
                'tools': ['git', 'moon'],
                'params': {'repo': 'test/repo'},
            }
        )
        
        result = verifier.verify(context)
        
        assert result is not None
        assert result.exact_match is False
        assert 0 < result.confidence < 1.0
    
    def test_verify_empty_trajectory(self, verifier):
        """测试空轨迹验证"""
        context = VerificationContext(
            trajectory={},
            expected={'tools': ['git'], 'params': {'repo': 'test'}},
            actual={'tools': [], 'params': {}}
        )
        
        result = verifier.verify(context)
        
        assert result is not None
        # 空轨迹与期望不匹配时应该返回低置信度
        assert result.exact_match is False or result.confidence < 1.0


class TestConfidenceTracker:
    """ConfidenceTracker 测试套件"""
    
    @pytest.fixture
    def tracker(self):
        """创建测试用追踪器"""
        return ConfidenceTracker()
    
    def test_tracker_initialization(self, tracker):
        """测试追踪器初始化"""
        assert tracker is not None
        assert hasattr(tracker, 'add')
        assert hasattr(tracker, 'get_summary')
    
    def test_add_confidence(self, tracker):
        """测试添加置信度"""
        tracker.add(0.8)
        tracker.add(0.9)
        tracker.add(0.7)
        
        summary = tracker.get_summary()
        
        assert 'average' in summary
        assert summary['average'] == pytest.approx(0.8, abs=0.01)
    
    def test_confidence_trend(self, tracker):
        """测试置信度趋势"""
        # 添加递增的置信度
        for i in range(10):
            tracker.add(0.5 + i * 0.05)
        
        summary = tracker.get_summary()
        
        assert 'trend' in summary
        # 趋势可能是 increasing, improving, stable 等
        assert summary['trend'] in ['improving', 'stable', 'increasing']
    
    def test_confidence_stability(self, tracker):
        """测试置信度稳定性"""
        # 添加稳定的置信度
        for _ in range(10):
            tracker.add(0.8)
        
        summary = tracker.get_summary()
        
        assert 'stability' in summary
        assert summary['stability'] >= 0.9
    
    def test_alert_detection(self, tracker):
        """测试告警检测"""
        # 添加低置信度
        for _ in range(10):
            tracker.add(0.3)
        
        summary = tracker.get_summary()
        
        assert summary.get('should_alert') is True
        assert 'alert_reason' in summary


class TestEnhancedRewardCalculator:
    """EnhancedRewardCalculator 测试套件"""
    
    @pytest.fixture
    def calculator(self):
        """创建测试用计算器"""
        return EnhancedRewardCalculator()
    
    @pytest.fixture
    def sample_trajectory(self):
        """创建示例轨迹"""
        return {
            'id': 'test_001',
            'description': 'Test trajectory',
            'predicted_tools': ['git', 'moon'],
            'ground_truth_tools': ['git', 'moon'],
            'predicted_params': {'repo': 'test/repo'},
            'ground_truth_params': {'repo': 'test/repo'},
        }
    
    def test_calculator_initialization(self, calculator):
        """测试计算器初始化"""
        assert calculator is not None
        assert hasattr(calculator, 'calculate')
    
    def test_calculate_reward(self, calculator, sample_trajectory):
        """测试奖励计算"""
        reward = calculator.calculate(sample_trajectory)
        
        assert reward is not None
        assert isinstance(reward, EnhancedReward)
        assert reward.total >= 0
    
    def test_reward_components(self, calculator, sample_trajectory):
        """测试奖励组件"""
        reward = calculator.calculate(sample_trajectory)
        
        assert hasattr(reward, 'rformat')
        assert hasattr(reward, 'rname')
        assert hasattr(reward, 'rparam')
        assert hasattr(reward, 'rvalue')
        
        # 验证组件值
        assert 0 <= reward.rformat <= 1
        assert 0 <= reward.rname <= 1
        assert 0 <= reward.rparam <= 1
        assert 0 <= reward.rvalue <= 1
    
    def test_verification_included(self, calculator, sample_trajectory):
        """测试验证结果包含"""
        reward = calculator.calculate(sample_trajectory)
        
        assert hasattr(reward, 'verification')
        # verification 可能是 VerificationResult 或 VerificationContext
        if reward.verification is not None:
            # 类型可能是 VerificationResult
            assert hasattr(reward.verification, 'confidence')
    
    def test_partial_match_lower_reward(self, calculator):
        """测试部分匹配奖励较低"""
        exact_trajectory = {
            'predicted_tools': ['git'],
            'ground_truth_tools': ['git'],
            'predicted_params': {'repo': 'test'},
            'ground_truth_params': {'repo': 'test'},
        }
        
        partial_trajectory = {
            'predicted_tools': ['git', 'moon'],
            'ground_truth_tools': ['git'],
            'predicted_params': {'repo': 'test'},
            'ground_truth_params': {'repo': 'other'},
        }
        
        exact_reward = calculator.calculate(exact_trajectory)
        partial_reward = calculator.calculate(partial_trajectory)
        
        assert exact_reward.total > partial_reward.total


class TestVerificationIntegration:
    """验证机制集成测试"""
    
    @pytest.mark.integration
    def test_full_verification_workflow(self):
        """测试完整验证工作流"""
        verifier = SelfVerifier()
        tracker = ConfidenceTracker()
        calculator = EnhancedRewardCalculator()
        
        # 创建测试轨迹
        trajectories = [
            {
                'id': f'test_{i}',
                'predicted_tools': ['git', 'moon'],
                'ground_truth_tools': ['git', 'moon'] if i % 2 == 0 else ['git'],
                'predicted_params': {'repo': 'test'},
                'ground_truth_params': {'repo': 'test'} if i % 2 == 0 else {'repo': 'other'},
            }
            for i in range(10)
        ]
        
        # 验证并计算奖励
        for traj in trajectories:
            # 创建验证上下文
            context = VerificationContext(
                trajectory=traj,
                expected={
                    'tools': traj.get('ground_truth_tools', []),
                    'params': traj.get('ground_truth_params', {}),
                },
                actual={
                    'tools': traj.get('predicted_tools', []),
                    'params': traj.get('predicted_params', {}),
                }
            )
            
            # 验证
            result = verifier.verify(context)
            
            # 追踪置信度
            tracker.add(result.confidence)
            
            # 计算奖励
            reward = calculator.calculate(traj)
            
            # 验证结果存在
            assert result is not None
            assert reward is not None
        
        # 获取总结
        summary = tracker.get_summary()
        
        assert 'average' in summary
        assert 'trend' in summary
        assert 'stability' in summary


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
