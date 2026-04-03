"""Domain Models for Curriculum-Forge Services

This module defines the core data structures used across all services.
Based on the dataclass-first approach from claude-code's models.py.

Usage:
    from services.models import TrainingEnvironment, ExperimentResult
    
    env = TrainingEnvironment(
        name="Beginner Env",
        difficulty=0.3,
        tasks=[...],
    )
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum
from datetime import datetime


class LearningStage(Enum):
    """Learning stage levels"""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class ExperimentStatus(Enum):
    """Experiment result status"""
    KEEP = "keep"
    DISCARD = "discard"
    RUNNING = "running"
    FAILED = "failed"


@dataclass
class TaskConfig:
    """Configuration for a single training task"""
    id: str
    type: str
    description: str
    target: str
    tools_required: List[str] = field(default_factory=list)
    hints: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    max_duration: int = 300  # seconds
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "description": self.description,
            "target": self.target,
            "tools_required": self.tools_required,
            "hints": self.hints,
            "examples": self.examples,
            "max_duration": self.max_duration,
        }


@dataclass
class TrainingEnvironment:
    """
    Training environment configuration.
    
    This is the core data structure that Agent A generates
    and Agent B uses to run experiments.
    """
    id: str
    name: str
    description: str
    stage: LearningStage
    difficulty: float  # 0.0 - 1.0
    tasks: List[TaskConfig] = field(default_factory=list)
    available_tools: List[str] = field(default_factory=list)
    tool_constraints: Dict[str, Any] = field(default_factory=dict)
    reward_config: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    @property
    def task_count(self) -> int:
        return len(self.tasks)
    
    @property
    def difficulty_level(self) -> str:
        if self.difficulty < 0.3:
            return "easy"
        elif self.difficulty < 0.6:
            return "medium"
        else:
            return "hard"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "stage": self.stage.value,
            "difficulty": self.difficulty,
            "difficulty_level": self.difficulty_level,
            "tasks": [t.to_dict() for t in self.tasks],
            "available_tools": self.available_tools,
            "tool_constraints": self.tool_constraints,
            "reward_config": self.reward_config,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class ExperimentRecord:
    """
    Record of a single experiment run.
    
    This is what gets stored in results.tsv.
    """
    commit: str
    timestamp: datetime
    bpb_score: float  # bits per byte score
    memory_mb: int
    status: ExperimentStatus
    description: str
    stage: LearningStage = LearningStage.BEGINNER
    reward: float = 0.0
    duration: float = 0.0
    tools_used: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_keep(self) -> bool:
        return self.status == ExperimentStatus.KEEP
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "commit": self.commit,
            "timestamp": self.timestamp.isoformat(),
            "bpb_score": self.bpb_score,
            "memory_mb": self.memory_mb,
            "status": self.status.value,
            "description": self.description,
            "stage": self.stage.value,
            "reward": self.reward,
            "duration": self.duration,
            "tools_used": self.tools_used,
            "metadata": self.metadata,
        }
    
    def to_tsv(self) -> str:
        """Format as TSV row for results.tsv"""
        return f"{self.commit}\t{self.timestamp.isoformat()}\t{self.bpb_score}\t{self.memory_mb}\t{self.status.value}\t{self.description}"


@dataclass 
class ProgressMetrics:
    """
    Aggregated progress metrics.
    
    Calculated from ExperimentRecord history.
    """
    total_experiments: int = 0
    keep_count: int = 0
    discard_count: int = 0
    keep_rate: float = 0.0
    avg_reward: float = 0.0
    total_reward: float = 0.0
    best_score: float = 0.0
    avg_duration: float = 0.0
    current_stage: LearningStage = LearningStage.BEGINNER
    weak_areas: List[str] = field(default_factory=list)
    strong_areas: List[str] = field(default_factory=list)
    
    @classmethod
    def from_records(cls, records: List[ExperimentRecord]) -> 'ProgressMetrics':
        """Calculate metrics from a list of experiment records"""
        if not records:
            return cls()
        
        keep_records = [r for r in records if r.is_keep]
        
        total = len(records)
        keep = len(keep_records)
        
        return cls(
            total_experiments=total,
            keep_count=keep,
            discard_count=total - keep,
            keep_rate=keep / total if total > 0 else 0.0,
            avg_reward=sum(r.reward for r in records) / total if total > 0 else 0.0,
            total_reward=sum(r.reward for r in records),
            best_score=max(r.bpb_score for r in records) if records else 0.0,
            avg_duration=sum(r.duration for r in records) / total if total > 0 else 0.0,
            current_stage=_infer_stage(keep / total if total > 0 else 0.0),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_experiments": self.total_experiments,
            "keep_count": self.keep_count,
            "discard_count": self.discard_count,
            "keep_rate": self.keep_rate,
            "avg_reward": self.avg_reward,
            "total_reward": self.total_reward,
            "best_score": self.best_score,
            "avg_duration": self.avg_duration,
            "current_stage": self.current_stage.value,
            "weak_areas": self.weak_areas,
            "strong_areas": self.strong_areas,
        }


def _infer_stage(keep_rate: float) -> LearningStage:
    """Infer learning stage from keep rate"""
    if keep_rate < 0.3:
        return LearningStage.BEGINNER
    elif keep_rate < 0.6:
        return LearningStage.INTERMEDIATE
    else:
        return LearningStage.ADVANCED


@dataclass
class RewardBreakdown:
    """
    Detailed breakdown of reward calculation.
    
    From the ToolRL paper's fine-grained reward design.
    """
    rformat: float = 0.0      # Format correctness: {0, 1}
    rname: float = 0.0        # Tool name match: [-1, 1]
    rparam: float = 0.0       # Parameter name match: [-1, 1]
    rvalue: float = 0.0       # Parameter value match: [-1, 1]
    rcorrect: float = 0.0      # Total correctness: [-3, 3]
    rfinal: float = 0.0      # Final reward
    
    def __post_init__(self):
        self.rcorrect = self.rname + self.rparam + self.rvalue
        self.rfinal = self.rformat + self.rcorrect
    
    @property
    def is_valid(self) -> bool:
        return self.rformat in (0.0, 1.0) and -3.0 <= self.rcorrect <= 3.0
    
    def to_dict(self) -> Dict[str, float]:
        return {
            "rformat": self.rformat,
            "rname": self.rname,
            "rparam": self.rparam,
            "rvalue": self.rvalue,
            "rcorrect": self.rcorrect,
            "rfinal": self.rfinal,
        }


@dataclass
class ServiceHealth:
    """Health status of a service"""
    name: str
    status: str  # "healthy", "degraded", "down"
    uptime: float
    error_rate: float
    last_error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
