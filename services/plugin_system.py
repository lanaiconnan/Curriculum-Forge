"""Plugin System for Curriculum-Forge

Provides:
- Plugin discovery and loading
- Hook system for extensibility
- Plugin configuration management
- Plugin lifecycle management

Design patterns from claude-code's modular architecture:
- Metadata-driven registration
- Type-safe interfaces
- Clean separation of concerns
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, TypeVar, Type
from abc import ABC, abstractmethod
from enum import Enum
import logging
import importlib
import inspect

from .base import ServiceBase, ServiceConfig

logger = logging.getLogger(__name__)

T = TypeVar('T', bound='Plugin')


class PluginHook(Enum):
    """Standard hooks that plugins can register for"""
    # Environment lifecycle
    ENV_BEFORE_GENERATE = "env:before_generate"
    ENV_AFTER_GENERATE = "env:after_generate"
    
    # Experiment lifecycle
    EXP_BEFORE_RUN = "exp:before_run"
    EXP_AFTER_RUN = "exp:after_run"
    
    # RL lifecycle
    RL_BEFORE_TRAIN = "rl:before_train"
    RL_AFTER_TRAIN = "rl:after_train"
    
    # Reward lifecycle
    REWARD_BEFORE_CALC = "reward:before_calc"
    REWARD_AFTER_CALC = "reward:after_calc"
    
    # Results lifecycle
    RESULT_BEFORE_SAVE = "result:before_save"
    RESULT_AFTER_SAVE = "result:after_save"
    
    # Stage lifecycle
    STAGE_BEFORE_TRANSITION = "stage:before_transition"
    STAGE_AFTER_TRANSITION = "stage:after_transition"
    
    # Governance lifecycle (Phase 7.1)
    GOVERNANCE_AGENT_REGISTERED = "governance:agent_registered"
    GOVERNANCE_AGENT_UNREGISTERED = "governance:agent_unregistered"
    GOVERNANCE_TASK_ASSIGNED = "governance:task_assigned"
    GOVERNANCE_TASK_COMPLETED = "governance:task_completed"
    GOVERNANCE_REPUTATION_CHANGED = "governance:reputation_changed"
    GOVERNANCE_QUOTA_EXCEEDED = "governance:quota_exceeded"
    GOVERNANCE_RULE_VIOLATION = "governance:rule_violation"
    GOVERNANCE_PROPOSAL_CREATED = "governance:proposal_created"
    GOVERNANCE_PROPOSAL_CLOSED = "governance:proposal_closed"
    
    # Knowledge lifecycle (Phase 7.1)
    KNOWLEDGE_EXPERIENCE_STORED = "knowledge:experience_stored"
    KNOWLEDGE_EXPERIENCE_RETRIEVED = "knowledge:experience_retrieved"
    KNOWLEDGE_PAGE_CREATED = "knowledge:page_created"
    KNOWLEDGE_PAGE_UPDATED = "knowledge:page_updated"
    KNOWLEDGE_PAGE_DELETED = "knowledge:page_deleted"
    
    # Tenant lifecycle (Phase 7.1)
    TENANT_CREATED = "tenant:created"
    TENANT_UPDATED = "tenant:updated"
    TENANT_SUSPENDED = "tenant:suspended"
    TENANT_QUOTA_CHECK = "tenant:quota_check"


@dataclass
class PluginMeta:
    """Plugin metadata (set in subclass)"""
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    hooks: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    priority: int = 100  # Lower = higher priority


class PluginContext:
    """
    Context object passed to plugin hooks.
    
    Provides access to:
    - Current event data
    - Service provider (for accessing other services)
    - Plugin-specific storage
    """
    
    def __init__(
        self,
        hook_name: str,
        data: Optional[Dict[str, Any]] = None,
    ):
        self.hook_name = hook_name
        self.data = data or {}
        self._storage: Dict[str, Dict[str, Any]] = {}
        self._stopped = False
    
    @property
    def is_stopped(self) -> bool:
        """Check if event propagation is stopped"""
        return self._stopped
    
    def stop_propagation(self) -> None:
        """Stop event propagation to lower-priority plugins"""
        self._stopped = True
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get data from context"""
        return self.data.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set data in context"""
        self.data[key] = value
    
    def get_plugin_storage(self, plugin_name: str) -> Dict[str, Any]:
        """Get plugin-specific storage"""
        if plugin_name not in self._storage:
            self._storage[plugin_name] = {}
        return self._storage[plugin_name]


HookHandler = Callable[[PluginContext], Optional[PluginContext]]


class Plugin(ABC):
    """
    Abstract base class for plugins.
    
    Plugins extend Curriculum-Forge without modifying core code.
    
    Usage:
        class MyPlugin(Plugin):
            meta = PluginMeta(
                name="my-plugin",
                description="My custom plugin",
                hooks=["env:before_generate", "exp:after_run"],
            )
            
            def on_hook(self, ctx: PluginContext) -> Optional[PluginContext]:
                if ctx.hook_name == "env:before_generate":
                    # Modify environment before generation
                    ctx.set("extra_constraint", "no_numpy")
                return ctx
            
            def initialize(self):
                # Setup plugin resources
                pass
            
            def cleanup(self):
                # Cleanup plugin resources
                pass
    """
    
    meta: PluginMeta = PluginMeta(name="unnamed")
    
    def __init__(self):
        self._initialized = False
        self._handlers: Dict[str, HookHandler] = {}
        self._register_hooks()
    
    def _register_hooks(self) -> None:
        """Register all hooks from meta.hooks"""
        for hook in self.meta.hooks:
            self._handlers[hook] = self.on_hook
    
    @abstractmethod
    def on_hook(self, ctx: PluginContext) -> Optional[PluginContext]:
        """
        Handle a hook event.
        
        Args:
            ctx: Plugin context with event data
        
        Returns:
            Modified context (or None to stop propagation)
        """
        pass
    
    def initialize(self) -> None:
        """Initialize plugin resources. Override in subclass."""
        self._initialized = True
    
    def cleanup(self) -> None:
        """Cleanup plugin resources. Override in subclass."""
        self._initialized = False
    
    @property
    def is_initialized(self) -> bool:
        return self._initialized
    
    def __repr__(self) -> str:
        return f"Plugin(name={self.meta.name!r}, version={self.meta.version!r})"


class PluginManager:
    """
    Central plugin manager.
    
    Handles:
    - Plugin registration and discovery
    - Hook dispatching
    - Plugin lifecycle
    - Priority-based execution
    
    Usage:
        manager = PluginManager()
        manager.register(MyPlugin())
        manager.register(AnotherPlugin())
        
        # Dispatch hooks
        ctx = manager.dispatch("env:before_generate", {"difficulty": 0.5})
        
        # Shutdown
        manager.cleanup_all()
    """
    
    def __init__(self):
        self._plugins: Dict[str, Plugin] = {}
        self._hook_map: Dict[str, List[Plugin]] = {}
    
    def register(self, plugin: Plugin) -> 'PluginManager':
        """
        Register a plugin.
        
        Args:
            plugin: Plugin instance
        
        Returns:
            self for chaining
        """
        name = plugin.meta.name
        
        if name in self._plugins:
            logger.warning(f"Plugin '{name}' already registered, skipping")
            return self
        
        # Check dependencies
        for dep in plugin.meta.depends_on:
            if dep not in self._plugins:
                logger.warning(
                    f"Plugin '{name}' depends on '{dep}' which is not registered"
                )
        
        # Register plugin
        self._plugins[name] = plugin
        
        # Build hook map
        for hook_name in plugin.meta.hooks:
            if hook_name not in self._hook_map:
                self._hook_map[hook_name] = []
            self._hook_map[hook_name].append(plugin)
        
        # Sort by priority (lower = higher priority)
        for hook_name in self._hook_map:
            self._hook_map[hook_name].sort(
                key=lambda p: p.meta.priority
            )
        
        logger.info(f"Registered plugin: {name} v{plugin.meta.version}")
        return self
    
    def unregister(self, name: str) -> bool:
        """Unregister a plugin by name"""
        if name not in self._plugins:
            return False
        
        plugin = self._plugins.pop(name)
        
        # Remove from hook map
        for hook_name in plugin.meta.hooks:
            if hook_name in self._hook_map:
                self._hook_map[hook_name] = [
                    p for p in self._hook_map[hook_name] if p.meta.name != name
                ]
        
        plugin.cleanup()
        logger.info(f"Unregistered plugin: {name}")
        return True
    
    def dispatch(
        self,
        hook_name: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> PluginContext:
        """
        Dispatch a hook event to all registered plugins.
        
        Args:
            hook_name: Hook name
            data: Event data
        
        Returns:
            Final context after all plugins have processed
        """
        ctx = PluginContext(hook_name=hook_name, data=data or {})
        
        plugins = self._hook_map.get(hook_name, [])
        
        for plugin in plugins:
            try:
                result = plugin.on_hook(ctx)
                
                if result is None:
                    ctx.stop_propagation()
                    break
                
                if ctx.is_stopped:
                    break
                    
            except Exception as e:
                logger.error(
                    f"Plugin '{plugin.meta.name}' error on hook '{hook_name}': {e}"
                )
                # Continue to next plugin
        
        return ctx
    
    def initialize_all(self) -> None:
        """Initialize all plugins"""
        for plugin in self._plugins.values():
            try:
                plugin.initialize()
                logger.info(f"Initialized plugin: {plugin.meta.name}")
            except Exception as e:
                logger.error(
                    f"Failed to initialize plugin '{plugin.meta.name}': {e}"
                )
    
    def cleanup_all(self) -> None:
        """Cleanup all plugins"""
        for plugin in self._plugins.values():
            try:
                plugin.cleanup()
            except Exception as e:
                logger.error(
                    f"Failed to cleanup plugin '{plugin.meta.name}': {e}"
                )
    
    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all registered plugins"""
        return [
            {
                "name": p.meta.name,
                "version": p.meta.version,
                "description": p.meta.description,
                "hooks": p.meta.hooks,
                "initialized": p.is_initialized,
                "priority": p.meta.priority,
            }
            for p in sorted(self._plugins.values(), key=lambda p: p.meta.priority)
        ]
    
    def get_plugin(self, name: str) -> Optional[Plugin]:
        """Get a plugin by name"""
        return self._plugins.get(name)
    
    def has_plugin(self, name: str) -> bool:
        """Check if a plugin is registered"""
        return name in self._plugins
