"""测试 Agent A - Generator (环境生成器)

测试内容：
1. AgentA 初始化
2. 进度分析
3. 学习阶段判断
4. 动态奖励缩放
5. 环境生成
"""

import pytest
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_a.generator import AgentA, TrainingEnvironment, AgentBProgress


class TestTrainingEnvironment:
    """TrainingEnvironment 测试"""
    
    def test_creation(self):
        env = TrainingEnvironment(
            id="test_1",
            name="Test Env",
            description="A test environment",
            difficulty=0.5,
            tasks=[],
            available_tools=["git", "moon"],
            tool_constraints={},
            reward_config={},
        )
        assert env.id == "test_1"
        assert env.name == "Test Env"
        assert env.difficulty == 0.5
    
    def test_minimal_creation(self):
        env = TrainingEnvironment(id="x", name="X", description="", tasks=[], difficulty=0.0, available_tools=[], tool_constraints={}, reward_config={})
        assert env.id == "x"


class TestAgentBProgress:
    """AgentBProgress 测试"""
    
    def test_creation(self):
        progress = AgentBProgress(
            total_experiments=10,
            keep_rate=0.6,
            best_score=2.5,
            weak_areas=["tool_selection"],
        )
        assert progress.total_experiments == 10
        assert progress.best_score == 2.5


class TestAgentA:
    """AgentA 核心测试"""
    
    @pytest.fixture
    def agent(self, tmp_path):
        """创建测试 Agent"""
        return AgentA(workspace=str(tmp_path))
    
    def test_initialization(self, agent):
        assert agent is not None
        assert hasattr(agent, 'analyze_progress')
        assert hasattr(agent, 'generate_environment')
        assert hasattr(agent, 'get_learning_stage')
    
    def test_analyze_progress_empty(self, agent, tmp_path):
        """测试空结果分析"""
        # 创建空 TSV
        tsv = tmp_path / "results.tsv"
        tsv.write_text("")
        
        progress = agent.analyze_progress(str(tsv))
        assert progress is not None
    
    def test_analyze_progress_with_data(self, agent, tmp_path):
        """测试有数据时分析"""
        tsv = tmp_path / "results.tsv"
        tsv.write_text("id\tstatus\tbpb_score\nexp1\tkeep\t0.8\nexp2\tdiscard\t0.3\n")
        
        progress = agent.analyze_progress(str(tsv))
        assert progress is not None
    
    def test_get_learning_stage(self, agent):
        """测试阶段判断"""
        progress_low = AgentBProgress(
            total_experiments=5, keep_rate=0.2, best_score=0.5, weak_areas=[]
        )
        stage = agent.get_learning_stage(progress_low)
        assert isinstance(stage, str)
        assert stage in ['beginner', 'intermediate', 'advanced']
    
    def test_get_dynamic_reward_scale(self, agent):
        """测试奖励缩放"""
        for stage in ['beginner', 'intermediate', 'advanced']:
            scale = agent.get_dynamic_reward_scale(stage)
            assert isinstance(scale, (float, dict))
    
    def test_generate_environment(self, agent, tmp_path):
        """测试环境生成"""
        tsv = tmp_path / "results.tsv"
        tsv.write_text("")
        
        progress = agent.analyze_progress(str(tsv))
        env = agent.generate_environment(progress)
        
        assert env is not None
        assert isinstance(env, TrainingEnvironment)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
