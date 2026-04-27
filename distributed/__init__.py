"""
Distributed Coordinator Support

支持多节点部署的协调机制:
- NodeRegistry: 节点注册与健康检查
- LeaderElection: 主节点选举 (基于租约)
- DistributedLock: 分布式锁
- TaskDistribution: 任务分发策略

架构说明:
- 无状态 Gateway 节点可水平扩展
- Coordinator 通过 Leader Election 实现单主多从
- 任务队列使用分布式锁保证幂等性
"""

from __future__ import annotations

import asyncio
import logging
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Callable
from enum import Enum
from abc import ABC, abstractmethod

logger = logging.getLogger("distributed")

# ── Data Classes ───────────────────────────────────────────────────────────────

class NodeStatus(str, Enum):
    """节点状态"""
    ACTIVE = "active"
    IDLE = "idle"
    DRAINING = "draining"
    OFFLINE = "offline"


@dataclass
class NodeInfo:
    """节点信息"""
    node_id: str
    host: str
    port: int
    status: NodeStatus = NodeStatus.ACTIVE
    is_leader: bool = False
    capacity: int = 100  # 最大并发任务数
    current_load: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    last_heartbeat: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "host": self.host,
            "port": self.port,
            "status": self.status.value,
            "is_leader": self.is_leader,
            "capacity": self.capacity,
            "current_load": self.current_load,
            "load_pct": round(self.current_load / self.capacity * 100, 1) if self.capacity > 0 else 0,
            "metadata": self.metadata,
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "registered_at": self.registered_at.isoformat(),
        }
    
    def is_healthy(self, timeout_seconds: int = 30) -> bool:
        """检查节点是否健康"""
        if self.status == NodeStatus.OFFLINE:
            return False
        elapsed = (datetime.now(timezone.utc) - self.last_heartbeat).total_seconds()
        return elapsed < timeout_seconds
    
    def available_capacity(self) -> int:
        """获取可用容量"""
        if self.status != NodeStatus.ACTIVE:
            return 0
        return max(0, self.capacity - self.current_load)


# ── Node Registry ──────────────────────────────────────────────────────────────

class NodeRegistry:
    """
    节点注册表
    
    管理所有节点的注册、心跳、健康检查。
    支持回调通知。
    """
    
    def __init__(self, heartbeat_timeout: int = 30):
        self._nodes: Dict[str, NodeInfo] = {}
        self._lock = threading.RLock()
        self._heartbeat_timeout = heartbeat_timeout
        self._on_node_joined: Optional[Callable[[NodeInfo], None]] = None
        self._on_node_left: Optional[Callable[[NodeInfo], None]] = None
        self._on_leader_changed: Optional[Callable[[Optional[NodeInfo]], None]] = None
    
    def register(
        self,
        host: str,
        port: int,
        capacity: int = 100,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> NodeInfo:
        """注册新节点"""
        node_id = f"node_{uuid.uuid4().hex[:8]}"
        
        node = NodeInfo(
            node_id=node_id,
            host=host,
            port=port,
            capacity=capacity,
            metadata=metadata or {},
        )
        
        with self._lock:
            self._nodes[node_id] = node
        
        logger.info(f"Node registered: {node_id} ({host}:{port})")
        
        if self._on_node_joined:
            self._on_node_joined(node)
        
        return node
    
    def unregister(self, node_id: str) -> bool:
        """注销节点"""
        with self._lock:
            node = self._nodes.pop(node_id, None)
            if not node:
                return False
        
        logger.info(f"Node unregistered: {node_id}")
        
        if self._on_node_left:
            self._on_node_left(node)
        
        return True
    
    def heartbeat(self, node_id: str, load: Optional[int] = None) -> bool:
        """更新节点心跳"""
        with self._lock:
            node = self._nodes.get(node_id)
            if not node:
                return False
            
            node.last_heartbeat = datetime.now(timezone.utc)
            if load is not None:
                node.current_load = load
        
        return True
    
    def get_node(self, node_id: str) -> Optional[NodeInfo]:
        """获取节点信息"""
        return self._nodes.get(node_id)
    
    def list_nodes(self, status: Optional[NodeStatus] = None) -> List[NodeInfo]:
        """列出所有节点"""
        nodes = list(self._nodes.values())
        if status:
            nodes = [n for n in nodes if n.status == status]
        return nodes
    
    def list_healthy_nodes(self) -> List[NodeInfo]:
        """列出健康节点"""
        return [n for n in self._nodes.values() if n.is_healthy(self._heartbeat_timeout)]
    
    def check_health(self) -> Dict[str, Any]:
        """
        执行健康检查
        
        标记不健康的节点为 OFFLINE
        """
        now = datetime.now(timezone.utc)
        unhealthy = []
        
        with self._lock:
            for node in self._nodes.values():
                if not node.is_healthy(self._heartbeat_timeout):
                    if node.status != NodeStatus.OFFLINE:
                        node.status = NodeStatus.OFFLINE
                        unhealthy.append(node)
        
        for node in unhealthy:
            logger.warning(f"Node marked unhealthy: {node.node_id}")
            if self._on_node_left:
                self._on_node_left(node)
        
        return {
            "total": len(self._nodes),
            "healthy": len(self.list_healthy_nodes()),
            "unhealthy": len(unhealthy),
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """获取集群统计"""
        nodes = list(self._nodes.values())
        healthy = [n for n in nodes if n.is_healthy(self._heartbeat_timeout)]
        
        return {
            "total_nodes": len(nodes),
            "healthy_nodes": len(healthy),
            "total_capacity": sum(n.capacity for n in healthy),
            "total_load": sum(n.current_load for n in healthy),
            "by_status": {
                status.value: len([n for n in nodes if n.status == status])
                for status in NodeStatus
            },
        }
    
    def set_callbacks(
        self,
        on_joined: Optional[Callable[[NodeInfo], None]] = None,
        on_left: Optional[Callable[[NodeInfo], None]] = None,
        on_leader_changed: Optional[Callable[[Optional[NodeInfo]], None]] = None,
    ) -> None:
        """设置回调"""
        self._on_node_joined = on_joined
        self._on_node_left = on_left
        self._on_leader_changed = on_leader_changed


# ── Leader Election ────────────────────────────────────────────────────────────

class LeaderElection:
    """
    主节点选举
    
    基于租约的实现:
    - 获取租约的节点成为 Leader
    - 租约过期后自动重新选举
    - 支持优雅降级
    """
    
    def __init__(
        self,
        node_id: str,
        lease_duration: int = 10,  # 秒
    ):
        self.node_id = node_id
        self.lease_duration = lease_duration
        self._leader_id: Optional[str] = None
        self._lease_expires: Optional[datetime] = None
        self._lock = threading.Lock()
        self._on_elected: Optional[Callable[[], None]] = None
        self._on_demoted: Optional[Callable[[], None]] = None
    
    def try_acquire_leadership(self) -> bool:
        """尝试获取领导权"""
        now = datetime.now(timezone.utc)
        
        with self._lock:
            # 检查当前 leader
            if self._leader_id and self._lease_expires:
                if self._lease_expires > now:
                    # Lease still valid
                    return self._leader_id == self.node_id
                else:
                    # Lease expired
                    logger.info(f"Leader lease expired: {self._leader_id}")
                    self._leader_id = None
            
            # Try to become leader
            # 简单实现: 先到先得 (生产环境应使用 Redis/ZooKeeper)
            self._leader_id = self.node_id
            self._lease_expires = now + timedelta(seconds=self.lease_duration)
            
            logger.info(f"Node {self.node_id} became leader")
            
            if self._on_elected:
                self._on_elected()
            
            return True
    
    def renew_lease(self) -> bool:
        """续约租约"""
        with self._lock:
            if self._leader_id != self.node_id:
                return False
            
            self._lease_expires = datetime.now(timezone.utc) + timedelta(
                seconds=self.lease_duration
            )
            return True
    
    def release_leadership(self) -> None:
        """释放领导权"""
        with self._lock:
            if self._leader_id == self.node_id:
                logger.info(f"Node {self.node_id} released leadership")
                self._leader_id = None
                self._lease_expires = None
                
                if self._on_demoted:
                    self._on_demoted()
    
    def is_leader(self) -> bool:
        """检查当前节点是否为 Leader"""
        with self._lock:
            if self._leader_id != self.node_id:
                return False
            if self._lease_expires and self._lease_expires > datetime.now(timezone.utc):
                return True
            return False
    
    def get_leader(self) -> Optional[str]:
        """获取当前 Leader ID"""
        with self._lock:
            if self._lease_expires and self._lease_expires > datetime.now(timezone.utc):
                return self._leader_id
            return None
    
    def set_callbacks(
        self,
        on_elected: Optional[Callable[[], None]] = None,
        on_demoted: Optional[Callable[[], None]] = None,
    ) -> None:
        """设置回调"""
        self._on_elected = on_elected
        self._on_demoted = on_demoted


# ── Distributed Lock ───────────────────────────────────────────────────────────

class DistributedLock:
    """
    分布式锁
    
    简单的内存实现，生产环境应使用 Redis 或其他分布式存储。
    """
    
    def __init__(self, name: str, ttl: int = 30):
        self.name = name
        self.ttl = ttl
        self._holder: Optional[str] = None
        self._expires: Optional[datetime] = None
        self._lock = threading.Lock()
    
    def acquire(self, holder_id: Optional[str] = None, wait: bool = False, timeout: float = 5.0) -> bool:
        """
        获取锁
        
        Args:
            holder_id: 持有者 ID
            wait: 是否等待
            timeout: 等待超时 (秒)
        
        Returns:
            是否成功获取
        """
        holder_id = holder_id or str(uuid.uuid4())
        start_time = time.time()
        
        while True:
            with self._lock:
                now = datetime.now(timezone.utc)
                
                # Check if lock is available
                if self._expires and self._expires < now:
                    # Lock expired
                    self._holder = None
                    self._expires = None
                
                if self._holder is None:
                    # Acquire lock
                    self._holder = holder_id
                    self._expires = now + timedelta(seconds=self.ttl)
                    return True
                
                if self._holder == holder_id:
                    # Re-entrant
                    self._expires = now + timedelta(seconds=self.ttl)
                    return True
            
            if not wait:
                return False
            
            if time.time() - start_time > timeout:
                return False
            
            time.sleep(0.1)
    
    def release(self, holder_id: Optional[str] = None) -> bool:
        """释放锁"""
        with self._lock:
            if holder_id and self._holder != holder_id:
                return False
            
            self._holder = None
            self._expires = None
            return True
    
    def is_locked(self) -> bool:
        """检查锁状态"""
        with self._lock:
            if self._expires and self._expires > datetime.now(timezone.utc):
                return True
            return False


class LockManager:
    """锁管理器"""
    
    def __init__(self):
        self._locks: Dict[str, DistributedLock] = {}
        self._lock = threading.Lock()
    
    def get_lock(self, name: str, ttl: int = 30) -> DistributedLock:
        """获取或创建锁"""
        with self._lock:
            if name not in self._locks:
                self._locks[name] = DistributedLock(name, ttl)
            return self._locks[name]


# ── Task Distribution ──────────────────────────────────────────────────────────

class TaskDistributionStrategy(str, Enum):
    """任务分发策略"""
    ROUND_ROBIN = "round_robin"
    LEAST_LOADED = "least_loaded"
    RANDOM = "random"
    CONSISTENT_HASH = "consistent_hash"


class TaskDistributor:
    """
    任务分发器
    
    根据策略将任务分配到不同节点
    """
    
    def __init__(
        self,
        registry: NodeRegistry,
        strategy: TaskDistributionStrategy = TaskDistributionStrategy.LEAST_LOADED,
    ):
        self.registry = registry
        self.strategy = strategy
        self._round_robin_index = 0
        self._lock = threading.Lock()
    
    def select_node(self, task_id: Optional[str] = None) -> Optional[NodeInfo]:
        """
        选择执行任务的节点
        
        Args:
            task_id: 任务 ID (用于一致性哈希)
        
        Returns:
            选中的节点，如果没有可用节点则返回 None
        """
        nodes = self.registry.list_healthy_nodes()
        
        # Filter nodes with available capacity
        available = [n for n in nodes if n.available_capacity() > 0]
        
        if not available:
            return None
        
        if self.strategy == TaskDistributionStrategy.ROUND_ROBIN:
            return self._select_round_robin(available)
        elif self.strategy == TaskDistributionStrategy.LEAST_LOADED:
            return self._select_least_loaded(available)
        elif self.strategy == TaskDistributionStrategy.RANDOM:
            return random.choice(available)
        elif self.strategy == TaskDistributionStrategy.CONSISTENT_HASH:
            return self._select_consistent_hash(available, task_id)
        else:
            return available[0]
    
    def _select_round_robin(self, nodes: List[NodeInfo]) -> NodeInfo:
        """轮询选择"""
        with self._lock:
            node = nodes[self._round_robin_index % len(nodes)]
            self._round_robin_index += 1
            return node
    
    def _select_least_loaded(self, nodes: List[NodeInfo]) -> NodeInfo:
        """选择负载最低的节点"""
        return min(nodes, key=lambda n: n.current_load / n.capacity if n.capacity > 0 else 0)
    
    def _select_consistent_hash(self, nodes: List[NodeInfo], task_id: Optional[str]) -> NodeInfo:
        """一致性哈希选择"""
        if not task_id:
            return nodes[0]
        
        # Simple hash-based selection
        hash_val = hash(task_id)
        return nodes[hash_val % len(nodes)]
    
    def distribute(self, task: Dict[str, Any], task_id: Optional[str] = None) -> Optional[str]:
        """
        分发任务到节点
        
        Returns:
            目标节点 ID
        """
        node = self.select_node(task_id)
        if node:
            logger.debug(f"Task {task_id or 'unknown'} assigned to node {node.node_id}")
            return node.node_id
        return None
