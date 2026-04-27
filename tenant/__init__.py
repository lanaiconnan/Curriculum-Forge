"""
Multi-tenancy Support

提供租户隔离、资源配额、使用统计等功能。

架构:
- TenantRegistry: 租户注册与管理
- TenantContext: 请求级别的租户上下文
- TenantQuota: 租户资源配额管理
- TenantMetrics: 租户使用统计
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

logger = logging.getLogger("tenant")

# ── Data Classes ───────────────────────────────────────────────────────────────

class TenantStatus(str, Enum):
    """租户状态"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TRIAL = "trial"
    EXPIRED = "expired"


@dataclass
class TenantQuota:
    """租户资源配额"""
    max_agents: int = 10
    max_jobs_per_day: int = 1000
    max_concurrent_jobs: int = 10
    max_storage_mb: int = 1024  # 1GB
    max_api_calls_per_hour: int = 10000
    features: List[str] = field(default_factory=lambda: ["basic"])
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_agents": self.max_agents,
            "max_jobs_per_day": self.max_jobs_per_day,
            "max_concurrent_jobs": self.max_concurrent_jobs,
            "max_storage_mb": self.max_storage_mb,
            "max_api_calls_per_hour": self.max_api_calls_per_hour,
            "features": self.features,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TenantQuota":
        return cls(
            max_agents=data.get("max_agents", 10),
            max_jobs_per_day=data.get("max_jobs_per_day", 1000),
            max_concurrent_jobs=data.get("max_concurrent_jobs", 10),
            max_storage_mb=data.get("max_storage_mb", 1024),
            max_api_calls_per_hour=data.get("max_api_calls_per_hour", 10000),
            features=data.get("features", ["basic"]),
        )


@dataclass
class TenantUsage:
    """租户使用统计"""
    jobs_today: int = 0
    jobs_total: int = 0
    concurrent_jobs: int = 0
    storage_used_mb: float = 0.0
    api_calls_this_hour: int = 0
    last_reset: Optional[datetime] = None
    last_hour_reset: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "jobs_today": self.jobs_today,
            "jobs_total": self.jobs_total,
            "concurrent_jobs": self.concurrent_jobs,
            "storage_used_mb": self.storage_used_mb,
            "api_calls_this_hour": self.api_calls_this_hour,
            "last_reset": self.last_reset.isoformat() if self.last_reset else None,
            "last_hour_reset": self.last_hour_reset.isoformat() if self.last_hour_reset else None,
        }
    
    def reset_daily(self) -> None:
        """重置每日统计"""
        self.jobs_today = 0
        self.last_reset = datetime.now(timezone.utc)
    
    def reset_hourly(self) -> None:
        """重置每小时统计"""
        self.api_calls_this_hour = 0
        self.last_hour_reset = datetime.now(timezone.utc)


@dataclass
class Tenant:
    """租户实体"""
    tenant_id: str
    name: str
    status: TenantStatus = TenantStatus.ACTIVE
    quota: TenantQuota = field(default_factory=TenantQuota)
    usage: TenantUsage = field(default_factory=TenantUsage)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "name": self.name,
            "status": self.status.value,
            "quota": self.quota.to_dict(),
            "usage": self.usage.to_dict(),
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
    
    def is_active(self) -> bool:
        """检查租户是否活跃"""
        if self.status == TenantStatus.SUSPENDED:
            return False
        if self.status == TenantStatus.EXPIRED:
            return False
        if self.expires_at and datetime.now(timezone.utc) > self.expires_at:
            self.status = TenantStatus.EXPIRED
            return False
        return True
    
    def can_create_job(self) -> bool:
        """检查是否可以创建新任务"""
        if not self.is_active():
            return False
        if self.usage.jobs_today >= self.quota.max_jobs_per_day:
            return False
        if self.usage.concurrent_jobs >= self.quota.max_concurrent_jobs:
            return False
        return True
    
    def can_register_agent(self, current_agents: int) -> bool:
        """检查是否可以注册新Agent"""
        if not self.is_active():
            return False
        return current_agents < self.quota.max_agents
    
    def can_call_api(self) -> bool:
        """检查是否可以调用API"""
        if not self.is_active():
            return False
        return self.usage.api_calls_this_hour < self.quota.max_api_calls_per_hour
    
    def has_feature(self, feature: str) -> bool:
        """检查是否有特定功能"""
        return feature in self.quota.features or "all" in self.quota.features


# ── Tenant Registry ────────────────────────────────────────────────────────────

class TenantRegistry:
    """
    租户注册表
    
    管理所有租户的生命周期、配额和使用统计。
    线程安全，支持回调通知。
    """
    
    _instance: Optional["TenantRegistry"] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> "TenantRegistry":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._tenants: Dict[str, Tenant] = {}
        self._tenant_locks: Dict[str, threading.Lock] = {}
        self._on_tenant_created: Optional[Callable[[Tenant], None]] = None
        self._on_tenant_updated: Optional[Callable[[Tenant], None]] = None
        self._on_tenant_suspended: Optional[Callable[[Tenant], None]] = None
        logger.info("TenantRegistry initialized")
    
    @classmethod
    def reset_singleton(cls) -> None:
        """重置单例（测试用）"""
        with cls._lock:
            cls._instance = None
    
    def _get_tenant_lock(self, tenant_id: str) -> threading.Lock:
        """获取租户级别的锁"""
        if tenant_id not in self._tenant_locks:
            self._tenant_locks[tenant_id] = threading.Lock()
        return self._tenant_locks[tenant_id]
    
    # ── CRUD Operations ───────────────────────────────────────────────────────
    
    def create_tenant(
        self,
        name: str,
        quota: Optional[TenantQuota] = None,
        metadata: Optional[Dict[str, Any]] = None,
        trial_days: Optional[int] = None,
    ) -> Tenant:
        """创建新租户"""
        tenant_id = f"tenant_{uuid.uuid4().hex[:12]}"
        
        status = TenantStatus.TRIAL if trial_days else TenantStatus.ACTIVE
        expires_at = None
        if trial_days:
            from datetime import timedelta
            expires_at = datetime.now(timezone.utc) + timedelta(days=trial_days)
        
        tenant = Tenant(
            tenant_id=tenant_id,
            name=name,
            status=status,
            quota=quota or TenantQuota(),
            metadata=metadata or {},
            expires_at=expires_at,
        )
        
        with self._get_tenant_lock(tenant_id):
            self._tenants[tenant_id] = tenant
        
        logger.info(f"Created tenant: {tenant_id} ({name})")
        
        if self._on_tenant_created:
            self._on_tenant_created(tenant)
        
        return tenant
    
    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """获取租户"""
        return self._tenants.get(tenant_id)
    
    def update_tenant(
        self,
        tenant_id: str,
        name: Optional[str] = None,
        quota: Optional[TenantQuota] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Tenant]:
        """更新租户信息"""
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return None
        
        with self._get_tenant_lock(tenant_id):
            if name is not None:
                tenant.name = name
            if quota is not None:
                tenant.quota = quota
            if metadata is not None:
                tenant.metadata.update(metadata)
        
        if self._on_tenant_updated:
            self._on_tenant_updated(tenant)
        
        return tenant
    
    def delete_tenant(self, tenant_id: str) -> bool:
        """删除租户"""
        if tenant_id not in self._tenants:
            return False
        
        with self._get_tenant_lock(tenant_id):
            del self._tenants[tenant_id]
            if tenant_id in self._tenant_locks:
                del self._tenant_locks[tenant_id]
        
        logger.info(f"Deleted tenant: {tenant_id}")
        return True
    
    def suspend_tenant(self, tenant_id: str, reason: str = "") -> bool:
        """暂停租户"""
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return False
        
        tenant.status = TenantStatus.SUSPENDED
        tenant.metadata["suspension_reason"] = reason
        tenant.metadata["suspended_at"] = datetime.now(timezone.utc).isoformat()
        
        logger.warning(f"Suspended tenant: {tenant_id} - {reason}")
        
        if self._on_tenant_suspended:
            self._on_tenant_suspended(tenant)
        
        return True
    
    def activate_tenant(self, tenant_id: str) -> bool:
        """激活租户"""
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return False
        
        tenant.status = TenantStatus.ACTIVE
        if "suspension_reason" in tenant.metadata:
            del tenant.metadata["suspension_reason"]
        if "suspended_at" in tenant.metadata:
            del tenant.metadata["suspended_at"]
        
        logger.info(f"Activated tenant: {tenant_id}")
        return True
    
    def list_tenants(
        self,
        status: Optional[TenantStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Tenant]:
        """列出租户"""
        tenants = list(self._tenants.values())
        
        if status:
            tenants = [t for t in tenants if t.status == status]
        
        return tenants[offset:offset + limit]
    
    # ── Usage Tracking ─────────────────────────────────────────────────────────
    
    def record_job_created(self, tenant_id: str) -> bool:
        """记录任务创建"""
        tenant = self._tenants.get(tenant_id)
        if not tenant or not tenant.can_create_job():
            return False
        
        with self._get_tenant_lock(tenant_id):
            tenant.usage.jobs_today += 1
            tenant.usage.jobs_total += 1
            tenant.usage.concurrent_jobs += 1
        
        return True
    
    def record_job_completed(self, tenant_id: str) -> None:
        """记录任务完成"""
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return
        
        with self._get_tenant_lock(tenant_id):
            tenant.usage.concurrent_jobs = max(0, tenant.usage.concurrent_jobs - 1)
    
    def record_api_call(self, tenant_id: str) -> bool:
        """记录API调用"""
        tenant = self._tenants.get(tenant_id)
        if not tenant or not tenant.can_call_api():
            return False
        
        with self._get_tenant_lock(tenant_id):
            tenant.usage.api_calls_this_hour += 1
        
        return True
    
    def update_storage_usage(self, tenant_id: str, mb: float) -> None:
        """更新存储使用"""
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return
        
        with self._get_tenant_lock(tenant_id):
            tenant.usage.storage_used_mb = mb
    
    def check_and_reset_counters(self) -> None:
        """检查并重置计数器（定时任务调用）"""
        now = datetime.now(timezone.utc)
        
        for tenant in self._tenants.values():
            # 每日重置
            if tenant.usage.last_reset:
                if tenant.usage.last_reset.date() < now.date():
                    tenant.usage.reset_daily()
            else:
                tenant.usage.reset_daily()
            
            # 每小时重置
            if tenant.usage.last_hour_reset:
                hours_diff = (now - tenant.usage.last_hour_reset).total_seconds() / 3600
                if hours_diff >= 1:
                    tenant.usage.reset_hourly()
            else:
                tenant.usage.reset_hourly()
    
    # ── Callbacks ─────────────────────────────────────────────────────────────
    
    def set_callbacks(
        self,
        on_created: Optional[Callable[[Tenant], None]] = None,
        on_updated: Optional[Callable[[Tenant], None]] = None,
        on_suspended: Optional[Callable[[Tenant], None]] = None,
    ) -> None:
        """设置回调函数"""
        self._on_tenant_created = on_created
        self._on_tenant_updated = on_updated
        self._on_tenant_suspended = on_suspended
    
    # ── Statistics ─────────────────────────────────────────────────────────────
    
    def get_stats(self) -> Dict[str, Any]:
        """获取全局统计"""
        tenants = list(self._tenants.values())
        
        return {
            "total_tenants": len(tenants),
            "by_status": {
                status.value: len([t for t in tenants if t.status == status])
                for status in TenantStatus
            },
            "total_jobs": sum(t.usage.jobs_total for t in tenants),
            "total_storage_mb": sum(t.usage.storage_used_mb for t in tenants),
        }


# ── Tenant Context ─────────────────────────────────────────────────────────────

class TenantContext:
    """
    租户上下文
    
    用于请求级别的租户信息传递。
    配合 FastAPI Depends 使用。
    """
    
    _current: threading.local = threading.local()
    
    @classmethod
    def set(cls, tenant: Optional[Tenant]) -> None:
        """设置当前租户"""
        cls._current.tenant = tenant
    
    @classmethod
    def get(cls) -> Optional[Tenant]:
        """获取当前租户"""
        return getattr(cls._current, "tenant", None)
    
    @classmethod
    def get_id(cls) -> Optional[str]:
        """获取当前租户ID"""
        tenant = cls.get()
        return tenant.tenant_id if tenant else None
    
    @classmethod
    def require(cls) -> Tenant:
        """获取当前租户（必须存在）"""
        tenant = cls.get()
        if not tenant:
            raise ValueError("No tenant in context")
        return tenant
    
    @classmethod
    def clear(cls) -> None:
        """清除当前租户"""
        if hasattr(cls._current, "tenant"):
            del cls._current.tenant


# ── Convenience Functions ─────────────────────────────────────────────────────

def get_tenant_registry() -> TenantRegistry:
    """获取租户注册表实例"""
    return TenantRegistry()


# ── Re-exports from middleware ───────────────────────────────────────────────

from tenant.middleware import (
    TenantMiddleware,
    get_current_tenant,
    require_tenant,
    check_tenant_feature,
)
