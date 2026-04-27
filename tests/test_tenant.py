"""
Tests for Multi-tenancy Support
"""

import pytest
import threading
from datetime import datetime, timezone, timedelta

from tenant import (
    TenantStatus,
    TenantQuota,
    TenantUsage,
    Tenant,
    TenantRegistry,
    TenantContext,
)


class TestTenantQuota:
    """测试租户配额"""
    
    def test_default_quota(self):
        """测试默认配额"""
        quota = TenantQuota()
        assert quota.max_agents == 10
        assert quota.max_jobs_per_day == 1000
        assert quota.max_concurrent_jobs == 10
        assert quota.max_storage_mb == 1024
        assert "basic" in quota.features
    
    def test_custom_quota(self):
        """测试自定义配额"""
        quota = TenantQuota(
            max_agents=100,
            max_jobs_per_day=10000,
            features=["basic", "advanced", "analytics"],
        )
        assert quota.max_agents == 100
        assert len(quota.features) == 3
    
    def test_quota_serialization(self):
        """测试配额序列化"""
        quota = TenantQuota(max_agents=50)
        data = quota.to_dict()
        
        restored = TenantQuota.from_dict(data)
        assert restored.max_agents == 50
        assert restored.max_jobs_per_day == quota.max_jobs_per_day


class TestTenantUsage:
    """测试租户使用统计"""
    
    def test_default_usage(self):
        """测试默认使用量"""
        usage = TenantUsage()
        assert usage.jobs_today == 0
        assert usage.concurrent_jobs == 0
    
    def test_reset_daily(self):
        """测试每日重置"""
        usage = TenantUsage(jobs_today=100)
        usage.reset_daily()
        
        assert usage.jobs_today == 0
        assert usage.last_reset is not None
    
    def test_reset_hourly(self):
        """测试每小时重置"""
        usage = TenantUsage(api_calls_this_hour=500)
        usage.reset_hourly()
        
        assert usage.api_calls_this_hour == 0
        assert usage.last_hour_reset is not None


class TestTenant:
    """测试租户实体"""
    
    def test_tenant_creation(self):
        """测试创建租户"""
        tenant = Tenant(
            tenant_id="tenant_001",
            name="Test Company",
        )
        
        assert tenant.tenant_id == "tenant_001"
        assert tenant.name == "Test Company"
        assert tenant.status == TenantStatus.ACTIVE
        assert tenant.is_active()
    
    def test_tenant_expiry(self):
        """测试租户过期"""
        tenant = Tenant(
            tenant_id="tenant_002",
            name="Expired Company",
            status=TenantStatus.TRIAL,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        
        # 检查过期会自动更新状态
        assert not tenant.is_active()
        assert tenant.status == TenantStatus.EXPIRED
    
    def test_can_create_job(self):
        """测试任务创建检查"""
        tenant = Tenant(tenant_id="t1", name="Test")
        
        # 正常情况
        assert tenant.can_create_job()
        
        # 达到每日限制
        tenant.usage.jobs_today = tenant.quota.max_jobs_per_day
        assert not tenant.can_create_job()
        
        # 重置
        tenant.usage.jobs_today = 0
        
        # 达到并发限制
        tenant.usage.concurrent_jobs = tenant.quota.max_concurrent_jobs
        assert not tenant.can_create_job()
    
    def test_can_register_agent(self):
        """测试Agent注册检查"""
        tenant = Tenant(tenant_id="t1", name="Test")
        
        assert tenant.can_register_agent(5)
        assert not tenant.can_register_agent(10)  # 达到上限
    
    def test_has_feature(self):
        """测试功能检查"""
        tenant = Tenant(
            tenant_id="t1",
            name="Test",
            quota=TenantQuota(features=["basic", "analytics"]),
        )
        
        assert tenant.has_feature("basic")
        assert tenant.has_feature("analytics")
        assert not tenant.has_feature("enterprise")
    
    def test_all_features(self):
        """测试所有功能权限"""
        tenant = Tenant(
            tenant_id="t1",
            name="Test",
            quota=TenantQuota(features=["all"]),
        )
        
        assert tenant.has_feature("any_feature")
        assert tenant.has_feature("enterprise")


class TestTenantRegistry:
    """测试租户注册表"""
    
    def setup_method(self):
        """每个测试前重置单例"""
        TenantRegistry.reset_singleton()
    
    def test_singleton(self):
        """测试单例模式"""
        r1 = TenantRegistry()
        r2 = TenantRegistry()
        
        assert r1 is r2
    
    def test_create_tenant(self):
        """测试创建租户"""
        registry = TenantRegistry()
        tenant = registry.create_tenant(name="Test Company")
        
        assert tenant.tenant_id.startswith("tenant_")
        assert tenant.name == "Test Company"
        assert tenant.status == TenantStatus.ACTIVE
    
    def test_create_trial_tenant(self):
        """测试创建试用租户"""
        registry = TenantRegistry()
        tenant = registry.create_tenant(name="Trial Company", trial_days=14)
        
        assert tenant.status == TenantStatus.TRIAL
        assert tenant.expires_at is not None
        assert tenant.expires_at > datetime.now(timezone.utc)
    
    def test_get_tenant(self):
        """测试获取租户"""
        registry = TenantRegistry()
        created = registry.create_tenant(name="Test")
        
        fetched = registry.get_tenant(created.tenant_id)
        assert fetched is created
    
    def test_update_tenant(self):
        """测试更新租户"""
        registry = TenantRegistry()
        tenant = registry.create_tenant(name="Old Name")
        
        updated = registry.update_tenant(
            tenant.tenant_id,
            name="New Name",
            metadata={"key": "value"},
        )
        
        assert updated.name == "New Name"
        assert updated.metadata["key"] == "value"
    
    def test_delete_tenant(self):
        """测试删除租户"""
        registry = TenantRegistry()
        tenant = registry.create_tenant(name="Test")
        
        assert registry.delete_tenant(tenant.tenant_id)
        assert registry.get_tenant(tenant.tenant_id) is None
    
    def test_suspend_tenant(self):
        """测试暂停租户"""
        registry = TenantRegistry()
        tenant = registry.create_tenant(name="Test")
        
        assert registry.suspend_tenant(tenant.tenant_id, "Payment overdue")
        
        fetched = registry.get_tenant(tenant.tenant_id)
        assert fetched.status == TenantStatus.SUSPENDED
        assert not fetched.is_active()
        assert "Payment overdue" in fetched.metadata["suspension_reason"]
    
    def test_activate_tenant(self):
        """测试激活租户"""
        registry = TenantRegistry()
        tenant = registry.create_tenant(name="Test")
        
        registry.suspend_tenant(tenant.tenant_id)
        assert registry.activate_tenant(tenant.tenant_id)
        
        fetched = registry.get_tenant(tenant.tenant_id)
        assert fetched.status == TenantStatus.ACTIVE
        assert fetched.is_active()
    
    def test_list_tenants(self):
        """测试列出租户"""
        registry = TenantRegistry()
        
        registry.create_tenant(name="Active 1")
        registry.create_tenant(name="Active 2")
        tenant = registry.create_tenant(name="Suspended")
        registry.suspend_tenant(tenant.tenant_id)
        
        all_tenants = registry.list_tenants()
        assert len(all_tenants) == 3
        
        active_only = registry.list_tenants(status=TenantStatus.ACTIVE)
        assert len(active_only) == 2
    
    def test_list_tenants_pagination(self):
        """测试分页"""
        registry = TenantRegistry()
        
        for i in range(5):
            registry.create_tenant(name=f"Tenant {i}")
        
        page1 = registry.list_tenants(limit=2, offset=0)
        page2 = registry.list_tenants(limit=2, offset=2)
        
        assert len(page1) == 2
        assert len(page2) == 2


class TestTenantRegistryUsage:
    """测试租户使用统计"""
    
    def setup_method(self):
        TenantRegistry.reset_singleton()
    
    def test_record_job_created(self):
        """测试记录任务创建"""
        registry = TenantRegistry()
        tenant = registry.create_tenant(name="Test")
        
        # 成功创建
        assert registry.record_job_created(tenant.tenant_id)
        
        fetched = registry.get_tenant(tenant.tenant_id)
        assert fetched.usage.jobs_today == 1
        assert fetched.usage.concurrent_jobs == 1
    
    def test_record_job_exceeds_quota(self):
        """测试超过配额"""
        registry = TenantRegistry()
        tenant = registry.create_tenant(name="Test")
        tenant.quota.max_jobs_per_day = 1
        
        # 第一次成功
        assert registry.record_job_created(tenant.tenant_id)
        # 第二次失败
        assert not registry.record_job_created(tenant.tenant_id)
    
    def test_record_job_completed(self):
        """测试记录任务完成"""
        registry = TenantRegistry()
        tenant = registry.create_tenant(name="Test")
        
        registry.record_job_created(tenant.tenant_id)
        assert tenant.usage.concurrent_jobs == 1
        
        registry.record_job_completed(tenant.tenant_id)
        assert tenant.usage.concurrent_jobs == 0
    
    def test_record_api_call(self):
        """测试记录API调用"""
        registry = TenantRegistry()
        tenant = registry.create_tenant(name="Test")
        
        assert registry.record_api_call(tenant.tenant_id)
        assert tenant.usage.api_calls_this_hour == 1
    
    def test_update_storage_usage(self):
        """测试更新存储使用"""
        registry = TenantRegistry()
        tenant = registry.create_tenant(name="Test")
        
        registry.update_storage_usage(tenant.tenant_id, 512.5)
        assert tenant.usage.storage_used_mb == 512.5


class TestTenantRegistryCallbacks:
    """测试回调"""
    
    def setup_method(self):
        TenantRegistry.reset_singleton()
    
    def test_on_tenant_created(self):
        """测试创建回调"""
        registry = TenantRegistry()
        created_tenants = []
        
        def on_created(t):
            created_tenants.append(t)
        
        registry.set_callbacks(on_created=on_created)
        tenant = registry.create_tenant(name="Test")
        
        assert len(created_tenants) == 1
        assert created_tenants[0] is tenant
    
    def test_on_tenant_suspended(self):
        """测试暂停回调"""
        registry = TenantRegistry()
        suspended_tenants = []
        
        def on_suspended(t):
            suspended_tenants.append(t)
        
        registry.set_callbacks(on_suspended=on_suspended)
        tenant = registry.create_tenant(name="Test")
        registry.suspend_tenant(tenant.tenant_id)
        
        assert len(suspended_tenants) == 1


class TestTenantContext:
    """测试租户上下文"""
    
    def test_set_and_get(self):
        """测试设置和获取"""
        tenant = Tenant(tenant_id="t1", name="Test")
        
        TenantContext.set(tenant)
        assert TenantContext.get() is tenant
        assert TenantContext.get_id() == "t1"
        
        TenantContext.clear()
        assert TenantContext.get() is None
    
    def test_require(self):
        """测试必须存在"""
        tenant = Tenant(tenant_id="t1", name="Test")
        
        TenantContext.set(tenant)
        assert TenantContext.require() is tenant
        
        TenantContext.clear()
        
        with pytest.raises(ValueError, match="No tenant in context"):
            TenantContext.require()


class TestTenantRegistryStats:
    """测试全局统计"""
    
    def setup_method(self):
        TenantRegistry.reset_singleton()
    
    def test_get_stats(self):
        """测试获取统计"""
        registry = TenantRegistry()
        
        registry.create_tenant(name="Active 1")
        registry.create_tenant(name="Active 2")
        tenant = registry.create_tenant(name="Suspended")
        registry.suspend_tenant(tenant.tenant_id)
        
        stats = registry.get_stats()
        
        assert stats["total_tenants"] == 3
        assert stats["by_status"]["active"] == 2
        assert stats["by_status"]["suspended"] == 1
