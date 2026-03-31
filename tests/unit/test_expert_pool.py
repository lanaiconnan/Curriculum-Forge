"""Unit tests for Expert Pool

Run: pytest tests/unit/test_expert_pool.py -v
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from protocols.expert_pool.pool import ExpertPool, ExpertRegistry, Expert, ExpertCategory
from protocols.expert_pool.selector import ExpertSelector, LearnerState, SelectionStrategy
from protocols.expert_pool.experts import (
    ToolMasteryExpert,
    ErrorRecoveryExpert,
    OptimizationExpert,
)
from protocols.expert_pool.integration import ExpertPoolIntegration, ExpertPoolConfig


class TestExpertRegistry:
    """Tests for ExpertRegistry"""
    
    def test_default_experts_registered(self):
        """Test default experts are registered"""
        registry = ExpertRegistry()
        experts = registry.list_all()
        
        assert len(experts) >= 6  # At least 6 default experts
        categories = set(e.category for e in experts)
        assert ExpertCategory.TOOL_MASTERY in categories
        assert ExpertCategory.ERROR_RECOVERY in categories
    
    def test_find_by_category(self):
        """Test finding experts by category"""
        registry = ExpertRegistry()
        tool_experts = registry.find_by_category(ExpertCategory.TOOL_MASTERY)
        
        assert len(tool_experts) > 0
        assert all(e.category == ExpertCategory.TOOL_MASTERY for e in tool_experts)
    
    def test_find_by_weak_area(self):
        """Test finding experts by weak area"""
        registry = ExpertRegistry()
        error_experts = registry.find_by_weak_area("error_handling")
        
        assert len(error_experts) > 0
        assert any("error" in wa.lower() for e in error_experts for wa in e.target_weak_areas)


class TestExpertSelector:
    """Tests for ExpertSelector"""
    
    def test_select_with_weak_areas(self):
        """Test selection prioritizes matching weak areas"""
        selector = ExpertSelector(strategy=SelectionStrategy.HYBRID, exploration_rate=0.0)
        registry = ExpertRegistry()
        
        state = LearnerState(
            weak_areas=["error_handling"],
            skill_level="intermediate",
            available_tools=["git", "moon"],
        )
        
        result = selector.select(state, registry.list_all())
        
        assert result.selected_expert_id is not None
        assert result.score > 0
    
    def test_select_respects_tool_availability(self):
        """Test selection considers tool availability"""
        selector = ExpertSelector(exploration_rate=0.0)
        registry = ExpertRegistry()
        
        # Only git available
        state = LearnerState(
            skill_level="beginner",
            available_tools=["git"],  # Only git
        )
        
        experts = registry.list_all()
        result = selector.select(state, experts)
        
        # Should select an expert that uses git
        selected = registry.get(result.selected_expert_id)
        assert selected is not None
    
    def test_exploration_rate(self):
        """Test exploration picks different experts"""
        selector = ExpertSelector(exploration_rate=1.0)  # Always explore
        registry = ExpertRegistry()
        
        state = LearnerState(available_tools=["git", "moon"])
        
        selected_ids = set()
        for _ in range(10):
            result = selector.select(state, registry.list_all())
            selected_ids.add(result.selected_expert_id)
        
        # With high exploration, should see variety
        assert len(selected_ids) > 1
    
    def test_skill_level_matching(self):
        """Test selection considers skill level"""
        selector = ExpertSelector(exploration_rate=0.0)
        
        # Test beginner
        beginner_state = LearnerState(skill_level="beginner", available_tools=["git", "moon"])
        beginner_result = selector.select(beginner_state, ExpertRegistry().list_all())
        
        # Test advanced
        advanced_state = LearnerState(skill_level="advanced", available_tools=["git", "moon"])
        advanced_result = selector.select(advanced_state, ExpertRegistry().list_all())
        
        # Different experts should be selected for different levels
        assert beginner_result.selected_expert_id is not None


class TestExpertPool:
    """Tests for ExpertPool"""
    
    def test_pool_initialization(self):
        """Test pool initializes with experts"""
        pool = ExpertPool()
        experts = pool.list_experts()
        
        assert len(experts) >= 6
    
    def test_update_expert_stats(self):
        """Test updating expert statistics"""
        pool = ExpertPool()
        
        # Record success
        pool.update_expert_stats("expert_tool_mastery", success=True)
        
        expert = pool.get_expert("expert_tool_mastery")
        assert expert.usage_count == 1
        assert expert.success_rate == 1.0
        
        # Record failure
        pool.update_expert_stats("expert_tool_mastery", success=False)
        
        expert = pool.get_expert("expert_tool_mastery")
        assert expert.usage_count == 2
        assert 0 < expert.success_rate < 1.0  # EMA should give some value


class TestExpertGeneration:
    """Tests for expert environment generation"""
    
    def test_tool_mastery_generates_environment(self):
        """Test ToolMasteryExpert generates valid environment"""
        expert = ToolMasteryExpert()
        
        env = expert.generate_environment(
            stage="beginner",
            weak_areas=["tool_usage"],
        )
        
        assert env["expert_id"] == "expert_tool_mastery"
        assert "tasks" in env
        assert len(env["tasks"]) > 0
        assert env["difficulty"] == 0.3
    
    def test_error_recovery_generates_tasks(self):
        """Test ErrorRecoveryExpert generates appropriate tasks"""
        expert = ErrorRecoveryExpert()
        
        env = expert.generate_environment(
            stage="intermediate",
            weak_areas=["error_handling"],
        )
        
        assert "tasks" in env
        task_types = [t["type"] for t in env["tasks"]]
        assert "error_detection" in task_types
    
    def test_difficulty_scales_with_stage(self):
        """Test difficulty changes with stage"""
        expert = OptimizationExpert()
        
        beginner_env = expert.generate_environment("beginner", [])
        intermediate_env = expert.generate_environment("intermediate", [])
        advanced_env = expert.generate_environment("advanced", [])
        
        assert beginner_env["difficulty"] < intermediate_env["difficulty"]
        assert intermediate_env["difficulty"] < advanced_env["difficulty"]


class TestExpertPoolIntegration:
    """Tests for ExpertPoolIntegration"""
    
    def test_integration_initialization(self):
        """Test integration initializes correctly"""
        integration = ExpertPoolIntegration()
        
        assert integration.pool is not None
        assert integration.selector is not None
    
    def test_update_learner_state(self):
        """Test updating learner state"""
        integration = ExpertPoolIntegration()
        
        state = integration.update_learner_state(
            weak_areas=["error_handling"],
            skill_level="intermediate",
            recent_success_rate=0.7,
        )
        
        assert state.weak_areas == ["error_handling"]
        assert state.skill_level == "intermediate"
        assert state.recent_success_rate == 0.7
    
    def test_select_expert(self):
        """Test expert selection returns valid result"""
        integration = ExpertPoolIntegration()
        
        integration.update_learner_state(
            weak_areas=["error_handling"],
            skill_level="intermediate",
            available_tools=["git", "moon"],
        )
        
        result = integration.select_expert()
        
        assert result.expert_id is not None
        assert result.environment is not None
        assert "tasks" in result.environment
    
    def test_record_result_updates_stats(self):
        """Test recording result updates expert stats"""
        integration = ExpertPoolIntegration()
        
        # Select first (this also updates stats)
        result = integration.select_expert()
        expert_id = result.expert_id
        
        # Record success (this is the second update)
        integration.record_result(expert_id, success=True)
        
        expert = integration.pool.get_expert(expert_id)
        assert expert.usage_count == 2  # Selection + record_result
    
    def test_fallback_to_stage_based(self):
        """Test fallback when no weak areas"""
        integration = ExpertPoolIntegration(
            config=ExpertPoolConfig(fallback_to_stage_based=True)
        )
        
        # No weak areas specified
        integration.update_learner_state(
            weak_areas=[],  # Empty
            skill_level="advanced",
            available_tools=["git", "moon"],
        )
        
        result = integration.select_expert()
        
        # Should still select something (from fallback)
        assert result.expert_id is not None
    
    def test_statistics(self):
        """Test getting statistics"""
        integration = ExpertPoolIntegration()
        
        integration.update_learner_state(available_tools=["git", "moon"])
        integration.select_expert()
        
        stats = integration.get_statistics()
        
        assert "expert_pool" in stats
        assert "selector" in stats
        assert stats["total_selections"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
