"""Unit tests for Plugin System

Run: pytest tests/unit/test_plugins.py -v
"""

import pytest
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.plugin_system import (
    Plugin, PluginMeta, PluginManager, PluginContext, PluginHook,
)
from services.plugin_loader import (
    discover_plugins, load_plugins_into_manager,
    load_plugin_from_dir, _parse_plugin_md,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

class EchoPlugin(Plugin):
    """Test plugin that echoes data"""
    meta = PluginMeta(
        name="echo",
        version="1.0.0",
        description="Echo plugin for testing",
        hooks=["test:hook"],
        priority=100,
    )
    
    def __init__(self):
        super().__init__()
        self.calls = []
    
    def initialize(self):
        self._initialized = True
    
    def cleanup(self):
        self._initialized = False
    
    def on_hook(self, ctx: PluginContext):
        self.calls.append(ctx.hook_name)
        ctx.set("echo", True)
        return ctx


class StopPlugin(Plugin):
    """Test plugin that stops propagation"""
    meta = PluginMeta(
        name="stopper",
        version="1.0.0",
        hooks=["test:hook"],
        priority=10,  # Higher priority (runs first)
    )
    
    def on_hook(self, ctx: PluginContext):
        ctx.set("stopped_by", "stopper")
        return None  # Stop propagation


class ErrorPlugin(Plugin):
    """Test plugin that raises an error"""
    meta = PluginMeta(
        name="error-plugin",
        version="1.0.0",
        hooks=["test:hook"],
        priority=100,
    )
    
    def on_hook(self, ctx: PluginContext):
        raise RuntimeError("intentional error")


# ─── PluginContext ────────────────────────────────────────────────────────────

class TestPluginContext:
    def test_get_set(self):
        ctx = PluginContext("test:hook", {"x": 1})
        assert ctx.get("x") == 1
        ctx.set("y", 2)
        assert ctx.get("y") == 2

    def test_default_value(self):
        ctx = PluginContext("test:hook")
        assert ctx.get("missing", "default") == "default"

    def test_stop_propagation(self):
        ctx = PluginContext("test:hook")
        assert not ctx.is_stopped
        ctx.stop_propagation()
        assert ctx.is_stopped

    def test_plugin_storage(self):
        ctx = PluginContext("test:hook")
        storage = ctx.get_plugin_storage("my-plugin")
        storage["key"] = "value"
        assert ctx.get_plugin_storage("my-plugin")["key"] == "value"


# ─── PluginManager ────────────────────────────────────────────────────────────

class TestPluginManager:
    def test_register_and_list(self):
        manager = PluginManager()
        manager.register(EchoPlugin())
        plugins = manager.list_plugins()
        assert len(plugins) == 1
        assert plugins[0]["name"] == "echo"

    def test_dispatch_hook(self):
        manager = PluginManager()
        plugin = EchoPlugin()
        manager.register(plugin)
        
        ctx = manager.dispatch("test:hook", {"data": 42})
        assert ctx.get("echo") == True
        assert len(plugin.calls) == 1

    def test_no_handler_for_hook(self):
        manager = PluginManager()
        manager.register(EchoPlugin())
        ctx = manager.dispatch("other:hook", {})
        # Should return empty context without error
        assert ctx.hook_name == "other:hook"

    def test_stop_propagation(self):
        manager = PluginManager()
        stopper = StopPlugin()
        echo = EchoPlugin()
        manager.register(stopper)
        manager.register(echo)
        
        ctx = manager.dispatch("test:hook", {})
        # Stopper runs first (priority=10), stops propagation
        assert ctx.get("stopped_by") == "stopper"
        assert len(echo.calls) == 0  # Echo never ran

    def test_error_in_plugin_continues(self):
        manager = PluginManager()
        error_plugin = ErrorPlugin()
        echo = EchoPlugin()
        manager.register(error_plugin)
        manager.register(echo)
        
        # Should not raise, should continue to echo
        ctx = manager.dispatch("test:hook", {})
        assert ctx.get("echo") == True

    def test_unregister(self):
        manager = PluginManager()
        manager.register(EchoPlugin())
        assert manager.has_plugin("echo")
        manager.unregister("echo")
        assert not manager.has_plugin("echo")

    def test_priority_ordering(self):
        order = []
        
        class P1(Plugin):
            meta = PluginMeta(name="p1", hooks=["test:hook"], priority=200)
            def on_hook(self, ctx):
                order.append("p1")
                return ctx
        
        class P2(Plugin):
            meta = PluginMeta(name="p2", hooks=["test:hook"], priority=50)
            def on_hook(self, ctx):
                order.append("p2")
                return ctx
        
        manager = PluginManager()
        manager.register(P1())
        manager.register(P2())
        manager.dispatch("test:hook", {})
        
        # p2 (priority=50) should run before p1 (priority=200)
        assert order == ["p2", "p1"]

    def test_initialize_all(self):
        manager = PluginManager()
        plugin = EchoPlugin()
        manager.register(plugin)
        assert not plugin.is_initialized
        manager.initialize_all()
        assert plugin.is_initialized

    def test_cleanup_all(self):
        manager = PluginManager()
        plugin = EchoPlugin()
        manager.register(plugin)
        manager.initialize_all()
        manager.cleanup_all()
        assert not plugin.is_initialized


# ─── Plugin Loader ────────────────────────────────────────────────────────────

class TestPluginLoader:
    def test_parse_plugin_md(self, tmp_path):
        md = tmp_path / "PLUGIN.md"
        md.write_text("""---
name: test-plugin
version: 2.0.0
description: A test plugin
hooks:
  - env:before_generate
  - exp:after_run
priority: 50
---

# Test Plugin
""")
        meta = _parse_plugin_md(str(md))
        assert meta["name"] == "test-plugin"
        assert meta["version"] == "2.0.0"
        assert "env:before_generate" in meta["hooks"]
        assert "exp:after_run" in meta["hooks"]
        assert meta["priority"] == "50"

    def test_load_plugin_from_dir(self, tmp_path):
        # Create plugin directory
        plugin_dir = tmp_path / "my-plugin"
        plugin_dir.mkdir()
        
        # Write plugin.py
        (plugin_dir / "plugin.py").write_text("""
from services.plugin_system import Plugin, PluginMeta, PluginContext

class MyPlugin(Plugin):
    meta = PluginMeta(name="my-plugin", hooks=["test:hook"])
    
    def on_hook(self, ctx):
        return ctx
""")
        
        result = load_plugin_from_dir(str(plugin_dir))
        assert result.success
        assert result.plugin is not None
        assert result.plugin.meta.name == "my-plugin"

    def test_load_plugin_missing_py(self, tmp_path):
        plugin_dir = tmp_path / "empty-plugin"
        plugin_dir.mkdir()
        
        result = load_plugin_from_dir(str(plugin_dir))
        assert not result.success
        assert "plugin.py not found" in result.error

    def test_discover_plugins(self, tmp_path):
        # Create two plugin directories
        for name in ["plugin-a", "plugin-b"]:
            d = tmp_path / name
            d.mkdir()
            (d / "plugin.py").write_text(f"""
from services.plugin_system import Plugin, PluginMeta, PluginContext

class P(Plugin):
    meta = PluginMeta(name="{name}", hooks=["test:hook"])
    def on_hook(self, ctx): return ctx
""")
        
        results = discover_plugins(str(tmp_path))
        assert len(results) == 2
        assert all(r.success for r in results)

    def test_load_plugins_into_manager(self, tmp_path):
        d = tmp_path / "test-plugin"
        d.mkdir()
        (d / "plugin.py").write_text("""
from services.plugin_system import Plugin, PluginMeta, PluginContext

class TestPlugin(Plugin):
    meta = PluginMeta(name="test-plugin", hooks=["test:hook"])
    def initialize(self): self._initialized = True
    def on_hook(self, ctx): return ctx
""")
        
        manager = PluginManager()
        summary = load_plugins_into_manager(manager, str(tmp_path), auto_initialize=True)
        
        assert summary["success_count"] == 1
        assert summary["fail_count"] == 0
        assert manager.has_plugin("test-plugin")


# ─── Built-in Plugins ─────────────────────────────────────────────────────────

class TestBuiltinPlugins:
    def _get_plugins_dir(self):
        # Resolve from this file's location upward to project root
        this_file = os.path.abspath(__file__)          # tests/unit/test_plugins.py
        tests_unit = os.path.dirname(this_file)        # tests/unit/
        tests_dir = os.path.dirname(tests_unit)        # tests/
        project_root = os.path.dirname(tests_dir)      # project root
        return os.path.join(project_root, "plugins")
    
    def test_discover_builtin_plugins(self):
        plugins_dir = self._get_plugins_dir()
        results = discover_plugins(plugins_dir)
        names = [r.name for r in results if r.success]
        assert "reward-logger" in names
        assert "stage-tracker" in names
        assert "experiment-filter" in names

    def test_reward_logger_hooks(self):
        plugins_dir = self._get_plugins_dir()
        manager = PluginManager()
        load_plugins_into_manager(manager, plugins_dir, auto_initialize=True)
        
        ctx = manager.dispatch("reward:after_calc", {
            "exp_id": "test_001",
            "reward": {"rformat": 1.0, "rname": 1.0, "rparam": 0.5, "rvalue": 0.5, "rfinal": 3.0},
        })
        assert ctx is not None

    def test_stage_tracker_transition(self):
        plugins_dir = self._get_plugins_dir()
        manager = PluginManager()
        load_plugins_into_manager(manager, plugins_dir, auto_initialize=True)
        
        # Simulate stage transition
        ctx = manager.dispatch("stage:before_transition", {
            "from_stage": "beginner",
            "to_stage": "intermediate",
            "keep_rate": 0.35,
        })
        assert ctx.get("is_regression") == False
        
        # Simulate regression
        ctx2 = manager.dispatch("stage:before_transition", {
            "from_stage": "advanced",
            "to_stage": "beginner",
            "keep_rate": 0.1,
        })
        assert ctx2.get("is_regression") == True

    def test_experiment_filter_skip(self):
        plugins_dir = self._get_plugins_dir()
        manager = PluginManager()
        load_plugins_into_manager(manager, plugins_dir, auto_initialize=True)
        
        # Valid env should pass
        from services.models import TrainingEnvironment, LearningStage, TaskConfig
        env = TrainingEnvironment(
            id="e1", name="test", description="",
            stage=LearningStage.BEGINNER, difficulty=0.3,
            tasks=[TaskConfig(id="t1", type="test", description="", target="")]
        )
        ctx = manager.dispatch("exp:before_run", {"env": env})
        assert ctx.get("skip") == False
        
        # Result below threshold should be filtered
        ctx2 = manager.dispatch("result:before_save", {
            "reward": -5.0, "duration": 1.0
        })
        assert ctx2.get("filtered") == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
