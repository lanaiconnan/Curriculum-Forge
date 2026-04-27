"""
Tests for Distributed Support
"""

import pytest
import threading
import time
from datetime import datetime, timezone, timedelta

from distributed import (
    NodeStatus,
    NodeInfo,
    NodeRegistry,
    LeaderElection,
    DistributedLock,
    LockManager,
    TaskDistributionStrategy,
    TaskDistributor,
)


class TestNodeInfo:
    """测试节点信息"""
    
    def test_node_creation(self):
        """测试创建节点"""
        node = NodeInfo(
            node_id="node_001",
            host="localhost",
            port=8765,
        )
        
        assert node.node_id == "node_001"
        assert node.host == "localhost"
        assert node.port == 8765
        assert node.status == NodeStatus.ACTIVE
        assert not node.is_leader
    
    def test_node_health(self):
        """测试健康检查"""
        node = NodeInfo(
            node_id="node_001",
            host="localhost",
            port=8765,
        )
        
        # 刚创建，健康
        assert node.is_healthy()
        
        # 心跳过期
        node.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=60)
        assert not node.is_healthy()
        
        # 离线状态
        node.status = NodeStatus.OFFLINE
        assert not node.is_healthy()
    
    def test_available_capacity(self):
        """测试可用容量"""
        node = NodeInfo(
            node_id="node_001",
            host="localhost",
            port=8765,
            capacity=100,
            current_load=30,
        )
        
        assert node.available_capacity() == 70
        
        # Draining 状态
        node.status = NodeStatus.DRAINING
        assert node.available_capacity() == 0
    
    def test_serialization(self):
        """测试序列化"""
        node = NodeInfo(
            node_id="node_001",
            host="localhost",
            port=8765,
        )
        
        data = node.to_dict()
        assert data["node_id"] == "node_001"
        assert data["load_pct"] == 0.0


class TestNodeRegistry:
    """测试节点注册表"""
    
    def test_register_node(self):
        """测试注册节点"""
        registry = NodeRegistry()
        node = registry.register(host="localhost", port=8765)
        
        assert node.node_id.startswith("node_")
        assert node.host == "localhost"
        
        # 可以获取
        fetched = registry.get_node(node.node_id)
        assert fetched is node
    
    def test_unregister_node(self):
        """测试注销节点"""
        registry = NodeRegistry()
        node = registry.register(host="localhost", port=8765)
        
        assert registry.unregister(node.node_id)
        assert registry.get_node(node.node_id) is None
    
    def test_heartbeat(self):
        """测试心跳"""
        registry = NodeRegistry()
        node = registry.register(host="localhost", port=8765)
        
        # 模拟时间流逝
        old_heartbeat = node.last_heartbeat
        time.sleep(0.1)
        
        assert registry.heartbeat(node.node_id, load=50)
        assert node.last_heartbeat > old_heartbeat
        assert node.current_load == 50
    
    def test_list_nodes(self):
        """测试列出节点"""
        registry = NodeRegistry()
        
        registry.register(host="node1", port=8765)
        registry.register(host="node2", port=8766)
        
        all_nodes = registry.list_nodes()
        assert len(all_nodes) == 2
    
    def test_check_health(self):
        """测试健康检查"""
        registry = NodeRegistry(heartbeat_timeout=1)
        
        node = registry.register(host="localhost", port=8765)
        
        # 初始健康
        health = registry.check_health()
        assert health["healthy"] == 1
        
        # 模拟心跳过期
        node.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=10)
        
        health = registry.check_health()
        assert health["unhealthy"] == 1
        assert node.status == NodeStatus.OFFLINE
    
    def test_callbacks(self):
        """测试回调"""
        registry = NodeRegistry()
        joined_nodes = []
        left_nodes = []
        
        def on_joined(n):
            joined_nodes.append(n)
        
        def on_left(n):
            left_nodes.append(n)
        
        registry.set_callbacks(on_joined=on_joined, on_left=on_left)
        
        node = registry.register(host="localhost", port=8765)
        assert len(joined_nodes) == 1
        
        registry.unregister(node.node_id)
        assert len(left_nodes) == 1


class TestLeaderElection:
    """测试主节点选举"""
    
    def test_acquire_leadership(self):
        """测试获取领导权"""
        election = LeaderElection(node_id="node_001", lease_duration=5)
        
        assert election.try_acquire_leadership()
        assert election.is_leader()
        assert election.get_leader() == "node_001"
    
    def test_renew_lease(self):
        """测试续约"""
        election = LeaderElection(node_id="node_001", lease_duration=1)
        
        election.try_acquire_leadership()
        assert election.renew_lease()
        assert election.is_leader()
    
    def test_lease_expiry(self):
        """测试租约过期"""
        election = LeaderElection(node_id="node_001", lease_duration=0)
        
        election.try_acquire_leadership()
        
        # 租约立即过期
        time.sleep(0.1)
        assert not election.is_leader()
    
    def test_release_leadership(self):
        """测试释放领导权"""
        election = LeaderElection(node_id="node_001", lease_duration=10)
        
        election.try_acquire_leadership()
        election.release_leadership()
        
        assert not election.is_leader()
        assert election.get_leader() is None
    
    def test_callbacks(self):
        """测试回调"""
        election = LeaderElection(node_id="node_001", lease_duration=10)
        elected_count = [0]
        demoted_count = [0]
        
        def on_elected():
            elected_count[0] += 1
        
        def on_demoted():
            demoted_count[0] += 1
        
        election.set_callbacks(on_elected=on_elected, on_demoted=on_demoted)
        
        election.try_acquire_leadership()
        assert elected_count[0] == 1
        
        election.release_leadership()
        assert demoted_count[0] == 1


class TestDistributedLock:
    """测试分布式锁"""
    
    def test_acquire_and_release(self):
        """测试获取和释放"""
        lock = DistributedLock("test_lock", ttl=10)
        
        assert lock.acquire(holder_id="holder_001")
        assert lock.is_locked()
        
        assert lock.release(holder_id="holder_001")
        assert not lock.is_locked()
    
    def test_reentrant(self):
        """测试可重入"""
        lock = DistributedLock("test_lock", ttl=10)
        
        assert lock.acquire(holder_id="holder_001")
        assert lock.acquire(holder_id="holder_001")  # Re-entrant
        
        lock.release(holder_id="holder_001")
    
    def test_lock_conflict(self):
        """测试锁冲突"""
        lock = DistributedLock("test_lock", ttl=10)
        
        assert lock.acquire(holder_id="holder_001")
        
        # 另一个 holder 无法获取
        assert not lock.acquire(holder_id="holder_002")
        
        lock.release(holder_id="holder_001")
    
    def test_lock_expiry(self):
        """测试锁过期"""
        lock = DistributedLock("test_lock", ttl=0)
        
        lock.acquire(holder_id="holder_001")
        
        # 等待过期
        time.sleep(0.1)
        
        # 锁已过期，可以获取
        assert lock.acquire(holder_id="holder_002")
    
    def test_wait_for_lock(self):
        """测试等待锁"""
        lock = DistributedLock("test_lock", ttl=10)
        
        # 持有锁
        lock.acquire(holder_id="holder_001")
        
        # 在另一个线程中等待
        result = [False]
        
        def try_acquire():
            result[0] = lock.acquire(holder_id="holder_002", wait=True, timeout=0.5)
        
        thread = threading.Thread(target=try_acquire)
        thread.start()
        
        # 短暂等待后释放
        time.sleep(0.1)
        lock.release(holder_id="holder_001")
        
        thread.join()
        assert result[0]


class TestLockManager:
    """测试锁管理器"""
    
    def test_get_lock(self):
        """测试获取锁"""
        manager = LockManager()
        
        lock1 = manager.get_lock("lock_1")
        lock2 = manager.get_lock("lock_2")
        lock1_again = manager.get_lock("lock_1")
        
        assert lock1 is lock1_again
        assert lock1 is not lock2


class TestTaskDistributor:
    """测试任务分发器"""
    
    def setup_method(self):
        """每个测试前清空"""
        self.registry = NodeRegistry()
    
    def test_select_least_loaded(self):
        """测试最少负载策略"""
        node1 = self.registry.register(host="node1", port=8765, capacity=100)
        node2 = self.registry.register(host="node2", port=8766, capacity=100)
        
        node1.current_load = 80
        node2.current_load = 20
        
        distributor = TaskDistributor(self.registry, TaskDistributionStrategy.LEAST_LOADED)
        
        selected = distributor.select_node()
        assert selected.node_id == node2.node_id
    
    def test_select_round_robin(self):
        """测试轮询策略"""
        self.registry.register(host="node1", port=8765)
        self.registry.register(host="node2", port=8766)
        
        distributor = TaskDistributor(self.registry, TaskDistributionStrategy.ROUND_ROBIN)
        
        # 轮询顺序
        selected1 = distributor.select_node()
        selected2 = distributor.select_node()
        selected3 = distributor.select_node()
        
        assert selected1.node_id != selected2.node_id
        assert selected1.node_id == selected3.node_id
    
    def test_no_available_nodes(self):
        """测试无可用节点"""
        node = self.registry.register(host="node1", port=8765, capacity=100)
        node.current_load = 100  # 满载
        
        distributor = TaskDistributor(self.registry)
        
        assert distributor.select_node() is None
    
    def test_distribute_task(self):
        """测试分发任务"""
        self.registry.register(host="node1", port=8765)
        
        distributor = TaskDistributor(self.registry)
        
        target = distributor.distribute({"task": "data"}, task_id="task_001")
        assert target is not None
