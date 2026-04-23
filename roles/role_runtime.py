"""
Role Runtime

MoonClaw Role Substrate 的 Curriculum-Forge 实现。
定义 teacher / learner / reviewer 三种角色的运行时契约。

Phase 2 改造：角色接入真实 Provider，通过 service_container 执行。

参考：moonclaw/moonclaw-jobs/src/roles/role_substrate.ts
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from providers.base import TaskPhase, RunState, TaskOutput


class RolePhase(Enum):
    """角色生命周期阶段"""
    IDLE       = "idle"
    ASSIGNING  = "assigning"    # 分配任务
    WORKING    = "working"      # 执行中
    REPORTING  = "reporting"    # 汇报结果
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
    - role_phase(): 角色对应的 TaskPhase
    - assign(): 任务分配
    - work(): 执行逻辑（接入 Provider）
    - report(): 结果汇报
    - to_agent_info(): 转换为 Coordinator 的 AgentInfo
    
    Phase 2 新增：
    - provider: 绑定对应的 TaskProvider
    - service_container: 访问 services/ 层
    - work() 调用真实 Provider.execute()
    """
    
    def __init__(
        self,
        name: str,
        provider: Any = None,
        service_container: Any = None,
    ):
        self.name = name
        self.provider = provider  # Bound TaskProvider
        self.service_container = service_container  # ServiceContainer for DI
        self._current_phase = RolePhase.IDLE
        self._tasks: List[RoleTask] = []
        self._reports: List[RoleReport] = []
        self._last_output: Optional[TaskOutput] = None
    
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
        """执行角色工作（调用 Provider）"""
        raise NotImplementedError
    
    async def report(self, report: RoleReport) -> None:
        """记录角色报告"""
        self._reports.append(report)
    
    @property
    def last_output(self) -> Optional[TaskOutput]:
        """最近一次 Provider 执行的输出"""
        return self._last_output
    
    @property
    def status(self) -> Dict[str, Any]:
        return {
            "role": self.name,
            "phase": self._current_phase.value,
            "tasks_assigned": len(self._tasks),
            "reports_count": len(self._reports),
            "has_provider": self.provider is not None,
            "has_service_container": self.service_container is not None,
        }


class TeacherRole(RoleRuntime):
    """
    教师角色 — 负责任务分解和课程设计。
    对应 CurriculumProvider。
    """
    
    def __init__(
        self,
        provider: Any = None,
        service_container: Any = None,
    ):
        super().__init__(
            name="Teacher",
            provider=provider,
            service_container=service_container,
        )
    
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
        
        Phase 2: 调用 CurriculumProvider.execute() 获取真实结果。
        若 provider 未绑定，返回降级结果。
        """
        if self.provider is not None:
            from runtimes.adaptive_runtime import AdaptiveRuntime, PipelineConfig
            from runtimes.checkpoint_store import CheckpointStore
            
            # Build a minimal runtime for provider execution
            store = CheckpointStore()
            config = PipelineConfig(
                profile="teacher",
                providers=[self.provider],
                auto_save=False,
            )
            runtime = AdaptiveRuntime(
                config=config,
                checkpoint_store=store,
                service_container=self.service_container,
            )
            
            run_config = {"topic": task.description}
            output = await self.provider.execute(run_config, runtime)
            self._last_output = output
            
            result_data = output.to_dict()
            metrics = {
                "ok": output.ok,
                "phase": output.phase.value,
            }
        else:
            # Degraded: no provider bound
            result_data = {
                "status": "ok",
                "modules_generated": 0,
                "note": "No provider bound — degraded mode",
            }
            metrics = {"ok": True, "degraded": True}
        
        self._current_phase = RolePhase.REPORTING
        return RoleReport(
            role=self.name,
            phase=self._current_phase,
            output=result_data,
            metrics=metrics,
        )
    
    def to_agent_info(self) -> Any:
        """转换为 Coordinator 的 AgentInfo"""
        from services.coordinator import AgentInfo, AgentRole
        return AgentInfo(
            id="teacher",
            name="Teacher (Curriculum Generator)",
            role=AgentRole.PRODUCER,
            capabilities=["generate", "analyze", "curriculum"],
        )


class LearnerRole(RoleRuntime):
    """
    学习者角色 — 负责执行训练和积累经验。
    对应 HarnessProvider + MemoryProvider。
    """
    
    def __init__(
        self,
        harness_provider: Any = None,
        memory_provider: Any = None,
        service_container: Any = None,
    ):
        super().__init__(
            name="Learner",
            provider=harness_provider,
            service_container=service_container,
        )
        self.harness_provider = harness_provider
        self.memory_provider = memory_provider
    
    @property
    def role_phase(self) -> TaskPhase:
        return TaskPhase.HARNESS
    
    async def assign(self, task: RoleTask) -> None:
        self._current_phase = RolePhase.ASSIGNING
        self._tasks.append(task)
        self._current_phase = RolePhase.WORKING
    
    async def work(self, task: RoleTask) -> RoleReport:
        """
        学习者工作：执行 Harness + 积累 Memory。
        
        Phase 2: 依次调用 HarnessProvider 和 MemoryProvider。
        """
        from runtimes.adaptive_runtime import AdaptiveRuntime, PipelineConfig
        from runtimes.checkpoint_store import CheckpointStore
        
        harness_output = None
        memory_output = None
        
        if self.harness_provider is not None:
            store = CheckpointStore()
            config = PipelineConfig(
                profile="learner",
                providers=[self.harness_provider],
                auto_save=False,
            )
            runtime = AdaptiveRuntime(
                config=config,
                checkpoint_store=store,
                service_container=self.service_container,
            )
            harness_output = await self.harness_provider.execute({}, runtime)
            self._last_output = harness_output
        
        if self.memory_provider is not None:
            store = CheckpointStore()
            config = PipelineConfig(
                profile="learner",
                providers=[self.memory_provider],
                auto_save=False,
            )
            runtime = AdaptiveRuntime(
                config=config,
                checkpoint_store=store,
                service_container=self.service_container,
            )
            memory_output = await self.memory_provider.execute({}, runtime)
        
        if harness_output or memory_output:
            result_data = {}
            metrics = {}
            if harness_output:
                result_data["harness"] = harness_output.to_dict()
                metrics["harness_ok"] = harness_output.ok
            if memory_output:
                result_data["memory"] = memory_output.to_dict()
                metrics["memory_ok"] = memory_output.ok
        else:
            result_data = {
                "status": "ok",
                "note": "No providers bound — degraded mode",
            }
            metrics = {"ok": True, "degraded": True}
        
        self._current_phase = RolePhase.REPORTING
        return RoleReport(
            role=self.name,
            phase=self._current_phase,
            output=result_data,
            metrics=metrics,
        )
    
    def to_agent_info(self) -> Any:
        """转换为 Coordinator 的 AgentInfo"""
        from services.coordinator import AgentInfo, AgentRole
        return AgentInfo(
            id="learner",
            name="Learner (Experiment Runner)",
            role=AgentRole.EXECUTOR,
            capabilities=["execute", "train", "harness", "memory"],
        )


class ReviewerRole(RoleRuntime):
    """
    评审角色 — 负责结果验收和反馈。
    对应 ReviewProvider。
    """
    
    def __init__(
        self,
        provider: Any = None,
        service_container: Any = None,
    ):
        super().__init__(
            name="Reviewer",
            provider=provider,
            service_container=service_container,
        )
    
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
        
        Phase 2: 调用 ReviewProvider.execute()。
        """
        if self.provider is not None:
            from runtimes.adaptive_runtime import AdaptiveRuntime, PipelineConfig
            from runtimes.checkpoint_store import CheckpointStore
            
            store = CheckpointStore()
            config = PipelineConfig(
                profile="reviewer",
                providers=[self.provider],
                auto_save=False,
            )
            runtime = AdaptiveRuntime(
                config=config,
                checkpoint_store=store,
                service_container=self.service_container,
            )
            
            output = await self.provider.execute({}, runtime)
            self._last_output = output
            
            result_data = output.to_dict()
            metrics = {
                "ok": output.ok,
                "phase": output.phase.value,
            }
        else:
            result_data = {
                "status": "ok",
                "verdict": "pass",
                "note": "No provider bound — degraded mode",
                "feedback": ["✅ Degraded mode auto-pass"],
            }
            metrics = {"ok": True, "degraded": True}
        
        self._current_phase = RolePhase.REPORTING
        return RoleReport(
            role=self.name,
            phase=self._current_phase,
            output=result_data,
            metrics=metrics,
        )
    
    def to_agent_info(self) -> Any:
        """转换为 Coordinator 的 AgentInfo"""
        from services.coordinator import AgentInfo, AgentRole
        return AgentInfo(
            id="reviewer",
            name="Reviewer (Quality Gate)",
            role=AgentRole.REVIEWER,
            capabilities=["review", "judge", "feedback"],
        )
