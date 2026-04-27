"""Plugin System Tests

Tests for the plugin system including:
- Plugin registration and lifecycle
- Hook dispatching
- Priority ordering
- Governance and knowledge hooks
"""

import pytest
from services.plugin_system import (
    Plugin,
    PluginMeta,
    PluginContext,
    PluginManager,
    PluginHook,
)


class MockPlugin(Plugin):
    """Test plugin for basic tests"""
    
    meta = PluginMeta(
        name="mock-plugin",
        version="1.0.0",
        description="Mock plugin for testing",
        hooks=["env:before_generate", "exp:after_run"],
        priority=100,
    )
    
    def __init__(self):
        super().__init__()
        self.call_count = 0
        self.last_ctx = None
    
    def on_hook(self, ctx: PluginContext):
        self.call_count += 1
        self.last_ctx = ctx
        ctx.set("mock_processed", True)
        return ctx


class HighPriorityPlugin(Plugin):
    """High priority plugin for ordering tests"""
    
    meta = PluginMeta(
        name="high-priority",
        version="1.0.0",
        hooks=["env:before_generate"],
        priority=10,  # Lower number = higher priority
    )
    
    def __init__(self):
        super().__init__()
        self.call_order = []
    
    def on_hook(self, ctx: PluginContext):
        ctx.set("order", ctx.get("order", []) + ["high"])
        return ctx


class LowPriorityPlugin(Plugin):
    """Low priority plugin for ordering tests"""
    
    meta = PluginMeta(
        name="low-priority",
        version="1.0.0",
        hooks=["env:before_generate"],
        priority=100,  # Higher number = lower priority
    )
    
    def on_hook(self, ctx: PluginContext):
        ctx.set("order", ctx.get("order", []) + ["low"])
        return ctx


class StoppingPlugin(Plugin):
    """Plugin that stops propagation"""
    
    meta = PluginMeta(
        name="stopping-plugin",
        version="1.0.0",
        hooks=["env:before_generate"],
        priority=50,
    )
    
    def on_hook(self, ctx: PluginContext):
        ctx.set("stopped_by", "stopping-plugin")
        ctx.stop_propagation()
        return ctx


class GovernanceTrackerPlugin(Plugin):
    """Plugin for testing governance hooks"""
    
    meta = PluginMeta(
        name="governance-tracker",
        version="1.0.0",
        description="Tracks governance events",
        hooks=[
            "governance:agent_registered",
            "governance:task_assigned",
            "governance:reputation_changed",
        ],
        priority=100,
    )
    
    def __init__(self):
        super().__init__()
        self.events = []
    
    def on_hook(self, ctx: PluginContext):
        self.events.append({
            "hook": ctx.hook_name,
            "data": dict(ctx.data),
        })
        return ctx


# ===== Plugin Tests =====

def test_plugin_meta():
    """Test plugin metadata"""
    plugin = MockPlugin()
    
    assert plugin.meta.name == "mock-plugin"
    assert plugin.meta.version == "1.0.0"
    assert "env:before_generate" in plugin.meta.hooks
    assert len(plugin.meta.hooks) == 2


def test_plugin_context():
    """Test PluginContext data operations"""
    ctx = PluginContext("test:hook", {"initial": "data"})
    
    # Get/set
    assert ctx.get("initial") == "data"
    ctx.set("new_key", "new_value")
    assert ctx.get("new_key") == "new_value"
    assert ctx.get("missing", "default") == "default"
    
    # Stop propagation
    assert not ctx.is_stopped
    ctx.stop_propagation()
    assert ctx.is_stopped


def test_plugin_context_storage():
    """Test plugin-specific storage"""
    ctx = PluginContext("test:hook")
    
    storage = ctx.get_plugin_storage("my-plugin")
    storage["counter"] = 42
    
    # Same storage retrieved again
    assert ctx.get_plugin_storage("my-plugin")["counter"] == 42


# ===== PluginManager Tests =====

def test_manager_register():
    """Test plugin registration"""
    manager = PluginManager()
    plugin = MockPlugin()
    
    result = manager.register(plugin)
    
    assert result is manager  # Chaining
    assert "mock-plugin" in manager._plugins


def test_manager_register_duplicate():
    """Test duplicate registration is skipped"""
    manager = PluginManager()
    plugin1 = MockPlugin()
    plugin2 = MockPlugin()
    
    manager.register(plugin1)
    manager.register(plugin2)  # Should skip
    
    assert len(manager._plugins) == 1


def test_manager_unregister():
    """Test plugin unregistration"""
    manager = PluginManager()
    plugin = MockPlugin()
    
    manager.register(plugin)
    result = manager.unregister("mock-plugin")
    
    assert result is True
    assert "mock-plugin" not in manager._plugins


def test_manager_dispatch():
    """Test hook dispatching"""
    manager = PluginManager()
    plugin = MockPlugin()
    manager.register(plugin)
    
    ctx = manager.dispatch("env:before_generate", {"difficulty": 0.5})
    
    assert plugin.call_count == 1
    assert plugin.last_ctx.get("difficulty") == 0.5
    assert ctx.get("mock_processed") is True


def test_manager_dispatch_no_plugins():
    """Test dispatching to no plugins"""
    manager = PluginManager()
    
    ctx = manager.dispatch("nonexistent:hook", {"data": "value"})
    
    assert ctx.get("data") == "value"


def test_manager_priority_order():
    """Test plugins are called in priority order"""
    manager = PluginManager()
    high = HighPriorityPlugin()
    low = LowPriorityPlugin()
    
    # Register in reverse order
    manager.register(low)
    manager.register(high)
    
    ctx = manager.dispatch("env:before_generate")
    
    # High priority (10) should run before low (100)
    assert ctx.get("order") == ["high", "low"]


def test_manager_stop_propagation():
    """Test stop propagation"""
    manager = PluginManager()
    stopping = StoppingPlugin()
    low = LowPriorityPlugin()
    
    manager.register(low)  # priority 100
    manager.register(stopping)  # priority 50
    
    ctx = manager.dispatch("env:before_generate")
    
    # Stopping plugin (50) runs first, stops propagation
    assert ctx.get("stopped_by") == "stopping-plugin"
    assert ctx.get("order") is None  # Low priority never ran


def test_manager_initialize_cleanup():
    """Test initialize and cleanup all plugins"""
    manager = PluginManager()
    plugin = MockPlugin()
    manager.register(plugin)
    
    manager.initialize_all()
    assert plugin.is_initialized
    
    manager.cleanup_all()
    assert not plugin.is_initialized


# ===== Governance Hook Tests =====

def test_governance_hooks_exist():
    """Test governance hooks are defined"""
    assert PluginHook.GOVERNANCE_AGENT_REGISTERED.value == "governance:agent_registered"
    assert PluginHook.GOVERNANCE_TASK_ASSIGNED.value == "governance:task_assigned"
    assert PluginHook.GOVERNANCE_REPUTATION_CHANGED.value == "governance:reputation_changed"


def test_governance_plugin_tracking():
    """Test governance events are tracked"""
    manager = PluginManager()
    tracker = GovernanceTrackerPlugin()
    manager.register(tracker)
    
    # Simulate governance events
    manager.dispatch("governance:agent_registered", {"agent_id": "agent-1"})
    manager.dispatch("governance:task_assigned", {"task_id": "task-1", "agent_id": "agent-1"})
    manager.dispatch("governance:reputation_changed", {"agent_id": "agent-1", "delta": 10})
    
    assert len(tracker.events) == 3
    assert tracker.events[0]["hook"] == "governance:agent_registered"
    assert tracker.events[1]["data"]["task_id"] == "task-1"
    assert tracker.events[2]["data"]["delta"] == 10


# ===== Knowledge Hook Tests =====

def test_knowledge_hooks_exist():
    """Test knowledge hooks are defined"""
    assert PluginHook.KNOWLEDGE_EXPERIENCE_STORED.value == "knowledge:experience_stored"
    assert PluginHook.KNOWLEDGE_PAGE_CREATED.value == "knowledge:page_created"


# ===== Tenant Hook Tests =====

def test_tenant_hooks_exist():
    """Test tenant hooks are defined"""
    assert PluginHook.TENANT_CREATED.value == "tenant:created"
    assert PluginHook.TENANT_QUOTA_CHECK.value == "tenant:quota_check"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
