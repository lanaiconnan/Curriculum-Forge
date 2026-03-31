"""Concrete Expert implementations

Each expert specializes in a specific training area.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from protocols.expert_pool.pool import Expert, ExpertCategory


@dataclass
class BaseExpert(Expert):
    """Base class for all experts with common generation logic"""
    
    def generate_environment(
        self,
        stage: str,
        weak_areas: List[str],
        context: Dict[str, Any] = None,
    ):
        """Generate a training environment for this expert"""
        context = context or {}
        
        return {
            "expert_id": self.id,
            "expert_name": self.name,
            "category": self.category.value,
            "tasks": self._generate_tasks(stage, weak_areas),
            "difficulty": self._get_difficulty(stage),
            "tools": self.required_tools,
            "reward_config": self._get_reward_config(stage),
        }
    
    def _generate_tasks(self, stage: str, weak_areas: List[str]) -> List[Dict]:
        """Override in subclass"""
        return []
    
    def _get_difficulty(self, stage: str) -> float:
        """Get difficulty multiplier"""
        return {"beginner": 0.3, "intermediate": 0.5, "advanced": 0.7}.get(stage, 0.5)
    
    def _get_reward_config(self, stage: str) -> Dict:
        """Get reward configuration"""
        scale = {"beginner": 1.0, "intermediate": 0.7, "advanced": 0.5}.get(stage, 0.7)
        return {
            "r_format_scale": scale,
            "r_correct_scale": scale * 3.0,
            "stage": stage,
        }


class ToolMasteryExpert(BaseExpert):
    """Expert for single-tool proficiency training"""
    
    def __init__(self):
        super().__init__(
            id="expert_tool_mastery",
            name="Tool Mastery Expert",
            category=ExpertCategory.TOOL_MASTERY,
            description="Focuses on mastering individual tool usage",
            target_weak_areas=["tool_selection", "tool_parameters", "tool_usage"],
            required_tools=["git", "moon"],
            skill_level="beginner",
        )
    
    def _generate_tasks(self, stage: str, weak_areas: List[str]) -> List[Dict]:
        tasks = [
            {
                "id": f"{self.id}_task1",
                "type": "tool_practice",
                "description": f"Practice {tool} basic operations",
                "target": f"Successfully use {tool} for common operations",
                "tools_required": [tool],
            }
            for tool in self.required_tools
        ]
        
        if stage == "advanced":
            tasks.append({
                "id": f"{self.id}_task2",
                "type": "tool_chaining",
                "description": "Chain multiple operations with same tool",
                "target": "Efficient tool usage",
                "tools_required": self.required_tools,
            })
        
        return tasks


class ErrorRecoveryExpert(BaseExpert):
    """Expert for error handling and recovery"""
    
    def __init__(self):
        super().__init__(
            id="expert_error_recovery",
            name="Error Recovery Expert",
            category=ExpertCategory.ERROR_RECOVERY,
            description="Teaches error detection and recovery strategies",
            target_weak_areas=["error_handling", "debugging", "failure_recovery"],
            required_tools=["git", "moon"],
            skill_level="intermediate",
        )
    
    def _generate_tasks(self, stage: str, weak_areas: List[str]) -> List[Dict]:
        tasks = [
            {
                "id": f"{self.id}_task1",
                "type": "error_detection",
                "description": "Detect and diagnose errors in tool output",
                "target": "Accurate error identification",
                "tools_required": ["git"],
            },
            {
                "id": f"{self.id}_task2", 
                "type": "recovery_strategy",
                "description": "Implement error recovery strategy",
                "target": "Successful recovery from failures",
                "tools_required": ["git", "moon"],
            },
        ]
        
        if stage == "advanced":
            tasks.append({
                "id": f"{self.id}_task3",
                "type": "prevention",
                "description": "Implement error prevention",
                "target": "Proactive error avoidance",
                "tools_required": self.required_tools,
            })
        
        return tasks


class OptimizationExpert(BaseExpert):
    """Expert for performance optimization"""
    
    def __init__(self):
        super().__init__(
            id="expert_optimization",
            name="Optimization Expert",
            category=ExpertCategory.OPTIMIZATION,
            description="Focuses on performance optimization techniques",
            target_weak_areas=["performance", "efficiency", "resource_usage"],
            required_tools=["moon"],
            skill_level="advanced",
        )
    
    def _generate_tasks(self, stage: str, weak_areas: List[str]) -> List[Dict]:
        tasks = [
            {
                "id": f"{self.id}_task1",
                "type": "profiling",
                "description": "Identify performance bottlenecks",
                "target": "Accurate bottleneck detection",
                "tools_required": ["moon"],
            },
            {
                "id": f"{self.id}_task2",
                "type": "optimization",
                "description": "Optimize identified bottlenecks",
                "target": "Measurable performance improvement",
                "tools_required": ["moon"],
            },
        ]
        
        if stage == "advanced":
            tasks.append({
                "id": f"{self.id}_task3",
                "type": "benchmarking",
                "description": "Create and run benchmarks",
                "target": "Quantified performance metrics",
                "tools_required": ["moon"],
            })
        
        return tasks


class MultiToolExpert(BaseExpert):
    """Expert for multi-tool coordination"""
    
    def __init__(self):
        super().__init__(
            id="expert_multi_tool",
            name="Multi-Tool Expert",
            category=ExpertCategory.MULTI_TOOL,
            description="Teaches coordinating multiple tools in sequence",
            target_weak_areas=["tool_coordination", "workflow_automation", "chaining"],
            required_tools=["git", "moon"],
            skill_level="intermediate",
        )
    
    def _generate_tasks(self, stage: str, weak_areas: List[str]) -> List[Dict]:
        tasks = [
            {
                "id": f"{self.id}_task1",
                "type": "sequential",
                "description": "Use git then moon in sequence",
                "target": "Successful two-tool workflow",
                "tools_required": ["git", "moon"],
            },
            {
                "id": f"{self.id}_task2",
                "type": "parallel",
                "description": "Coordinate parallel tool usage",
                "target": "Efficient parallel execution",
                "tools_required": ["git", "moon"],
            },
        ]
        
        if stage == "advanced":
            tasks.append({
                "id": f"{self.id}_task3",
                "type": "conditional",
                "description": "Conditional tool selection based on output",
                "target": "Adaptive tool orchestration",
                "tools_required": ["git", "moon"],
            })
        
        return tasks


class EdgeCaseExpert(BaseExpert):
    """Expert for edge case handling"""
    
    def __init__(self):
        super().__init__(
            id="expert_edge_case",
            name="Edge Case Expert",
            category=ExpertCategory.EDGE_CASE,
            description="Teaches handling of edge cases and corner scenarios",
            target_weak_areas=["edge_cases", "boundary_conditions", "error_prone_scenarios"],
            required_tools=["git", "moon"],
            skill_level="advanced",
        )
    
    def _generate_tasks(self, stage: str, weak_areas: List[str]) -> List[Dict]:
        tasks = [
            {
                "id": f"{self.id}_task1",
                "type": "boundary",
                "description": "Handle boundary conditions",
                "target": "Correct handling at limits",
                "tools_required": ["git"],
            },
            {
                "id": f"{self.id}_task2",
                "type": "empty_state",
                "description": "Handle empty/null inputs gracefully",
                "target": "Robust empty state handling",
                "tools_required": ["moon"],
            },
        ]
        
        if stage == "advanced":
            tasks.append({
                "id": f"{self.id}_task3",
                "type": "race_condition",
                "description": "Handle race conditions and timing issues",
                "target": "Correct concurrent behavior",
                "tools_required": ["git", "moon"],
            })
        
        return tasks


class CodeReviewExpert(BaseExpert):
    """Expert for code review and quality"""
    
    def __init__(self):
        super().__init__(
            id="expert_code_review",
            name="Code Review Expert",
            category=ExpertCategory.CODE_REVIEW,
            description="Focuses on code quality and review skills",
            target_weak_areas=["code_quality", "review_skills", "best_practices"],
            required_tools=["git"],
            skill_level="intermediate",
        )
    
    def _generate_tasks(self, stage: str, weak_areas: List[str]) -> List[Dict]:
        tasks = [
            {
                "id": f"{self.id}_task1",
                "type": "review",
                "description": "Review code for issues",
                "target": "Identify problems accurately",
                "tools_required": ["git"],
            },
            {
                "id": f"{self.id}_task2",
                "type": "suggestions",
                "description": "Provide improvement suggestions",
                "target": "Actionable feedback",
                "tools_required": ["git"],
            },
        ]
        
        if stage == "advanced":
            tasks.append({
                "id": f"{self.id}_task3",
                "type": "refactoring",
                "description": "Suggest and apply refactoring",
                "target": "Improved code structure",
                "tools_required": ["git"],
            })
        
        return tasks
