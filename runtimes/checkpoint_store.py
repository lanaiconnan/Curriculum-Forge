"""
Checkpoint Store

MoonClaw 风格的 Pipeline 状态持久化。
每个运行产生一个 CheckpointRecord（JSON），支持断点恢复。

参考：moonclaw/moonclaw-jobs/src/forge/checkpoint.ts
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from providers.base import RunState


CHECKPOINT_DIR = Path.home() / ".curriculum-forge" / "checkpoints"
DEFAULT_DIR = CHECKPOINT_DIR


@dataclass
class CheckpointRecord:
    """
    Pipeline 运行记录。
    
    对应 MoonClaw moonclaw-jobs/src/forge/checkpoint.ts 的 CheckpointRecord。
    """
    id: str                          # 格式: run_YYYYMMDD_HHMMSS
    created_at: str                  # ISO-8601
    profile: str                     # 使用的 profile 名称
    phase: str                       # 当前/最终阶段
    state: RunState                  # 运行状态
    config: Dict[str, Any]           # 原始配置（来自 profile JSON）
    state_data: Dict[str, Any]       # 中间状态（Provider 执行结果）
    metrics: Dict[str, Any]           # 统计指标
    description: str = ""            # 运行描述
    finished_at: Optional[str] = None  # 完成时间
    workspace_dir: Optional[str] = None  # Per-run workspace directory
    retry_count: int = 0  # Number of retry attempts made
    max_retries: int = 3  # Maximum retry attempts allowed (0 = disabled)
    workflow_id: Optional[str] = None  # Coordinator Workflow ID (set by Gateway when job is registered with Coordinator)
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（含 RunState enum 处理）"""
        d = asdict(self)
        d["state"] = self.state.value  # enum → string
        return d
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> CheckpointRecord:
        """从字典反序列化"""
        d["state"] = RunState(d["state"])  # string → enum
        return cls(**d)


class CheckpointStore:
    """
    Checkpoint 持久化管理器。
    
    管理 .curriculum-forge/checkpoints/ 目录下的 JSON 文件。
    每个运行对应一个 {run_id}.json 文件。
    """
    
    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = (base_dir or DEFAULT_DIR).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    # ── Core Operations ────────────────────────────────────────────────────
    
    def save(self, record: CheckpointRecord) -> Path:
        """
        保存 CheckpointRecord 到 JSON 文件。
        
        Returns:
            Path: 保存的文件路径
        """
        path = self.base_dir / f"{record.id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record.to_dict(), f, ensure_ascii=False, indent=2)
        return path
    
    def load(self, run_id: str) -> Optional[CheckpointRecord]:
        """
        加载指定 run_id 的 CheckpointRecord。
        
        Returns:
            CheckpointRecord 或 None（文件不存在）
        """
        path = self.base_dir / f"{run_id}.json"
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return CheckpointRecord.from_dict(d)
    
    def delete(self, run_id: str) -> bool:
        """删除指定 Checkpoint"""
        path = self.base_dir / f"{run_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False
    
    def list(
        self,
        profile: Optional[str] = None,
        state: Optional[RunState] = None,
        limit: int = 50,
    ) -> List[CheckpointRecord]:
        """
        列出 Checkpoint 记录。
        
        Args:
            profile: 按 profile 过滤
            state: 按运行状态过滤
            limit: 最多返回条数（按时间倒序）
        """
        records = []
        for path in sorted(self.base_dir.glob("run_*.json"), reverse=True):
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                record = CheckpointRecord.from_dict(d)
                if profile and record.profile != profile:
                    continue
                if state and record.state != state:
                    continue
                records.append(record)
                if len(records) >= limit:
                    break
            except (json.JSONDecodeError, KeyError):
                continue
        return records
    
    def latest(self, profile: Optional[str] = None) -> Optional[CheckpointRecord]:
        """获取最近一条 Checkpoint"""
        records = self.list(profile=profile, limit=1)
        return records[0] if records else None
    
    # ── Utilities ──────────────────────────────────────────────────────────
    
    @staticmethod
    def new_id() -> str:
        """生成新的 run_id"""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"run_{ts}"
    
    def summary(self) -> Dict[str, Any]:
        """返回 CheckpointStore 统计摘要"""
        all_records = self.list(limit=1000)
        by_state: Dict[str, int] = {}
        by_profile: Dict[str, int] = {}
        for r in all_records:
            by_state[r.state.value] = by_state.get(r.state.value, 0) + 1
            by_profile[r.profile] = by_profile.get(r.profile, 0) + 1
        return {
            "total": len(all_records),
            "by_state": by_state,
            "by_profile": by_profile,
            "storage_dir": str(self.base_dir),
        }
