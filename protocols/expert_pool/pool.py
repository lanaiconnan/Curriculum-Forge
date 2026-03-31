"""Expert Pool - Registry of specialized training experts

Each Expert is a specialized training scenario that targets specific skills.
The pool manages expert registration and provides access to available experts.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from enum import Enum


class ExpertCategory(Enum):
    """Categories of training experts"""
    TOOL_MASTERY = "tool_mastery"       # Single tool proficiency
    ERROR_RECOVERY = "error_recovery"   # Error handling & recovery
    OPTIMIZATION = "optimization"        # Performance optimization
    MULTI_TOOL = "multi_tool"           # Combining multiple tools
    EDGE_CASE = "edge_case"             # Handling edge cases
    CODE_REVIEW = "code_review"         # Code review & quality


@dataclass
class Expert:
    """A specialized training expert
    
    Each expert focuses on a specific skill area and generates
    targeted training environments.
    """
    id: str
    name: str
    category: ExpertCategory
    description: str
    
    # What weak areas this expert targets
    target_weak_areas: List[str]
    
    # Required tools for this expert's scenarios
    required_tools: List[str]
    
    # Skill level: beginner/intermediate/advanced
    skill_level: str
    
    # Generation function: (stage, weak_areas, context) -> TrainingEnvironment
    generate_fn: Callable = None
    
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    usage_count: int = 0
    success_rate: float = 0.0
    
    def __post_init__(self):
        # Ensure category is enum
        if isinstance(self.category, str):
            self.category = ExpertCategory(self.category)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category.value,
            "description": self.description,
            "target_weak_areas": self.target_weak_areas,
            "required_tools": self.required_tools,
            "skill_level": self.skill_level,
            "usage_count": self.usage_count,
            "success_rate": self.success_rate,
        }


class ExpertRegistry:
    """Registry of available training experts
    
    Manages the collection of experts and provides lookup by category,
    weak area, or tool requirements.
    """
    
    def __init__(self):
        self.experts: Dict[str, Expert] = {}
        self._register_default_experts()
    
    def _register_default_experts(self):
        """Register default set of experts"""
        from .experts import (
            ToolMasteryExpert,
            ErrorRecoveryExpert,
            OptimizationExpert,
            MultiToolExpert,
            EdgeCaseExpert,
            CodeReviewExpert,
        )
        
        # Create and register each expert type
        default_experts = [
            ToolMasteryExpert(),
            ErrorRecoveryExpert(),
            OptimizationExpert(),
            MultiToolExpert(),
            EdgeCaseExpert(),
            CodeReviewExpert(),
        ]
        
        for expert in default_experts:
            self.register(expert)
    
    def register(self, expert: Expert):
        """Register an expert"""
        self.experts[expert.id] = expert
    
    def unregister(self, expert_id: str):
        """Unregister an expert"""
        if expert_id in self.experts:
            del self.experts[expert_id]
    
    def get(self, expert_id: str) -> Optional[Expert]:
        """Get expert by ID"""
        return self.experts.get(expert_id)
    
    def list_all(self) -> List[Expert]:
        """List all registered experts"""
        return list(self.experts.values())
    
    def find_by_category(self, category: ExpertCategory) -> List[Expert]:
        """Find experts by category"""
        return [e for e in self.experts.values() if e.category == category]
    
    def find_by_weak_area(self, weak_area: str) -> List[Expert]:
        """Find experts that target a specific weak area"""
        return [
            e for e in self.experts.values() 
            if weak_area.lower() in [wa.lower() for wa in e.target_weak_areas]
        ]
    
    def find_by_tool(self, tool: str) -> List[Expert]:
        """Find experts that use a specific tool"""
        return [e for e in self.experts.values() if tool in e.required_tools]
    
    def find_by_skill_level(self, level: str) -> List[Expert]:
        """Find experts at a specific skill level"""
        return [e for e in self.experts.values() if e.skill_level == level]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get registry statistics"""
        categories = {}
        total_usage = 0
        total_success = 0
        success_count = 0
        
        for expert in self.experts.values():
            categories[expert.category.value] = categories.get(expert.category.value, 0) + 1
            total_usage += expert.usage_count
            if expert.usage_count > 0:
                total_success += expert.success_rate * expert.usage_count
                success_count += expert.usage_count
        
        return {
            "total_experts": len(self.experts),
            "by_category": categories,
            "total_usage": total_usage,
            "average_success_rate": total_success / success_count if success_count > 0 else 0.0,
        }


class ExpertPool:
    """Expert Pool - Main interface for expert selection and execution
    
    High-level API that combines registry with selection logic.
    """
    
    def __init__(self, registry: ExpertRegistry = None):
        self.registry = registry or ExpertRegistry()
    
    def get_expert(self, expert_id: str) -> Optional[Expert]:
        """Get an expert by ID"""
        return self.registry.get(expert_id)
    
    def list_experts(self) -> List[Expert]:
        """List all available experts"""
        return self.registry.list_all()
    
    def update_expert_stats(self, expert_id: str, success: bool):
        """Update expert usage statistics"""
        expert = self.registry.get(expert_id)
        if expert:
            expert.usage_count += 1
            # Update success rate with exponential moving average
            if expert.usage_count == 1:
                expert.success_rate = 1.0 if success else 0.0
            else:
                alpha = 0.1  # EMA weight
                expert.success_rate = (
                    alpha * (1.0 if success else 0.0) + 
                    (1 - alpha) * expert.success_rate
                )
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get pool statistics"""
        return self.registry.get_statistics()
