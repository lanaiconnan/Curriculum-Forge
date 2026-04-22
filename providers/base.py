"""
Provider Base Classes

基于 MoonClaw Extension Task Protocol 的任务执行抽象层。
定义 TaskProvider 接口和 TaskPhase 枚举。

参考：moonclaw/moonclaw-jobs/src/forge/task_provider.ts
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from runtimes.adaptive_runtime import AdaptiveRuntime


class TaskPhase(Enum):
    """Pipeline 执行阶段，对应 RL 训练流程的 4 个步骤"""
    CURRICULUM = "curriculum"   # 课程设计/任务分解
    HARNESS   = "harness"     # 测试用例生成/执行
    MEMORY    = "memory"       # 经验存储/检索
    REVIEW    = "review"       # 结果评审/反馈


class RunState(Enum):
    """Pipeline 运行状态（MoonClaw CheckpointState）"""
    PENDING    = "pending"
    RUNNING    = "running"
    WAITING    = "waiting"     # 等待外部输入（MoonClaw WaitingForInput）
    COMPLETED  = "completed"
    FAILED     = "failed"
    CANCELLED  = "cancelled"


@dataclass
class TaskOutput:
    """Provider 执行输出"""
    phase: TaskPhase
    data: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """检查执行是否成功"""
        return self.data.get("status") != "error"


@dataclass
class ProviderConfig:
    """Provider 配置"""
    name: str
    enabled: bool = True
    options: Dict[str, Any] = field(default_factory=dict)


class TaskProvider(ABC):
    """
    任务执行 Provider 基类。
    
    每个 Provider 对应 Pipeline 的一个阶段：
    - CurriculumProvider  →  CURRICULUM
    - HarnessProvider     →  HARNESS
    - MemoryProvider     →  MEMORY
    - ReviewProvider      →  REVIEW
    
    设计参考：MoonClaw TaskProvider + Curriculum-Forge services/
    """
    
    def __init__(self, config: Optional[ProviderConfig] = None):
        self.config = config or ProviderConfig(name=self.__class__.__name__)
        self._metrics: Dict[str, Any] = {}
    
    # ── Abstract Methods ────────────────────────────────────────────────────
    
    @property
    @abstractmethod
    def phase(self) -> TaskPhase:
        """返回此 Provider 对应的执行阶段"""
        raise NotImplementedError
    
    @abstractmethod
    async def execute(
        self,
        config: Dict[str, Any],
        runtime: AdaptiveRuntime,
    ) -> TaskOutput:
        """
        执行 Provider 逻辑。
        
        Args:
            config: 任务配置（从 profile JSON 加载）
            runtime: 执行引擎（包含 checkpoint store 等）
        
        Returns:
            TaskOutput: 包含执行结果和元数据
        
        Raises:
            ProviderError: 执行失败
        """
        raise NotImplementedError
    
    # ── Hook Methods ───────────────────────────────────────────────────────
    
    def can_handle(self, config: Dict[str, Any]) -> bool:
        """
        检查此 Provider 是否能处理此配置。
        
        默认返回 True，子类可覆盖实现过滤逻辑。
        例如 HarnessProvider 可检查 config.get("type") == "test"。
        """
        return True
    
    def validate_config(self, config: Dict[str, Any]) -> None:
        """
        验证配置是否有效。
        
        默认空实现，子类可覆盖添加验证。
        验证失败抛出 ValueError。
        """
        pass
    
    async def before_execute(
        self,
        config: Dict[str, Any],
        runtime: AdaptiveRuntime,
    ) -> None:
        """执行前 Hook（可选）"""
        pass
    
    async def after_execute(
        self,
        output: TaskOutput,
        runtime: AdaptiveRuntime,
    ) -> None:
        """执行后 Hook（可选）"""
        pass
    
    # ── Metrics ─────────────────────────────────────────────────────────────
    
    @property
    def metrics(self) -> Dict[str, Any]:
        """返回 Provider 指标"""
        return {
            **self._metrics,
            "phase": self.phase.value,
            "provider": self.__class__.__name__,
        }


class ProviderError(Exception):
    """Provider 执行错误"""
    
    def __init__(
        self,
        provider_name: str,
        phase: TaskPhase,
        message: str,
        cause: Optional[Exception] = None,
    ):
        self.provider_name = provider_name
        self.phase = phase
        self.cause = cause
        super().__init__(f"[{phase.value}] {provider_name}: {message}")


class ProviderRegistry:
    """
    Provider 注册中心。
    
    注册并发现可用 Provider。
    设计参考：MoonClaw ProviderRegistry。
    """
    
    def __init__(self):
        self._providers: Dict[TaskPhase, TaskProvider] = {}
        self._all: List[TaskProvider] = []
    
    def register(self, provider: TaskProvider) -> None:
        """注册一个 Provider"""
        self._providers[provider.phase] = provider
        self._all.append(provider)
    
    def get(self, phase: TaskPhase) -> Optional[TaskProvider]:
        """根据阶段获取 Provider"""
        return self._providers.get(phase)
    
    def list(self) -> List[TaskProvider]:
        """
        列出所有 Provider（按 phase 顺序：curriculum→harness→memory→review）。
        
        TaskPhase 值字母序即执行顺序：curriculum < harness < memory < review。
        """
        return sorted(self._all, key=lambda p: p.phase.value)
    
    def list_by_phase(self) -> Dict[TaskPhase, TaskProvider]:
        """按阶段映射返回所有 Provider"""
        return dict(self._providers)
