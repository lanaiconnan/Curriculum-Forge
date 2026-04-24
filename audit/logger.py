"""
AuditLogger — 审计日志核心实现

支持：
- 持久化存储到 JSONL 文件（每日一个文件）
- 内存索引加速查询
- 线程安全（asyncio 环境下使用锁）
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── 类型别名 ───────────────────────────────────────────────────────────────────

AuditRecord = Dict[str, Any]

CATEGORIES = {"job", "acp", "workflow", "channel", "gateway"}


# ── AuditLogger ────────────────────────────────────────────────────────────────

class AuditLogger:
    """
    审计日志记录器。

    Usage:
        audit = AuditLogger()
        audit.log(category="job", event="job_created", actor="system",
                  target="job_abc123", metadata={"profile": "rl_controller"})
    """

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        source: str = "gateway",
    ) -> None:
        if base_dir is None:
            base_dir = Path.home() / ".curriculum-forge" / "audit"
        self._base_dir = Path(base_dir)
        self._source = source
        self._lock = threading.Lock()
        # In-memory index: date → { event_type → count }
        self._index: Dict[str, Dict[str, int]] = {}
        # Ensure directory exists
        self._base_dir.mkdir(parents=True, exist_ok=True)

    # ── Public API ─────────────────────────────────────────────────────────────

    def log(
        self,
        *,
        category: str,
        event: str,
        actor: str = "system",
        target: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> AuditRecord:
        """
        记录一条审计日志。

        Args:
            category: 事件类别（job / acp / workflow / channel / gateway）
            event: 事件类型（如 job_created）
            actor: 操作者（agent_id / "system" / "user"）
            target: 目标资源（job_id / agent_id / workflow_id 等）
            metadata: 附加信息
            timestamp: 可选时间戳（默认当前 UTC 时间）
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        ts_str = timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        date_str = timestamp.strftime("%Y-%m-%d")

        record: AuditRecord = {
            "id": str(uuid.uuid4()),
            "timestamp": ts_str,
            "category": category,
            "event": event,
            "actor": str(actor),
            "target": str(target),
            "metadata": metadata or {},
            "source": self._source,
        }

        self._write(record, date_str)
        self._update_index(date_str, event)
        return record

    def query(
        self,
        *,
        category: Optional[str] = None,
        event: Optional[str] = None,
        actor: Optional[str] = None,
        target: Optional[str] = None,
        date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditRecord]:
        """
        查询审计日志。

        Args:
            category: 过滤类别
            event: 过滤事件类型
            actor: 过滤操作者
            target: 过滤目标资源
            date: 日期（YYYY-MM-DD，默认当天）
            limit: 返回条数（最多 1000）
            offset: 分页偏移
        """
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        limit = min(limit, 1000)
        filepath = self._filepath(date)

        if not filepath.exists():
            return []

        results: List[AuditRecord] = []
        skipped = 0

        with self._lock:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    if not self._matches(record, category, event, actor, target):
                        continue
                    if skipped < offset:
                        skipped += 1
                        continue
                    results.append(record)
                    if len(results) >= limit:
                        break

        return results

    def stats(self, date: Optional[str] = None) -> Dict[str, Any]:
        """
        统计指定日期的审计日志概况。
        """
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filepath = self._filepath(date)

        total = 0
        by_category: Dict[str, int] = {}
        by_event: Dict[str, int] = {}

        if filepath.exists():
            with self._lock:
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        record = json.loads(line)
                        total += 1
                        cat = record.get("category", "unknown")
                        evt = record.get("event", "unknown")
                        by_category[cat] = by_category.get(cat, 0) + 1
                        by_event[evt] = by_event.get(evt, 0) + 1

        return {
            "date": date,
            "total": total,
            "by_category": by_category,
            "by_event": by_event,
        }

    # ── Internal ───────────────────────────────────────────────────────────────

    def _filepath(self, date: str) -> Path:
        return self._base_dir / f"{date}.jsonl"

    def _write(self, record: AuditRecord, date: str) -> None:
        filepath = self._filepath(date)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with self._lock:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(line)

    def _update_index(self, date: str, event: str) -> None:
        if date not in self._index:
            self._index[date] = {}
        self._index[date][event] = self._index[date].get(event, 0) + 1

    @staticmethod
    def _matches(
        record: AuditRecord,
        category: Optional[str],
        event: Optional[str],
        actor: Optional[str],
        target: Optional[str],
    ) -> bool:
        if category and record.get("category") != category:
            return False
        if event and record.get("event") != event:
            return False
        if actor and record.get("actor") != actor:
            return False
        if target and record.get("target") != target:
            return False
        return True
