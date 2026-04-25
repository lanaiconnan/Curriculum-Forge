"""
Statistics Aggregator

后台定期预计算统计数据，缓存结果供 Gateway 使用。
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("stats_aggregator")


@dataclass
class StatsBucket:
    """时间桶统计数据"""
    timestamp: str
    total: int = 0
    completed: int = 0
    failed: int = 0
    total_duration_ms: int = 0
    job_count_with_duration: int = 0
    retries: int = 0

    def to_dict(self) -> Dict[str, Any]:
        avg_duration = (
            self.total_duration_ms // self.job_count_with_duration
            if self.job_count_with_duration > 0
            else 0
        )
        return {
            "timestamp": self.timestamp,
            "total": self.total,
            "completed": self.completed,
            "failed": self.failed,
            "avg_duration_ms": avg_duration,
            "retries": self.retries,
        }


@dataclass
class AggregatedStats:
    """预聚合统计数据"""
    updated_at: str
    hours: int
    buckets: List[StatsBucket] = field(default_factory=list)
    total_jobs: int = 0
    total_completed: int = 0
    total_failed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "updated_at": self.updated_at,
            "hours": self.hours,
            "buckets": [b.to_dict() for b in self.buckets],
            "total_jobs": self.total_jobs,
            "total_completed": self.total_completed,
            "total_failed": self.total_failed,
        }


class StatsAggregator:
    """
    统计数据聚合器。
    
    定期从 CheckpointStore 计算统计数据，缓存结果。
    """

    def __init__(
        self,
        store,
        interval_seconds: float = 300.0,  # 5分钟
        default_hours: int = 24,
    ):
        """
        Args:
            store: CheckpointStore 实例
            interval_seconds: 聚合间隔（秒）
            default_hours: 默认时间范围（小时）
        """
        self._store = store
        self._interval = interval_seconds
        self._default_hours = default_hours
        self._cache: Dict[int, AggregatedStats] = {}  # hours → stats
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """启动后台聚合任务"""
        if self._running:
            logger.warning("StatsAggregator already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"StatsAggregator started (interval={self._interval}s)")

    async def stop(self) -> None:
        """停止后台聚合任务"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("StatsAggregator stopped")

    async def _run_loop(self) -> None:
        """后台聚合循环"""
        # 启动时立即执行一次
        await self._aggregate()

        while self._running:
            try:
                await asyncio.sleep(self._interval)
                if self._running:
                    await self._aggregate()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Aggregation error: {e}")

    async def _aggregate(self) -> None:
        """执行聚合计算"""
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        updated_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        # 计算 24 小时和 72 小时两个维度
        for hours in [24, 72]:
            stats = self._compute_stats(hours, now, updated_at)
            self._cache[hours] = stats

        logger.debug(f"Aggregated stats for {len(self._cache)} time ranges")

    def _compute_stats(
        self,
        hours: int,
        now: datetime,
        updated_at: str,
    ) -> AggregatedStats:
        """计算指定时间范围的统计"""
        start_time = now - timedelta(hours=hours)

        # 初始化时间桶
        buckets: Dict[str, StatsBucket] = {}
        for h in range(hours):
            bucket_time = start_time + timedelta(hours=h)
            bucket_key = bucket_time.strftime("%Y-%m-%dT%H:00:00Z")
            buckets[bucket_key] = StatsBucket(timestamp=bucket_key)

        # 加载记录
        try:
            records = self._store.list(limit=10000)
        except Exception as e:
            logger.error(f"Failed to list records: {e}")
            records = []

        # 填充时间桶
        total_jobs = 0
        total_completed = 0
        total_failed = 0

        for record in records:
            try:
                created = datetime.fromisoformat(
                    record.created_at.replace("Z", "+00:00")
                )
                if created < start_time:
                    continue

                bucket_key = created.strftime("%Y-%m-%dT%H:00:00Z")
                if bucket_key not in buckets:
                    continue

                bucket = buckets[bucket_key]
                bucket.total += 1
                total_jobs += 1

                if record.state.value == "completed":
                    bucket.completed += 1
                    total_completed += 1
                elif record.state.value in ("failed", "cancelled", "aborted"):
                    bucket.failed += 1
                    total_failed += 1

                bucket.retries += record.retry_count

                # Duration
                if record.finished_at and record.created_at:
                    try:
                        start = datetime.fromisoformat(
                            record.created_at.replace("Z", "+00:00")
                        )
                        end = datetime.fromisoformat(
                            record.finished_at.replace("Z", "+00:00")
                        )
                        duration_ms = int((end - start).total_seconds() * 1000)
                        bucket.total_duration_ms += duration_ms
                        bucket.job_count_with_duration += 1
                    except Exception:
                        pass
            except Exception:
                pass

        # 排序时间桶
        sorted_buckets = [
            buckets[k] for k in sorted(buckets.keys())
        ]

        return AggregatedStats(
            updated_at=updated_at,
            hours=hours,
            buckets=sorted_buckets,
            total_jobs=total_jobs,
            total_completed=total_completed,
            total_failed=total_failed,
        )

    def get_stats(self, hours: int = 24) -> Optional[AggregatedStats]:
        """获取预聚合统计数据"""
        return self._cache.get(hours)

    def get_all_stats(self) -> Dict[int, AggregatedStats]:
        """获取所有预聚合数据"""
        return self._cache.copy()

    def invalidate(self) -> None:
        """清空缓存，触发重新计算"""
        self._cache.clear()
        logger.debug("Stats cache invalidated")
