"""Service Container and Provider

Provides:
- ServiceRegistry: Central registration point for all services
- ServiceContainer: Dependency injection container
- ServiceProvider: Facade for easy service access

This follows the patterns from claude-code's modular architecture:
- Clear separation of concerns
- Dependency injection
- Lifecycle management
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type, TypeVar, Callable
from .base import ServiceBase, ServiceConfig, ServiceState, ServiceError
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=ServiceBase)


@dataclass
class ServiceInfo:
    """Metadata about a registered service"""
    service: ServiceBase
    config: ServiceConfig
    is_primary: bool = False


class ServiceRegistry:
    """
    Central registry for all services.
    
    Usage:
        registry = ServiceRegistry()
        registry.register(EnvironmentService(config))
        registry.register(LearnerService(config))
        
        env_service = registry.get(EnvironmentService)
    """
    
    def __init__(self):
        self._services: Dict[str, ServiceInfo] = {}
        self._by_type: Dict[Type, str] = {}
    
    def register(
        self,
        service: ServiceBase,
        is_primary: bool = False,
    ) -> None:
        """
        Register a service.
        
        Args:
            service: Service instance to register
            is_primary: Whether this is the primary instance of its type
        """
        name = service.name
        
        if name in self._services:
            raise ServiceError(name, f"Service '{name}' already registered")
        
        # Store by name
        self._services[name] = ServiceInfo(
            service=service,
            config=service.config,
            is_primary=is_primary,
        )
        
        # Store by type (for lookup)
        service_type = type(service)
        if service_type not in self._by_type or is_primary:
            self._by_type[service_type] = name
        
        logger.info(f"Registered service: {name} ({service_type.__name__})")
    
    def get(self, name: str) -> Optional[ServiceBase]:
        """Get a service by name"""
        info = self._services.get(name)
        return info.service if info else None
    
    def get_by_type(self, service_type: Type[T]) -> Optional[T]:
        """Get a service by type"""
        name = self._by_type.get(service_type)
        if name is None:
            return None
        info = self._services.get(name)
        return info.service if info else None
    
    def get_all(self) -> List[ServiceBase]:
        """Get all registered services"""
        return [info.service for info in self._services.values()]
    
    def list_services(self) -> List[str]:
        """List all service names"""
        return list(self._services.keys())
    
    def unregister(self, name: str) -> bool:
        """Unregister a service"""
        if name not in self._services:
            return False
        
        info = self._services.pop(name)
        
        # Remove from type mapping
        service_type = type(info.service)
        if self._by_type.get(service_type) == name:
            del self._by_type[service_type]
        
        logger.info(f"Unregistered service: {name}")
        return True


class ServiceContainer:
    """
    Dependency injection container.
    
    Handles:
    - Service initialization order (based on dependencies)
    - Lifecycle management (start/stop in correct order)
    - Dependency resolution
    
    Usage:
        container = ServiceContainer()
        container.add(EnvironmentService, config)
        container.add(LearnerService, config)
        
        container.initialize_all()
        container.start_all()
        
        # Use services
        env = container.get(EnvironmentService)
        
        container.stop_all()
    """
    
    def __init__(self):
        self._registry = ServiceRegistry()
        self._factories: Dict[Type, Callable[[], ServiceBase]] = {}
        self._configs: Dict[Type, ServiceConfig] = {}
    
    @property
    def registry(self) -> ServiceRegistry:
        return self._registry
    
    def add(
        self,
        service_type: Type[T],
        config: ServiceConfig,
        factory: Optional[Callable[[], T]] = None,
    ) -> 'ServiceContainer':
        """
        Add a service to the container.
        
        Args:
            service_type: Service class
            config: Service configuration
            factory: Optional custom factory function
        
        Returns:
            self for chaining
        """
        self._configs[service_type] = config
        
        if factory:
            self._factories[service_type] = factory
        else:
            self._factories[service_type] = lambda: service_type(config)
        
        return self
    
    def _resolve_dependencies(self) -> List[Type]:
        """
        Resolve initialization order based on dependencies.
        
        Returns:
            List of service types in initialization order
        """
        # Build dependency graph
        graph: Dict[Type, List[Type]] = {}
        
        for service_type, config in self._configs.items():
            deps = []
            for dep_name in config.dependencies:
                # Find dependency by name
                for st, sc in self._configs.items():
                    if sc.name == dep_name:
                        deps.append(st)
                        break
            graph[service_type] = deps
        
        # Topological sort
        result = []
        visited = set()
        temp_visited = set()
        
        def visit(node: Type):
            if node in temp_visited:
                raise ServiceError(
                    self._configs[node].name,
                    "Circular dependency detected"
                )
            if node in visited:
                return
            
            temp_visited.add(node)
            for dep in graph.get(node, []):
                visit(dep)
            temp_visited.remove(node)
            visited.add(node)
            result.append(node)
        
        for service_type in self._configs:
            visit(service_type)
        
        return result
    
    def initialize_all(self) -> None:
        """Initialize all services in dependency order"""
        order = self._resolve_dependencies()
        
        for service_type in order:
            factory = self._factories.get(service_type)
            if not factory:
                continue
            
            service = factory()
            
            # Inject dependencies
            config = self._configs[service_type]
            for dep_name in config.dependencies:
                dep_service = self._registry.get(dep_name)
                if dep_service:
                    service.set_dependency(dep_name, dep_service)
            
            # Initialize
            try:
                service.transition_to(ServiceState.INITIALIZING)
                service.initialize()
                service.transition_to(ServiceState.READY)
                self._registry.register(service)
            except Exception as e:
                service.transition_to(ServiceState.ERROR)
                raise ServiceError(service.name, f"Initialization failed: {e}", e)
    
    def start_all(self) -> None:
        """Start all services in dependency order"""
        order = self._resolve_dependencies()
        
        for service_type in order:
            service = self._registry.get_by_type(service_type)
            if service and service.state == ServiceState.READY:
                try:
                    service.start()
                    service.transition_to(ServiceState.RUNNING)
                except Exception as e:
                    service.transition_to(ServiceState.ERROR)
                    raise ServiceError(service.name, f"Start failed: {e}", e)
    
    def stop_all(self) -> None:
        """Stop all services in reverse dependency order"""
        order = self._resolve_dependencies()
        
        for service_type in reversed(order):
            service = self._registry.get_by_type(service_type)
            if service and service.is_running:
                try:
                    service.transition_to(ServiceState.STOPPING)
                    service.stop()
                    service.transition_to(ServiceState.STOPPED)
                except Exception as e:
                    service.transition_to(ServiceState.ERROR)
                    logger.error(f"Error stopping {service.name}: {e}")
    
    def get(self, service_type: Type[T]) -> Optional[T]:
        """Get a service by type"""
        return self._registry.get_by_type(service_type)
    
    def get_by_name(self, name: str) -> Optional[ServiceBase]:
        """Get a service by name"""
        return self._registry.get(name)


class ServiceProvider:
    """
    Facade for easy service access.
    
    This is the main entry point for the service architecture.
    
    Usage:
        provider = ServiceProvider()
        
        # Configure services
        provider.configure(EnvironmentService, env_config)
        provider.configure(LearnerService, learner_config)
        
        # Start
        provider.start()
        
        # Use
        env = provider.get(EnvironmentService)
        result = env.generate()
        
        # Stop
        provider.stop()
    """
    
    _instance: Optional['ServiceProvider'] = None
    
    def __init__(self):
        self._container = ServiceContainer()
        self._started = False
    
    @classmethod
    def get_instance(cls) -> 'ServiceProvider':
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def configure(
        self,
        service_type: Type[T],
        config: ServiceConfig,
        factory: Optional[Callable[[], T]] = None,
    ) -> 'ServiceProvider':
        """
        Configure a service.
        
        Args:
            service_type: Service class
            config: Service configuration
            factory: Optional custom factory
        
        Returns:
            self for chaining
        """
        self._container.add(service_type, config, factory)
        return self
    
    def initialize(self) -> 'ServiceProvider':
        """Initialize all services"""
        self._container.initialize_all()
        return self
    
    def start(self) -> 'ServiceProvider':
        """Start all services"""
        if not self._started:
            self.initialize()
            self._container.start_all()
            self._started = True
        return self
    
    def stop(self) -> 'ServiceProvider':
        """Stop all services"""
        if self._started:
            self._container.stop_all()
            self._started = False
        return self
    
    def get(self, service_type: Type[T]) -> T:
        """
        Get a service.
        
        Raises:
            ServiceError if service not found
        """
        service = self._container.get(service_type)
        if service is None:
            raise ServiceError(
                service_type.__name__,
                f"Service not found. Did you configure it?"
            )
        return service
    
    def get_by_name(self, name: str) -> ServiceBase:
        """Get a service by name"""
        service = self._container.get_by_name(name)
        if service is None:
            raise ServiceError(name, f"Service '{name}' not found")
        return service
    
    def health_check(self) -> Dict[str, Any]:
        """Get health status of all services"""
        services = self._container.registry.get_all()
        return {
            "status": "healthy" if all(s.is_running for s in services) else "degraded",
            "services": [s.health_check() for s in services],
            "started": self._started,
        }
    
    def __enter__(self) -> 'ServiceProvider':
        return self.start()
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
