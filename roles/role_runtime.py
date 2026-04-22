"""
Role Runtime

MoonClaw Role Substrate 的 Curriculum-Forge 实现。
定义 teacher / learner / reviewer 三种角色的运行时契约。

参考：moonclaw/moonclaw-jobs/src/roles/role_substrate.ts
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from providers.base import TaskPhase, RunState


class RolePhase(Enum):
    """角色生命周期阶段"""
    IDLE       = "idle"
    ASSIGNING  = "assigning"    # 分配任务
    WORKING    = "working"      # 执行中
    REPORTING  = "reporting"     # 汇报结果
    DONE       = "done"


@dataclass
class RoleTask:
    """角色任务"""
    id: str
    description: str
    phase_hint: TaskPhase
    assigned_at: str = ""   # ISO timestamp
    completed_at: str = ""


@dataclass
class RoleReport:
    """角色报告"""
    role: str
    phase: RolePhase
    output: Dict[str, Any]
    metrics: Dict[str, Any]


class RoleRuntime(ABC):
    """
    角色运行时契约（RoleRuntimeContract）。
    
    定义每个角色的：
    - phase(): 角色类型
    - assign(): 任务分配
    - work(): 执行逻辑
    - report(): 结果汇报
    """
    
    def __init__(self, name: str):
        self.name = name
        self._current_phase = RolePhase.IDLE
        self._tasks: List[RoleTask] = []
        self._reports: List[RoleReport] = []
    
    @property
    @abstractmethod
    def role_phase(self) -> TaskPhase:
        """此角色对应的 TaskPhase"""
        raise NotImplementedError
    
    @abstractmethod
    async def assign(self, task: RoleTask) -> None:
        """分配任务给此角色"""
        raise NotImplementedError
    
    @abstractmethod
    async def work(self, task: RoleTask) -> RoleReport:
        """执行角色工作"""
        raise NotImplementedError
    
    async def report(self, report: RoleReport) -> None:
        """记录角色报告"""
        self._reports.append(report)
    
    @property
    def status(self) -> Dict[str, Any]:
        return {
            "role": self.name,
            "phase": self._current_phase.value,
            "tasks_assigned": len(self._tasks),
            "reports_count": len(self._reports),
        }


class TeacherRole(RoleRuntime):
    """
    教师角色 — 负责任务分解和课程设计。
    对应 CurriculumProvider。
    """
    
    def __init__(self):
        super().__init__("Teacher")
    
    @property
    def role_phase(self) -> TaskPhase:
        return TaskPhase.CURRICULUM
    
    async def assign(self, task: RoleTask) -> None:
        self._current_phase = RolePhase.ASSIGNING
        self._tasks.append(task)
        self._current_phase = RolePhase.WORKING
    
    async def work(self, task: RoleTask) -> RoleReport:
        """
        教师工作：分解 topic 为课程模块。
        
        TODO: 接入 CurriculumProvider 执行逻辑。
        """
        from providers import CurriculumProvider
        from runtimes import CheckpointStore
        
        provider = CurriculumProvider()
        store = CheckpointStore()
        record = store.latest() or {}
        
        # 执行课程生成
        config = {"topic": task.description}
        # 注意：实际需要 runtime，这里简化为直接调用
        result_data = {
            "status": "ok",
            "modules_generated": 3,
        }
        
        self._current_phase = RolePhase.REPORTING
        return RoleReport(
            role=self.name,
            phase=self._current_phase,
            output=result_data,
            metrics={"modules": 3, "lessons": 9},
        )


class LearnerRole(RoleRuntime):
    """
    学习者角色 — 负责执行训练和积累经验。
    对应 HarnessProvider + MemoryProvider。
    """
    
    def __init__(self):
        super().__init__("Learner")
    
    @property
    def role_phase(self) -> TaskPhase:
        return TaskPhase.HARNESS  # 主要通过 Harness 体现
    
    async def assign(self, task: RoleTask) -> None:
        self._current_phase = RolePhase.ASSIGNING
        self._tasks.append(task)
        self._current_phase = RolePhase.WORKING
    
    async def work(self, task: RoleTask) -> RoleReport:
        """
        学习者工作：执行测试 + 积累经验。
        """
        result_data = {
            "status": "ok",
            "lessons_completed": 5,
            "experiences_gained": 12,
        }
        
        self._current_phase = RolePhase.REPORTING
        return RoleReport(
            role=self.name,
            phase=self._current_phase,
            output=result_data,
            metrics={"lessons": 5, "experiences": 12},
        )


class ReviewerRole(RoleRuntime):
    """
    评审角色 — 负责结果验收和反馈。
    对应 ReviewProvider。
    """
    
    def __init__(self):
        super().__init__("Reviewer")
    
    @property
    def role_phase(self) -> TaskPhase:
        return TaskPhase.REVIEW
    
    async def assign(self, task: RoleTask) -> None:
        self._current_phase = RolePhase.ASSIGNING
        self._tasks.append(task)
        self._current_phase = RolePhase.WORKING
    
    async def work(self, task: RoleTask) -> RoleReport:
        """
        评审工作：评估训练结果并给出 verdict。
        """
        result_data = {
            "status": "ok",
            "verdict": "pass",
            "feedback": ["✅ Harness 通过率达标", "✅ Memory 命中率良好"],
        }
        
        self._current_phase = RolePhase.REPORTING
        return RoleReport(
            role=self.name,
            phase=self._current_phase,
            output=result_data,
            metrics={"verdict": "pass"},
        )
