"""测试 Analyst Agent

测试 analyst.py 的核心功能：
1. 结果分析
2. 趋势识别
3. 异常检测
4. 洞察生成
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_a.analyst import AnalystAgent, AnalysisReport, TrendAnalysis, TrendDirection


class TestAnalystAgent:
    """Analyst Agent 测试套件"""
    
    @pytest.fixture
    def agent(self):
        """创建测试用 Agent"""
        return AnalystAgent(scratchpad=None)
    
    @pytest.fixture
    def sample_results(self):
        """创建示例结果"""
        results = []
        for i in range(10):
            results.append({
                'id': f'exp_{i}',
                'reward': 0.5 + i * 0.05,
                'success': i % 2 == 0,
                'tools_used': ['git', 'moon'],
                'tokens_used': 100 + i * 10,
                'description': f'Test experiment {i}',
            })
        return results
    
    def test_agent_initialization(self, agent):
        """测试 Agent 初始化"""
        assert agent.scratchpad is None
        assert len(agent.history) == 0
        assert agent.volatility_threshold == 0.3
        assert agent.slope_threshold == 0.05
    
    def test_analyze(self, agent, sample_results):
        """测试分析功能"""
        report = agent.analyze(sample_results)
        
        assert isinstance(report, AnalysisReport)
        assert report.experiment_count == 10
        assert report.summary is not None
        assert len(agent.history) == 1
    
    def test_analyze_trends(self, agent, sample_results):
        """测试趋势分析"""
        trends = agent._analyze_trends(sample_results)
        
        assert 'reward' in trends
        assert isinstance(trends['reward'], TrendAnalysis)
        # 奖励应该呈改善趋势
        assert trends['reward'].direction in [TrendDirection.IMPROVING, TrendDirection.STABLE, TrendDirection.UNKNOWN]
    
    def test_identify_patterns(self, agent, sample_results):
        """测试模式识别"""
        patterns = agent._identify_patterns(sample_results)
        
        # _identify_patterns 返回列表
        assert isinstance(patterns, (list, dict))
    
    def test_empty_results(self, agent):
        """测试空结果处理"""
        report = agent.analyze([])
        
        assert report.experiment_count == 0
        assert report.summary is not None
    
    def test_history_tracking(self, agent, sample_results):
        """测试历史追踪"""
        # 多次分析
        for i in range(3):
            agent.analyze(sample_results)
        
        assert len(agent.history) == 3


class TestAnalystAgentIntegration:
    """集成测试"""
    
    def test_full_analysis_cycle(self):
        """测试完整分析周期"""
        agent = AnalystAgent(scratchpad=None)
        
        # 创建更复杂的结果
        results = []
        for i in range(20):
            results.append({
                'id': f'exp_{i}',
                'reward': 0.5 + i * 0.02 + (i % 3) * 0.01,  # 添加一些波动
                'success': i % 3 != 0,
                'tools_used': ['git', 'moon'] if i % 2 == 0 else ['git'],
                'tokens_used': 100 + i * 5,
                'description': f'Test experiment {i}',
            })
        
        # 分析
        report = agent.analyze(results)
        
        # 验证完整流程
        assert report.experiment_count == 20
        assert report.summary is not None
        assert report.trend_analysis is not None
        assert report.patterns is not None
