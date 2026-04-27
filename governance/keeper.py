"""
Keeper - 资源管理器

负责：
- Agent 注册与生命周期管理
- 资源配额分配
- 任务调度策略
- 健康检查与负载均衡
"""

import time
import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Callable, Any
from enum import Enum
from datetime import datetime
import logging

from governance.metrics import (
    track_agent_registered,
    track_agent_deregistered,
    track_task_assigned,
    KEEPER_RESOURCE_TOTAL,
    KEEPER_RESOURCE_USED,
    KEEPER_TASKS_REJECTED,
    KEEPER_HEALTH_CHECKS_TOTAL,
    KEEPER_AGENTS_UNHEALTHY,
)

logger = logging.getLogger(__name__)


class ResourceType(Enum):
    """资源类型"""
    CPU = "cpu"
    MEMORY = "memory"
    GPU = "gpu"
    API_CALLS = "api_calls"
    TASKS = "tasks"
    STORAGE = "storage"


class AgentStatus(Enum):
    """Agent 状态"""
    IDLE = "idle"
    BUSY = "busy"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"
    ERROR = "error"


@dataclass
class ResourceQuota:
    """资源配额"""
    resource_type: ResourceType
    total: float
    used: float = 0.0
    reserved: float = 0.0
    
    @property
    def available(self) -> float:
        return self.total - self.used - self.reserved
    
    @property
    def utilization(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.used + self.reserved) / self.total


@dataclass
class AgentProfile:
    """Agent 配置档案"""
    id: str
    name: str
    role: str  # teacher, learner, reviewer, etc.
    capabilities: Set[str] = field(default_factory=set)
    max_concurrent_tasks: int = 1
    
    # 资源配额
    quotas: Dict[ResourceType, ResourceQuota] = field(default_factory=dict)
    
    # 状态
    status: AgentStatus = AgentStatus.IDLE
    current_tasks: List[str] = field(default_factory=list)
    
    # 统计
    total_tasks_completed: int = 0
    total_tasks_failed: int = 0
    average_task_duration: float = 0.0
    last_heartbeat: Optional[datetime] = None
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_available(self) -> bool:
        """检查是否可接受新任务"""
        return (
            self.status == AgentStatus.IDLE and
            len(self.current_tasks) < self.max_concurrent_tasks and
            all(q.available > 0 for q in self.quotas.values())
        )
    
    def get_load(self) -> float:
        """获取当前负载 (0.0 - 1.0)"""
        if self.max_concurrent_tasks == 0:
            return 1.0
        return len(self.current_tasks) / self.max_concurrent_tasks


@dataclass
class SchedulingPolicy:
    """调度策略"""
    name: str
    priority: int = 0
    weight: float = 1.0
    constraints: Dict[str, Any] = field(default_factory=dict)
    
    # 策略类型
    strategy: str = "round_robin"  # round_robin, least_loaded, capability_match, priority
    
    def score_agent(self, agent: AgentProfile, task_requirements: Dict[str, Any] = None) -> float:
        """计算 agent 对任务的适配分数"""
        if not agent.is_available():
            return 0.0
        
        score = self.weight
        
        if self.strategy == "least_loaded":
            # 负载越低分数越高
            score *= (1.0 - agent.get_load())
        
        elif self.strategy == "capability_match":
            # 能力匹配度
            if task_requirements and "capabilities" in task_requirements:
                required = set(task_requirements["capabilities"])
                matched = len(required & agent.capabilities)
                total = len(required)
                if total > 0:
                    score *= matched / total
        
        elif self.strategy == "priority":
            # 优先级排序
            score *= (1.0 + agent.metadata.get("priority", 0) / 100.0)
        
        return score


class Keeper:
    """
    资源管理器
    
    负责 Agent 注册、资源配额、任务调度
    """
    
    def __init__(self, coordinator=None):
        self.coordinator = coordinator
        self._agents: Dict[str, AgentProfile] = {}
        self._policies: List[SchedulingPolicy] = []
        self._default_policy = SchedulingPolicy(
            name="default",
            strategy="least_loaded"
        )
        
        # 回调
        self._on_agent_registered: Optional[Callable] = None
        self._on_agent_unregistered: Optional[Callable] = None
        self._on_task_assigned: Optional[Callable] = None
        
        # 统计
        self._total_assignments = 0
        self._failed_assignments = 0
    
    # ════════════════════════════════════════════════════════════════════════
    # Agent 注册管理
    # ════════════════════════════════════════════════════════════════════════
    
    def register_agent(
        self,
        agent_id: str,
        name: str,
        role: str,
        capabilities: Optional[Set[str]] = None,
        max_concurrent_tasks: int = 1,
        quotas: Optional[Dict[ResourceType, ResourceQuota]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentProfile:
        """
        注册 Agent
        
        Args:
            agent_id: 唯一标识符
            name: 显示名称
            role: 角色 (teacher/learner/reviewer)
            capabilities: 能力集合
            max_concurrent_tasks: 最大并发任务数
            quotas: 资源配额
            metadata: 元数据
            
        Returns:
            AgentProfile
        """
        if agent_id in self._agents:
            logger.warning(f"Agent {agent_id} already registered, updating")
        
        profile = AgentProfile(
            id=agent_id,
            name=name,
            role=role,
            capabilities=capabilities or set(),
            max_concurrent_tasks=max_concurrent_tasks,
            quotas=quotas or {},
            metadata=metadata or {},
            last_heartbeat=datetime.now(),
        )
        
        self._agents[agent_id] = profile
        logger.info(f"Registered agent: {agent_id} ({role}) with capabilities: {capabilities}")
        
        # Metrics
        track_agent_registered(role, is_new=agent_id not in self._agents)
        
        # 回调
        if self._on_agent_registered:
            self._on_agent_registered(profile)
        
        return profile
    
    def unregister_agent(self, agent_id: str) -> bool:
        """注销 Agent"""
        if agent_id not in self._agents:
            return False
        
        profile = self._agents[agent_id]
        
        # 检查是否有正在执行的任务
        if profile.current_tasks:
            logger.warning(f"Agent {agent_id} has active tasks: {profile.current_tasks}")
            return False
        
        del self._agents[agent_id]
        logger.info(f"Unregistered agent: {agent_id}")
        
        # Metrics
        track_agent_deregistered(profile.role)
        
        # 回调
        if self._on_agent_unregistered:
            self._on_agent_unregistered(profile)
        
        return True
    
    def get_agent(self, agent_id: str) -> Optional[AgentProfile]:
        """获取 Agent 配置"""
        return self._agents.get(agent_id)
    
    def list_agents(
        self,
        role: Optional[str] = None,
        status: Optional[AgentStatus] = None,
        capability: Optional[str] = None,
    ) -> List[AgentProfile]:
        """列出 Agent"""
        agents = list(self._agents.values())
        
        if role:
            agents = [a for a in agents if a.role == role]
        if status:
            agents = [a for a in agents if a.status == status]
        if capability:
            agents = [a for a in agents if capability in a.capabilities]
        
        return agents
    
    def update_heartbeat(self, agent_id: str) -> bool:
        """更新心跳"""
        agent = self._agents.get(agent_id)
        if agent:
            agent.last_heartbeat = datetime.now()
            return True
        return False
    
    # ════════════════════════════════════════════════════════════════════════
    # 资源配额管理
    # ════════════════════════════════════════════════════════════════════════
    
    def set_quota(
        self,
        agent_id: str,
        resource_type: ResourceType,
        total: float,
    ) -> bool:
        """设置 Agent 资源配额"""
        agent = self._agents.get(agent_id)
        if not agent:
            return False
        
        agent.quotas[resource_type] = ResourceQuota(
            resource_type=resource_type,
            total=total,
        )
        logger.info(f"Set quota for {agent_id}: {resource_type.value}={total}")
        return True
    
    def reserve_resources(
        self,
        agent_id: str,
        resources: Dict[ResourceType, float],
    ) -> bool:
        """预留资源"""
        agent = self._agents.get(agent_id)
        if not agent:
            return False
        
        # 检查是否有足够资源
        for rtype, amount in resources.items():
            if rtype not in agent.quotas:
                continue
            if agent.quotas[rtype].available < amount:
                logger.warning(f"Insufficient {rtype.value} for {agent_id}")
                return False
        
        # 预留
        for rtype, amount in resources.items():
            if rtype in agent.quotas:
                agent.quotas[rtype].reserved += amount
        
        return True
    
    def release_resources(
        self,
        agent_id: str,
        resources: Dict[ResourceType, float],
    ) -> bool:
        """释放资源"""
        agent = self._agents.get(agent_id)
        if not agent:
            return False
        
        for rtype, amount in resources.items():
            if rtype in agent.quotas:
                agent.quotas[rtype].used = max(0, agent.quotas[rtype].used - amount)
                agent.quotas[rtype].reserved = max(0, agent.quotas[rtype].reserved - amount)
        
        return True
    
    def get_cluster_resources(self) -> Dict[ResourceType, Dict[str, float]]:
        """获取集群资源总览"""
        result = {}
        for rtype in ResourceType:
            total = sum(
                a.quotas.get(rtype, ResourceQuota(rtype, 0)).total
                for a in self._agents.values()
            )
            used = sum(
                a.quotas.get(rtype, ResourceQuota(rtype, 0)).used
                for a in self._agents.values()
            )
            reserved = sum(
                a.quotas.get(rtype, ResourceQuota(rtype, 0)).reserved
                for a in self._agents.values()
            )
            result[rtype] = {
                "total": total,
                "used": used,
                "reserved": reserved,
                "available": total - used - reserved,
            }
        return result
    
    # ═══════════════════════════════════════════════════ Agent: {agent.id} ({agent.role}), score: {score:.2f}")
        self._total_assignments += 1
        
        # 更新 agent 状态
        agent.current_tasks.append(task_id)
        if len(agent.current_tasks) >= agent.max_concurrent_tasks:
            agent.status = AgentStatus.BUSY
        
        # 回调
        if self._on_task_assigned:
            self._on_task_assigned(agent, task_id)
        
        return agent.id
    
    def release_task(self, agent_id: str, task_id: str, success: bool = True) -> bool:
        """释放任务"""
        agent = self._agents.get(agent_id)
        if not agent or task_id not in agent.current_tasks:
            return False
        
        agent.current_tasks.remove(task_id)
        agent.status = AgentStatus.IDLE
        
        if success:
            agent.total_tasks_completed += 1
        else:
            agent.total_tasks_failed += 1
        
        return True
    
    # ════════════════════════════════════════════════════════════════════════
    # 任务调度
    # ════════════════════════════════════════════════════════════════════════
    
    def add_policy(self, policy: SchedulingPolicy):
        """添加调度策略"""
        self._policies.append(policy)
        self._policies.sort(key=lambda p: p.priority, reverse=True)
    
    def assign_task(
        self,
        task_id: str,
        requirements: Optional[Dict[str, Any]] = None,
        role: Optional[str] = None,
    ) -> Optional[str]:
        """
        分配任务给最合适的 Agent
        
        Args:
            task_id: 任务 ID
            requirements: 任务需求（能力等）
            role: 指定角色
            
        Returns:
            分配的 agent_id，或 None（无可用 agent）
        """
        candidates = self.list_agents(status=AgentStatus.IDLE)
        
        # 过滤角色
        if role:
            candidates = [a for a in candidates if a.role == role]
        
        if not candidates:
            logger.warning(f"No available agents for task {task_id}")
            self._failed_assignments += 1
            KEEPER_TASKS_REJECTED.labels(reason='no_available_agent').inc()
            return None
        
        # 使用策略评分
        policy = self._policies[0] if self._policies else self._default_policy
        
        best_agent = None
        best_score = -1
        
        for agent in candidates:
            score = policy.score_agent(agent, requirements)
            if score > best_score:
                best_score = score
                best_agent = agent
        
        if not best_agent:
            self._failed_assignments += 1
            return None
        
        agent = best_agent
        logger.info(f"Assigned task {task_id} to Agent: {agent.id} ({agent.role}), score: {best_score:.2f}")
        self._total_assignments += 1
        
        # Metrics
        policy_name = policy.name if hasattr(policy, 'name') else 'default'
        track_task_assigned(agent.id, policy_name, 0.0)  # duration tracked externally
        
        # 更新 agent 状态
        agent.current_tasks.append(task_id)
        if len(agent.current_tasks) >= agent.max_concurrent_tasks:
            agent.status = AgentStatus.BUSY
        
        # 回调
        if self._on_task_assigned:
            self._on_task_assigned(agent, task_id)
        
        return agent.id
    
    def release_task(self, agent_id: str, task_id: str, success: bool = True) -> bool:
        """释放任务"""
        agent = self._agents.get(agent_id)
        if not agent or task_id not in agent.current_tasks:
            return False
        
        agent.current_tasks.remove(task_id)
        agent.status = AgentStatus.IDLE
        
        if success:
            agent.total_tasks_completed += 1
        else:
            agent.total_tasks_failed += 1
        
        return True
    
    # ════════════════════════════════════════════════════════════════════════
    # 健康检查
    # ════════════════════════════════════════════════════════════════════════
    
    async def health_check(self, timeout_seconds: int = 30) -> Dict[str, Any]:
        """
        执行健康检查
        
        Returns:
            健康状态报告
        """
        now = datetime.now()
        results = {
            "healthy": [],
            "unhealthy": [],
            "offline": [],
        }
        
        for agent in self._agents.values():
            if agent.status == AgentStatus.OFFLINE:
                results["offline"].append(agent.id)
                continue
            
            # 检查心跳
            if agent.last_heartbeat:
                elapsed = (now - agent.last_heartbeat).total_seconds()
                if elapsed > timeout_seconds:
                    results["unhealthy"].append({
                        "id": agent.id,
                        "reason": f"heartbeat_timeout ({elapsed:.1f}s)",
                    })
                    continue
            
            results["healthy"].append(agent.id)
        
        return {
            "timestamp": now.isoformat(),
            "total_agents": len(self._agents),
            "results": results,
            "healthy_count": len(results["healthy"]),
            "unhealthy_count": len(results["unhealthy"]),
            "offline_count": len(results["offline"]),
        }
    
    # ════════════════════════════════════════════════════════════════════════
    # 统计与监控
    # ════════════════════════════════════════════════════════════════════════
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        agents = list(self._agents.values())
        
        return {
            "total_agents": len(agents),
            "by_status": {
                status.value: len([a for a in agents if a.status == status])
                for status in AgentStatus
            },
            "by_role": self._count_by_role(),
            "resources": self.get_cluster_resources(),
            "assignments": {
                "total": self._total_assignments,
                "failed": self._failed_assignments,
                "success_rate": (
                    (self._total_assignments - self._failed_assignments) / self._total_assignments
                    if self._total_assignments > 0 else 0.0
                ),
            },
            "task_stats": {
                "completed": sum(a.total_tasks_completed for a in agents),
                "failed": sum(a.total_tasks_failed for a in agents),
            },
        }
    
    def _count_by_role(self) -> Dict[str, int]:
        """按角色统计"""
        counts = {}
        for agent in self._agents.values():
            counts[agent.role] = counts.get(agent.role, 0) + 1
        return counts
    
    # ════════════════════════════════════════════════════════════════════════
    # 回调设置
    # ════════════════════════════════════════════════════════════════════════
    
    def on_agent_registered(self, callback: Callable):
        """设置注册回调"""
        self._on_agent_registered = callback
    
    def on_agent_unregistered(self, callback: Callable):
        """设置注销回调"""
        self._on_agent_unregistered = callback
    
    def on_task_assigned(self, callback: Callable):
        """设置任务分配回调"""
        self._on_task_assigned = callback
