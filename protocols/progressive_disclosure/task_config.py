"""Task Configuration - Combined difficulty + disclosure settings

TaskConfig represents the complete configuration for a task,
combining difficulty settings with context disclosure decisions.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import json


@dataclass
class TaskConfig:
    """Complete task configuration
    
    Combines difficulty dimensions with context disclosure
    to produce a complete task specification.
    """
    # Task identity
    task_id: str
    description: str
    
    # Difficulty settings
    complexity: float = 0.3
    constraints: float = 0.3
    context: float = 0.3
    tools: float = 0.3
    scope: float = 0.3
    
    # Derived from difficulty
    difficulty: float = 0.3  # Overall difficulty
    
    # Context disclosure
    hints: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    documentation: List[str] = field(default_factory=list)
    scaffold: List[str] = field(default_factory=list)
    
    # Tool constraints
    allowed_tools: List[str] = field(default_factory=list)
    max_tool_calls: int = 10
    
    # Time constraints
    time_budget: int = 300  # seconds
    
    # Objectives and requirements
    objectives: List[str] = field(default_factory=list)
    requirements: List[str] = field(default_factory=list)
    
    # Metadata
    expert_id: Optional[str] = None
    stage: str = "intermediate"
    round_num: int = 1
    
    def compute_overall_difficulty(self) -> float:
        """Compute overall difficulty from dimensions"""
        weights = {
            "complexity": 0.30,
            "constraints": 0.20,
            "context": 0.20,
            "tools": 0.15,
            "scope": 0.15,
        }
        self.difficulty = (
            self.complexity * weights["complexity"] +
            self.constraints * weights["constraints"] +
            self.context * weights["context"] +
            self.tools * weights["tools"] +
            self.scope * weights["scope"]
        )
        return self.difficulty
    
    def derive_constraints(self):
        """Derive time and tool constraints from difficulty"""
        # Time budget: lower difficulty = more time
        base_time = 300
        time_range = 300  # Can vary by ±5 min
        self.time_budget = int(base_time + time_range * (1 - self.constraints))
        self.time_budget = max(60, min(600, self.time_budget))  # 1-10 min
        
        # Tool calls: lower difficulty = more allowed
        base_calls = 10
        call_range = 10
        self.max_tool_calls = int(base_calls + call_range * (1 - self.tools))
        self.max_tool_calls = max(5, min(25, self.max_tool_calls))
    
    def to_prompt(self) -> str:
        """Generate task prompt for learner"""
        lines = [
            f"## Task: {self.description}",
            f"",
            f"### Difficulty: {self.difficulty:.2f} ({self.stage})",
            f"",
        ]
        
        if self.objectives:
            lines.append("### Objectives")
            for obj in self.objectives:
                lines.append(f"- {obj}")
            lines.append("")
        
        if self.requirements:
            lines.append("### Requirements")
            for req in self.requirements:
                lines.append(f"- {req}")
            lines.append("")
        
        if self.hints:
            lines.append("### Hints")
            for hint in self.hints:
                lines.append(f"- {hint}")
            lines.append("")
        
        if self.examples:
            lines.append("### Examples")
            for ex in self.examples:
                lines.append(f"- {ex}")
            lines.append("")
        
        lines.extend([
            "### Constraints",
            f"- Time budget: {self.time_budget}s",
            f"- Max tool calls: {self.max_tool_calls}",
            f"- Allowed tools: {', '.join(self.allowed_tools) or 'any'}",
        ])
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "task_id": self.task_id,
            "description": self.description,
            "complexity": self.complexity,
            "constraints": self.constraints,
            "context": self.context,
            "tools": self.tools,
            "scope": self.scope,
            "difficulty": self.difficulty,
            "hints": self.hints,
            "examples": self.examples,
            "documentation": self.documentation,
            "scaffold": self.scaffold,
            "allowed_tools": self.allowed_tools,
            "max_tool_calls": self.max_tool_calls,
            "time_budget": self.time_budget,
            "objectives": self.objectives,
            "requirements": self.requirements,
            "expert_id": self.expert_id,
            "stage": self.stage,
            "round_num": self.round_num,
        }
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2)


class TaskConfigBuilder:
    """
    Builder for TaskConfig
    
    Provides fluent API for constructing task configurations
    from difficulty and disclosure settings.
    """
    
    def __init__(self):
        self._task_id = f"task-{id(self)}"
        self._description = "Task"
        self._complexity = 0.3
        self._constraints = 0.3
        self._context = 0.3
        self._tools = 0.3
        self._scope = 0.3
        self._hints = []
        self._examples = []
        self._documentation = []
        self._scaffold = []
        self._allowed_tools = ["git", "moon"]
        self._objectives = []
        self._requirements = []
        self._expert_id = None
        self._stage = "intermediate"
        self._round_num = 1
    
    def task_id(self, task_id: str) -> "TaskConfigBuilder":
        self._task_id = task_id
        return self
    
    def description(self, desc: str) -> "TaskConfigBuilder":
        self._description = desc
        return self
    
    def difficulty(self, dims: Dict[str, float]) -> "TaskConfigBuilder":
        """Set difficulty dimensions"""
        self._complexity = dims.get("complexity", self._complexity)
        self._constraints = dims.get("constraints", self._constraints)
        self._context = dims.get("context", self._context)
        self._tools = dims.get("tools", self._tools)
        self._scope = dims.get("scope", self._scope)
        return self
    
    def difficulty_overall(self, value: float) -> "TaskConfigBuilder":
        """Set all dimensions to same value"""
        self._complexity = value
        self._constraints = value
        self._context = value
        self._tools = value
        self._scope = value
        return self
    
    def hints(self, hints: List[str]) -> "TaskConfigBuilder":
        self._hints = hints
        return self
    
    def examples(self, examples: List[str]) -> "TaskConfigBuilder":
        self._examples = examples
        return self
    
    def scaffold(self, scaffold: List[str]) -> "TaskConfigBuilder":
        self._scaffold = scaffold
        return self
    
    def tools(self, tools: List[str]) -> "TaskConfigBuilder":
        self._allowed_tools = tools
        return self
    
    def objectives(self, objectives: List[str]) -> "TaskConfigBuilder":
        self._objectives = objectives
        return self
    
    def requirements(self, requirements: List[str]) -> "TaskConfigBuilder":
        self._requirements = requirements
        return self
    
    def expert(self, expert_id: str) -> "TaskConfigBuilder":
        self._expert_id = expert_id
        return self
    
    def stage(self, stage: str) -> "TaskConfigBuilder":
        self._stage = stage
        return self
    
    def round(self, round_num: int) -> "TaskConfigBuilder":
        self._round_num = round_num
        return self
    
    def from_disclosure(self, disclosure: Dict[str, List[str]]) -> "TaskConfigBuilder":
        """Apply disclosure results"""
        self._hints = disclosure.get("hints", self._hints)
        self._examples = disclosure.get("examples", self._examples)
        self._documentation = disclosure.get("documentation", self._documentation)
        self._scaffold = disclosure.get("scaffold", self._scaffold)
        return self
    
    def build(self) -> TaskConfig:
        """Build the TaskConfig"""
        config = TaskConfig(
            task_id=self._task_id,
            description=self._description,
            complexity=self._complexity,
            constraints=self._constraints,
            context=self._context,
            tools=self._tools,
            scope=self._scope,
            hints=self._hints,
            examples=self._examples,
            documentation=self._documentation,
            scaffold=self._scaffold,
            allowed_tools=self._allowed_tools,
            objectives=self._objectives,
            requirements=self._requirements,
            expert_id=self._expert_id,
            stage=self._stage,
            round_num=self._round_num,
        )
        
        # Compute derived values
        config.compute_overall_difficulty()
        config.derive_constraints()
        
        return config
