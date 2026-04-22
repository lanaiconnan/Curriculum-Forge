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
    ProviderRegistry,
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
    checkpoint_store: CheckpointStore = field(default_factory=None)
    _record: CheckpointRecord = field(default=None, init=False)
    _interactive_queue: asyncio.Queue = field(default_factory=None, init=False)
    
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
          - interactive=False：自动跳过或报错
        
        Args:
            config: 运行时配置（覆盖 profile 中的默认值）
        
        Returns:
            CheckpointRecord: 最终运行记录
        
        Raises:
            RuntimeError: Pipeline 执行失败
        """
        final_config = config or {}
        run_id = self.checkpoint_store.new_id()
        
        self._record = CheckpointRecord(
            id=run_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            profile=self.config.profile,
            phase=TaskPhase.CURRICULUM.value,
            state=RunState.RUNNING,
            config=final_config,
            state_data={},
            metrics={"providers_run": 0, "providers_succeeded": 0},
        )
        self._save()
        
        providers_to_run = self._resolve_providers()
        
        try:
            for provider in providers_to_run:
                output = await self._execute_provider(provider, final_config)
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
                        final_config.update(user_input)
                    else:
                        # 非交互模式：视为完成，跳过等待
                        pass
            
            self._record.state = RunState.COMPLETED
            self._record.finished_at = datetime.now(timezone.utc).isoformat()
            self._save()
            return self._record
            
        except Exception as e:
            self._record.state = RunState.FAILED
            self._record.metrics["error"] = str(e)
            self._record.finished_at = datetime.now(timezone.utc).isoformat()
            self._save()
            raise RuntimeError(f"Pipeline failed: {e}") from e
    
    async def resume(
        self,
        run_id: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> CheckpointRecord:
        """
        从 Checkpoint 恢复执行。
        
        Args:
            run_id: 要恢复的运行 ID
            config: 额外的运行时配置
        
        Returns:
            CheckpointRecord: 恢复后的最终记录
        """
        saved = self.checkpoint_store.load(run_id)
        if not saved:
            raise ValueError(f"Checkpoint not found: {run_id}")
        
        self._record = saved
        
        if saved.state == RunState.COMPLETED:
            print(f"Run already completed: {run_id}")
            return saved
        
        if saved.state not in (RunState.RUNNING, RunState.WAITING):
            raise ValueError(f"Cannot resume run in state: {saved.state.value}")
        
        # 找到上次中断的阶段
        resume_config = {**saved.config, **(config or {})}
        
        try:
            # Re-run all providers from the beginning
            # (In full implementation would resume from checkpoint)
            return await self.run(resume_config)
        except Exception as e:
            self._record.state = RunState.FAILED
            self._record.metrics["error"] = str(e)
            self._record.finished_at = datetime.now(timezone.utc).isoformat()
            self._save()
            raise
    
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
    
    def _resolve_providers(self) -> List[TaskProvider]:
        """根据 profile 配置解析要运行的 Provider 顺序"""
        return self.config.providers
    
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
        }
