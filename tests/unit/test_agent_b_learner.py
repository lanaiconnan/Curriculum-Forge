"""测试 Agent B - Learner (学习者)

测试内容：
1. ExperimentIdea / ExperimentResult
2. AgentB 初始化
3. 想法生成
4. 实验执行
5. 时间统计
"""

import pytest
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_b.learner import AgentB, ExperimentIdea, ExperimentResult


class TestExperimentIdea:
    """ExperimentIdea 测试"""
    
    def test_creation(self):
        idea = ExperimentIdea(
            id="idea_1",
            description="Test idea",
            implementation="print('hello')",
            expected="Hello output",
            priority="high",
        )
        assert idea.id == "idea_1"
        assert idea.priority == "high"
    
    def test_defaults(self):
        idea = ExperimentIdea(id="x", description="d", implementation="i", expected="e")
        assert idea.priority == "medium"


class TestExperimentResult:
    """ExperimentResult 测试"""
    
    def test_creation(self):
        idea = ExperimentIdea(id="x", description="d", implementation="i", expected="e")
        result = ExperimentResult(
            idea=idea,
            commit="abc123",
            status="keep",
            metrics={"score": 0.85},
            output="Success!",
            reward=1.0,
        )
        assert result.status == "keep"
        assert result.reward == 1.0
    
    def test_to_dict(self):
        idea = ExperimentIdea(id="x", description="d", implementation="i", expected="e")
        result = ExperimentResult(
            idea=idea,
            commit="abc",
            status="keep",
            metrics={"score": 0.5},
            output="test",
            reward=0.5,
        )
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d['status'] == "keep"
    
    def test_to_tsv(self):
        idea = ExperimentIdea(id="x", description="test desc", implementation="i", expected="e")
        result = ExperimentResult(
            idea=idea,
            commit="abc",
            status="keep",
            metrics={"score": 0.5},
            output="test",
            reward=0.5,
        )
        tsv = result.to_tsv()
        assert "abc" in tsv
        assert "keep" in tsv


class TestAgentB:
    """AgentB 核心测试"""
    
    @pytest.fixture
    def agent(self, tmp_path):
        return AgentB(workspace=str(tmp_path))
    
    def test_initialization(self, agent):
        assert agent is not None
        assert hasattr(agent, 'propose_ideas')
        assert hasattr(agent, 'run_experiment')
    
    def test_set_baseline(self, agent):
        agent.set_baseline(0.5)
        assert agent.baseline == 0.5
    
    def test_propose_ideas(self, agent):
        """测试想法生成"""
        from agent_a.generator import TrainingEnvironment
        env = TrainingEnvironment(
            id="test", name="Test", description="", 
            tasks=[{"description": "test task", "target": "improve"}],
            difficulty=0.5, available_tools=[], tool_constraints={}, reward_config={}
        )
        ideas = agent.propose_ideas(env)
        assert isinstance(ideas, list)
    
    def test_propose_ideas_with_env(self, agent):
        """测试有环境约束的想法"""
        from agent_a.generator import TrainingEnvironment
        env = TrainingEnvironment(
            id="test", name="Test", description="", tasks=[], 
            difficulty=0.5, available_tools=[], tool_constraints={}, reward_config={}
        )
        ideas = agent.propose_ideas(env)
        assert isinstance(ideas, list)
    
    def test_run_experiment(self, agent):
        """测试实验执行"""
        idea = ExperimentIdea(
            id="test_1",
            description="Simple test",
            implementation="print('test')",
            expected="test",
        )
        result = agent.run_experiment(idea, "test environment")
        assert isinstance(result, ExperimentResult)
    
    def test_get_time_stats(self, agent):
        stats = agent.get_time_stats()
        assert isinstance(stats, dict)
        assert 'total_time' in stats
        assert 'max_time' in stats

    def test_reset_timer(self, agent):
        agent.reset_timer()
        stats = agent.get_time_stats()
        assert stats['total_time'] == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
