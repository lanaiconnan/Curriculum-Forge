"""
LRU Cache for CheckpointStore

提供内存缓存，减少文件系统遍历开销。
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TypeVar, Generic
from functools import wraps

from runtimes.checkpoint_store import CheckpointRecord, CheckpointStore

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """缓存条目"""
    value: T
    timestamp: float  # 创建时间戳
    ttl_seconds: float  # 过期时间（秒）


class LRUCache(Generic[T]):
    """
    线程安全的 LRU 缓存（简化版，无锁）。
    
    用于缓存 CheckpointStore 的 list() 和 load() 结果。
    """

    def __init__(self, max_size: int = 100, ttl_seconds: float = 60.0):
        """
        Args:
            max_size: 最大缓存条目数
            ttl_seconds: 缓存过期时间（秒）
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, CacheEntry[T]] = OrderedDict()

    def get(self, key: str) -> Optional[T]:
        """获取缓存值（如果未过期）"""
        if key not in self._cache:
            return None

        entry = self._cache[key]
        age = time.time() - entry.timestamp

        if age > entry.ttl_seconds:
            # 过期，删除
            del self._cache[key]
            return None

        # 命中，移到队尾（最近使用）
        self._cache.move_to_end(key)
        return entry.value

    def set(self, key: str, value: T, ttl_seconds: Optional[float] = None) -> None:
        """设置缓存值"""
        if key in self._cache:
            # 已存在，删除旧的
            del self._cache[key]
        elif len(self._cache) >= self.max_size:
            # 缓存已满，删除最老的（队首）
            self._cache.popitem(last=False)

        ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
        self._cache[key] = CacheEntry(
            value=value,
            timestamp=time.time(),
            ttl_seconds=ttl,
        )

    def invalidate(self, key: str) -> bool:
        """使指定缓存失效"""
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()

    def size(self) -> int:
        """当前缓存大小"""
        return len(self._cache)


class CachedCheckpointStore:
    """
    带 LRU 缓存的 CheckpointStore 包装器。
    
    缓存策略：
    - list(): 缓存结果，key="list:{profile}:{state}:{limit}"
    - load(): 缓存单条记录
    - save()/delete(): 使相关缓存失效
    """

    def __init__(self, store, cache_size: int = 100, cache_ttl: float = 30.0):
        """
        Args:
            store: 原始 CheckpointStore 实例
            cache_size: 缓存最大条目数
            cache_ttl: 缓存过期时间（秒），默认 30s
        """
        self._store = store
        self._list_cache: LRUCache[List[CheckpointRecord]] = LRUCache(
            max_size=cache_size,
            ttl_seconds=cache_ttl,
        )
        self._record_cache: LRUCache[CheckpointRecord] = LRUCache(
            max_size=cache_size * 10,  # 单条记录缓存更大
            ttl_seconds=cache_ttl,
        )

    # ── 代理方法 ───────────────────────────────────────────────────────

    def save(self, record: CheckpointRecord) -> Any:
        """保存记录（使缓存失效）"""
        result = self._store.save(record)
        # 使 list 缓存失效
        self._list_cache.clear()
        # 使该记录的缓存失效
        self._record_cache.invalidate(record.id)
        return result

    def load(self, run_id: str) -> Optional[CheckpointRecord]:
        """加载记录（使用缓存）"""
        # 先查缓存
        cached = self._record_cache.get(run_id)
        if cached is not None:
            return cached

        # 缓存未命中，从 store 加载
        record = self._store.load(run_id)
        if record is not None:
            self._record_cache.set(run_id, record)

        return record

    def delete(self, run_id: str) -> bool:
        """删除记录（使缓存失效）"""
        result = self._store.delete(run_id)
        if result:
            self._list_cache.clear()
            self._record_cache.invalidate(run_id)
        return result

    def list(
        self,
        profile: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 50,
    ) -> List[CheckpointRecord]:
        """列出记录（使用缓存）"""
        # 构造缓存 key
        key = f"list:{profile or 'all'}:{state or 'all'}:{limit}"

        # 先查缓存
        cached = self._list_cache.get(key)
        if cached is not None:
            return cached

        # 缓存未命中，从 store 加载
        records = self._store.list(profile=profile, state=state, limit=limit)
        self._list_cache.set(key, records)

        return records

    def latest(self, profile: Optional[str] = None) -> Optional[CheckpointRecord]:
        """获取最新记录"""
        records = self.list(profile=profile, limit=1)
        return records[0] if records else None

    def summary(self) -> Dict[str, Any]:
        """返回统计摘要（不缓存，直接代理）"""
        return self._store.summary()

    @staticmethod
    def new_id() -> str:
        """生成新的 run_id"""
        return CheckpointStore.new_id()

    def base_dir(self):
        """返回基础目录"""
        return self._store.base_dir

    # ── 缓存管理 ───────────────────────────────────────────────────────

    def cache_stats(self) -> Dict[str, Any]:
        """返回缓存统计"""
        return {
            "list_cache_size": self._list_cache.size(),
            "record_cache_size": self._record_cache.size(),
            "max_size": self._list_cache.max_size,
            "ttl_seconds": self._list_cache.ttl_seconds,
        }

    def clear_cache(self) -> None:
        """清空所有缓存"""
        self._list_cache.clear()
        self._record_cache.clear()
