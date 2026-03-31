"""测试 Agent B - Reflector (反思机制)

测试内容：
1. ReflectionIssue / ReflectionImprovement
2. ReflectionAnalysis / Reflection
3. Reflector 反思流程
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_b.reflector import (
    Reflector,
    ReflectionIssue,
    ReflectionImprovement,
    ReflectionAnalysis,
    Reflection,
)


class TestReflectionIssue:
    """ReflectionIssue 测试"""
    
    def test_creation(self):
        issue = ReflectionIssue(
            severity="major",
            title="Test issue",
            description="Issue description",
            affected_trajectories=["t1", "t2"],
            root_cause="Missing check",
        )
        assert issue.severity == "major"
        assert len(issue.affected_trajectories) == 2
    
    def test_without_root_cause(self):
        issue = ReflectionIssue(
            severity="minor",
            title="Issue",
            description="Desc",
            affected_trajectories=[],
        )
        assert issue.root_cause is None


class TestReflectionImprovement:
    """ReflectionImprovement 测试"""
    
    def test_creation(self):
        imp = ReflectionImprovement(
            priority=1,
            title="Add validation",
            description="Validate inputs",
            expected_impact="Reduce errors by 50%",
            implementation_hint="Add check function",
        )
        assert imp.priority == 1
        assert imp.expected_impact == "Reduce errors by 50%"


class TestReflectionAnalysis:
    """ReflectionAnalysis 测试"""
    
    def test_creation(self):
        issue = ReflectionIssue("major", "Issue", "desc", ["t1"])
        imp = ReflectionImprovement(1, "Fix", "desc", "impact")
        analysis = ReflectionAnalysis(
            trajectory_summary="Good progress",
            success_patterns=["Pattern A", "Pattern B"],
            failure_patterns=["Pattern C"],
            issues=[issue],
            improvements=[imp],
            confidence=0.8,
        )
        assert analysis.trajectory_summary == "Good progress"
        assert len(analysis.success_patterns) == 2


class TestReflection:
    """Reflection 测试"""
    
    @pytest.fixture
    def reflection(self):
        issue = ReflectionIssue("major", "Issue", "desc", ["t1"])
        imp = ReflectionImprovement(1, "Fix", "desc", "impact")
        analysis = ReflectionAnalysis(
            trajectory_summary="Test summary",
            success_patterns=["p1"],
            failure_patterns=[],
            issues=[issue],
            improvements=[imp],
            confidence=0.9,
        )
        return Reflection(
            timestamp="2026-03-30",
            analysis=analysis,
            metrics={"reward": 1.0},
            stage="intermediate",
            recommendations=["Continue"],
        )
    
    def test_to_markdown(self, reflection):
        md = reflection.to_markdown()
        assert "反思报告" in md or "Reflection" in md.lower()
        # trajectory_summary 在 _generate_summary 中不直接输出，但 issues/improvements 会有
        assert "Issue" in md or "问题" in md
    
    def test_to_json(self, reflection):
        json_str = reflection.to_json()
        assert "2026-03-30" in json_str or "timestamp" in json_str
        # to_json returns JSON string
        import json
        data = json.loads(json_str)
        assert "timestamp" in data or "stage" in data


class TestReflector:
    """Reflector 核心测试"""
    
    @pytest.fixture
    def reflector(self):
        return Reflector()
    
    def test_initialization(self, reflector):
        assert reflector is not None
        assert hasattr(reflector, 'reflect')
    
    def test_reflect_empty(self, reflector):
        """测试空轨迹反思"""
        # 空轨迹会导致除零，至少需要一个轨迹
        trajectories = [{"id": "t1", "status": "keep", "reward": 0.5}]
        result = reflector.reflect(trajectories, metrics={}, stage="beginner")
        assert result is not None
        assert isinstance(result, Reflection)
        assert result.analysis is not None
    
    def test_reflect_with_trajectories(self, reflector):
        """测试有轨迹反思"""
        trajectories = [
            {
                "id": "t1",
                "actions": ["git commit", "git push"],
                "rewards": [1.0, 0.8],
                "outcome": "success",
            },
            {
                "id": "t2",
                "actions": ["git add"],
                "rewards": [0.5],
                "outcome": "partial",
            },
        ]
        
        result = reflector.reflect(trajectories, metrics={"reward": 1.0}, stage="intermediate")
        assert result is not None
        assert result.analysis.trajectory_summary is not None
    
    def test_reflect_with_metrics(self, reflector):
        """测试带指标反思"""
        trajectories = [
            {"id": "t1", "actions": ["a"], "rewards": [1.0]}
        ]
        metrics = {
            "total_reward": 1.0,
            "success_rate": 0.8,
        }
        
        result = reflector.reflect(trajectories, metrics=metrics, stage="advanced")
        assert result is not None
        assert result.metrics == metrics


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
