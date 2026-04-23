"""
Adaptive Runtime

MoonClaw 风格的 Pipeline 执行引擎。
协调 Provider 链的执行，管理状态转换，支持 WaitingForInput。

参考：moonclaw/moonclaw-jobs/src/forge/task_runtime.ts
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from providers.base import (
    RunState,
    TaskPhase,
    TaskProvider,
    TaskOutput,
)
from runtimes.checkpoint_store import CheckpointRecord, CheckpointStore
from runtimes.workspace import RunWorkspace

# Lazy import to avoid circular dependency
def _get_coordinator():
    from services.coordinator import Coordinator
    return Coordinator


@dataclass
class PipelineConfig:
    """Pipeline 执行配置"""
    profile: str
    providers: List[TaskProvider]
    checkpoint_dir: Optional[Path] = None
    auto_save: bool = True
    interactive: bool = False


class AdaptiveRuntime:
    """
    自适应执行引擎。

    管理 Pipeline 的端到端执行：
    1. 按顺序执行每个 Provider
    2. 自动保存 Checkpoint
    3. 支持 WaitingForInput 暂停
    4. 支持从 Checkpoint 恢复

    注意：使用普通类而非 @dataclass，以避免 pytest-asyncio 0.21.2
    的模块级 patch 与 dataclass __post_init__ 的 LOAD_GLOBAL bytecode 冲突。

    设计参考：MoonClaw AdaptiveTaskRuntime + moonclaw forge/runtime.ts
    """

    def __init__(
        self,
        config: PipelineConfig,
        checkpoint_store: CheckpointStore,
        service_container: Any = None,
        workspace: Optional[RunWorkspace] = None,
        coordinator: Any = None,
    ):
        self.config = config
        self.checkpoint_store = checkpoint_store
        self.service_container = service_container  # May be None (standalone mode)
        self.workspace = workspace  # Per-run workspace isolation
        self.coordinator = coordinator  # Optional: multi-agent Coordinator
        self._record: Optional[CheckpointRecord] = None
        self._interactive_queue = asyncio.Queue()
        self._provider_index: int = 0

    async def run_stream(self, run_id: Optional[str] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute pipeline and yield events for SSE streaming.

        Yields event dicts:
            {"event": "phase_start", "phase": "curriculum", "index": 0}
            {"event": "phase_done",  "phase": "curriculum", "output": {...}}
            {"event": "error",      "error": "..."}
        """
        from typing import AsyncGenerator

        run_config = {}
        rid = run_id or self.checkpoint_store.new_id()

        self._record = CheckpointRecord(
            id=rid,
            created_at=datetime.now(timezone.utc).isoformat(),
            profile=self.config.profile,
            phase=TaskPhase.CURRICULUM.value,
            state=RunState.RUNNING,
            config=run_config,
            state_data={},
            metrics={"providers_run": 0, "providers_succeeded": 0},
            workspace_dir=self.workspace.workspace_path() if self.workspace else None,
        )
        self._save()

        yield {"event": "start", "run_id": rid, "profile": self.config.profile}

        providers_to_run = self.config.providers
        self._provider_index = 0

        try:
            for idx, provider in enumerate(providers_to_run):
                self._provider_index = idx
                phase_name = provider.phase.value

                yield {"event": "phase_start", "phase": phase_name, "index": idx}

                output = await self._execute_provider(provider, run_config)

                self._record.state_data[phase_name] = output.to_dict()
                self._record.metrics["providers_run"] += 1
                if output.ok:
                    self._record.metrics["providers_succeeded"] += 1
                self._record.phase = phase_name
                self._save()

                yield {
                    "event": "phase_done",
                    "phase": phase_name,
                    "ok": output.ok,
                    "output": output.to_dict(),
                }

                if output.metadata.get("waiting"):
                    self._record.state = RunState.WAITING
                    self._save()
                    yield {"event": "waiting", "phase": phase_name}
                    if self.config.interactive:
                        user_input = await self._interactive_queue.get()
                        run_config.update(user_input)

            self._record.state = RunState.COMPLETED
            self._record.finished_at = datetime.now(timezone.utc).isoformat()
            self._save()
            yield {"event": "done", "state": "completed", "run_id": rid}

        except Exception as e:
            self._record.state = RunState.FAILED
            self._record.metrics["error"] = str(e)
            self._record.finished_at = datetime.now(timezone.utc).isoformat()
            self._save()
            yield {"event": "error", "error": str(e), "phase": self._record.phase}

    @property
    def record(self) -> Optional[CheckpointRecord]:
        return self._record

    @property
    def status(self) -> Dict[str, Any]:
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
            workspace_dir=self.workspace.workspace_path() if self.workspace else None,
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

                if output.metadata.get("waiting"):
                    self._record.state = RunState.WAITING
                    self._save()
                    if self.config.interactive:
                        user_input = await self._interactive_queue.get()
                        run_config.update(user_input)

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

    async def _execute_provider(
        self,
        provider: TaskProvider,
        config: Dict[str, Any],
    ) -> TaskOutput:
        """执行单个 Provider（含 before/after hook）。

        Provider 通过 runtime.service_container 访问 services/ 层。
        执行完成后，若 coordinator 存在，通过 MessageQueue 通知其他 Agent。
        """
        await provider.before_execute(config, self)
        output = await provider.execute(config, self)
        await provider.after_execute(output, self)

        # Notify coordinator if available
        if self.coordinator is not None:
            await self._notify_agents(provider.phase.value, output)

        return output

    async def _notify_agents(self, phase: str, output: TaskOutput) -> None:
        """通过 Coordinator 的 MessageQueue 通知其他 Agent。

        发送 broadcast 消息，包含 phase 和 output 摘要。
        其他 Agent 可以订阅此消息来触发后续操作。
        """
        try:
            self.coordinator.message_queue.broadcast(
                from_agent="runtime",
                msg_type="provider_done",
                payload={
                    "phase": phase,
                    "ok": output.ok,
                    "data_keys": list(output.data.keys()) if output.data else [],
                    "run_id": self._record.id if self._record else None,
                },
            )
        except Exception as e:
            # Notification failure should not break the pipeline
            import logging
            logging.getLogger(__name__).warning(
                f"Failed to notify agents: {e}"
            )

    def _save(self) -> None:
        """保存 Checkpoint（auto_save=True 时）"""
        if self.config.auto_save and self._record:
            self.checkpoint_store.save(self._record)

    async def push_input(self, data: Dict[str, Any]) -> None:
        """推送外部输入（用于 WaitingForInput 恢复）"""
        await self._interactive_queue.put(data)
