"""
Adaptive Runtime

MoonClaw 风格的 Pipeline 执行引擎。
协调 Provider 链的执行，管理状态转换，支持 WaitingForInput。

参考：moonclaw/moonclaw-jobs/src/forge/task_runtime.ts
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from providers.base import (
    RunState,
    TaskPhase,
    TaskProvider,
    TaskOutput,
)
from runtimes.checkpoint_store import CheckpointRecord, CheckpointStore


@dataclass
class PipelineConfig:
    """Pipeline 执行配置"""
    profile: str
    providers: List[TaskProvider]
    checkpoint_dir: Optional[Path] = None
    auto_save: bool = True
    interactive: bool = False


@dataclass
class AdaptiveRuntime:
    """
    自适应执行引擎。
    
    管理 Pipeline 的端到端执行：
    1. 按顺序执行每个 Provider
    2. 自动保存 Checkpoint
    3. 支持 WaitingForInput 暂停
    4. 支持从 Checkpoint 恢复
    
    设计参考：MoonClaw AdaptiveTaskRuntime + moonclaw forge/runtime.ts
    """
    
    config: PipelineConfig
    checkpoint_store: CheckpointStore = field(default=None)
    _record: Optional[CheckpointRecord] = field(default=None, init=False)
    _interactive_queue: asyncio.Queue = field(default_factory=None, init=False)
    _provider_index: int = field(default=0, init=False)  # 记录已完成的 Provider 索引
    
    def __post_init__(self):
        if self.checkpoint_store is None:
            self.checkpoint_store = CheckpointStore(self.config.checkpoint_dir)
        self._interactive_queue = asyncio.Queue()
    
    # ── Execution ─────────────────────────────────────────────────────────
    
    async def run(self, config: Optional[Dict[str, Any]] = None) -> CheckpointRecord:
        """
        执行完整 Pipeline。
        
        按 Provider 顺序执行，状态自动保存到 CheckpointStore。
        遇到 WaitingForInput 时：
          - interactive=True：暂停等待外部输入
          - interactive=False：自动跳过
        
        Args:
            config: 运行时配置（覆盖 profile 中的默认值）
        
        Returns:
            CheckpointRecord: 最终运行记录
        
        Raises:
            RuntimeError: Pipeline 执行失败
        """
        run_config = config or {}
        run_id = self.checkpoint_store.new_id()
        
        self._record = CheckpointRecord(
            id=run_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            profile=self.config.profile,
            phase=TaskPhase.CURRICULUM.value,
            state=RunState.RUNNING,
            config=run_config,
            state_data={},
            metrics={"providers_run": 0, "providers_succeeded": 0},
        )
        self._save()
        
        providers_to_run = self.config.providers
        self._provider_index = 0
        
        try:
            for idx, provider in enumerate(providers_to_run):
                self._provider_index = idx
                output = await self._execute_provider(provider, run_config)
                self._record.state_data[provider.phase.value] = output.to_dict()
                self._record.metrics["providers_run"] += 1
                if output.ok:
                    self._record.metrics["providers_succeeded"] += 1
                self._record.phase = provider.phase.value
                self._save()
                
                # WaitingForInput: 暂停等待外部输入
                if output.metadata.get("waiting"):
                    self._record.state = RunState.WAITING
                    self._save()
                    if self.config.interactive:
                        user_input = await self._interactive_queue.get()
                        run_config.update(user_input)
                    else:
                        pass  # 非交互模式：视为继续
            
            self._record.state = RunState.COMPLETED
            self._record.finished_at = datetime.now(timezone.utc).isoformat()
            self._save()
            return self._record
            
        except Exception as e:
            self._record.state = RunState.FAILED
            self._record.metrics["error"] = str(e)
            self._record.finished_at = datetime.now(timezone.utc).isoformat()
            self._save()
            raise RuntimeError(f"Pipeline failed at phase {self._record.phase}: {e}") from e
    
    async def resume(
        self,
        run_id: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> CheckpointRecord:
        """
        从 Checkpoint 恢复执行。
        
        读取保存的 state_data，跳过已完成的 Provider 阶段，
        从第一个未完成阶段继续。
        
        Args:
            run_id: 要恢复的运行 ID
            config: 额外的运行时配置
        
        Returns:
            CheckpointRecord: 恢复后的最终记录
        """
        saved = self.checkpoint_store.load(run_id)
        if not saved:
            raise ValueError(f"Checkpoint not found: {run_id}")
        
        if saved.state == RunState.COMPLETED:
            print(f"Run already completed: {run_id}")
            return saved
        
        if saved.state not in (RunState.RUNNING, RunState.WAITING):
            raise ValueError(f"Cannot resume run in state: {saved.state.value}")
        
        self._record = saved
        
        # 确定已完成的阶段
        completed_phases = set(saved.state_data.keys())
        providers_to_run = [
            p for p in self.config.providers
            if p.phase.value not in completed_phases
        ]
        
        print(f"Resuming from {len(completed_phases)} completed phases...")
        print(f"Remaining providers: {[p.phase.value for p in providers_to_run]}")
        
        resume_config = {**saved.config, **(config or {})}
        
        try:
            for provider in providers_to_run:
                self._record.phase = provider.phase.value
                self._record.state = RunState.RUNNING
                output = await self._execute_provider(provider, resume_config)
                self._record.state_data[provider.phase.value] = output.to_dict()
                self._record.metrics["providers_run"] += 1
                if output.ok:
                    self._record.metrics["providers_succeeded"] += 1
                self._save()
                
                if output.metadata.get("waiting"):
                    self._record.state = RunState.WAITING
                    self._save()
                    if self.config.interactive:
                        user_input = await self._interactive_queue.get()
                        resume_config.update(user_input)
            
            self._record.state = RunState.COMPLETED
            self._record.finished_at = datetime.now(timezone.utc).isoformat()
            self._save()
            return self._record
            
        except Exception as e:
            self._record.state = RunState.FAILED
            self._record.metrics["error"] = str(e)
            self._record.finished_at = datetime.now(timezone.utc).isoformat()
            self._save()
            raise RuntimeError(f"Resume failed: {e}") from e
    
    # ── Provider Execution ────────────────────────────────────────────────
    
    async def _execute_provider(
        self,
        provider: TaskProvider,
        config: Dict[str, Any],
    ) -> TaskOutput:
        """执行单个 Provider（含 before/after hook）"""
        await provider.before_execute(config, self)
        output = await provider.execute(config, self)
        await provider.after_execute(output, self)
        return output
    
    def _save(self) -> None:
        """保存 Checkpoint（auto_save=True 时）"""
        if self.config.auto_save and self._record:
            self.checkpoint_store.save(self._record)
    
    # ── Interactive Input ─────────────────────────────────────────────────
    
    async def push_input(self, data: Dict[str, Any]) -> None:
        """推送外部输入（用于 WaitingForInput 恢复）"""
        await self._interactive_queue.put(data)
    
    # ── Status ────────────────────────────────────────────────────────────
    
    @property
    def record(self) -> Optional[CheckpointRecord]:
        """获取当前 CheckpointRecord"""
        return self._record
    
    @property
    def status(self) -> Dict[str, Any]:
        """返回运行时状态摘要"""
        if not self._record:
            return {"state": "not_started"}
        return {
            "run_id": self._record.id,
            "state": self._record.state.value,
            "phase": self._record.phase,
            "profile": self._record.profile,
            "providers_run": self._record.metrics.get("providers_run", 0),
            "providers_succeeded": self._record.metrics.get("providers_succeeded", 0),
        }
