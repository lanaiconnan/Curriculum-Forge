"""Service Base Classes and Types

This module provides the foundation for the service-oriented architecture:
- Service lifecycle management (init/start/stop)
- Dependency injection support
- Service state tracking
- Configuration management

Based on patterns from claude-code Python port structure.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, TypeVar, Generic
from abc import ABC, abstractmethod
from enum import Enum
import time


class ServiceState(Enum):
    """Service lifecycle states"""
    CREATED = "created"
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class ServiceConfig:
    """Base configuration for all services"""
    name: str
    enabled: bool = True
    priority: int = 0
    dependencies: List[str] = field(default_factory=list)
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ServiceMetrics:
    """Service performance metrics"""
    start_time: float = 0.0
    stop_time: float = 0.0
    request_count: int = 0
    error_count: int = 0
    last_error: Optional[str] = None
    
    @property
    def uptime(self) -> float:
        """Calculate uptime in seconds"""
        if self.start_time == 0:
            return 0.0
        end = self.stop_time if self.stop_time > 0 else time.time()
        return end - self.start_time
    
    @property
    def error_rate(self) -> float:
        """Calculate error rate"""
        if self.request_count == 0:
            return 0.0
        return self.error_count / self.request_count


T = TypeVar('T')


class ServiceBase(ABC, Generic[T]):
    """
    Abstract base class for all services.
    
    Lifecycle:
        __init__ → initialize() → start() → [running] → stop() → cleanup()
    
    Usage:
        class MyService(ServiceBase[MyConfig]):
            def initialize(self):
                # Setup resources
            
            def start(self):
                # Start service
            
            def stop(self):
                # Stop service
    """
    
    def __init__(self, config: ServiceConfig):
        self.config = config
        self._state = ServiceState.CREATED
        self._metrics = ServiceMetrics()
        self._dependencies: Dict[str, 'ServiceBase'] = {}
    
    @property
    def name(self) -> str:
        return self.config.name
    
    @property
    def state(self) -> ServiceState:
        return self._state
    
    @property
    def metrics(self) -> ServiceMetrics:
        return self._metrics
    
    @property
    def is_running(self) -> bool:
        return self._state == ServiceState.RUNNING
    
    @property
    def is_ready(self) -> bool:
        return self._state in (ServiceState.READY, ServiceState.RUNNING)
    
    def set_dependency(self, name: str, service: 'ServiceBase') -> None:
        """Inject a dependency"""
        self._dependencies[name] = service
    
    def get_dependency(self, name: str) -> Optional['ServiceBase']:
        """Get an injected dependency"""
        return self._dependencies.get(name)
    
    def transition_to(self, new_state: ServiceState) -> None:
        """Transition to a new state"""
        old_state = self._state
        self._state = new_state
        self._on_state_change(old_state, new_state)
    
    def _on_state_change(self, old: ServiceState, new: ServiceState) -> None:
        """Hook for state change events"""
        pass
    
    @abstractmethod
    def initialize(self) -> None:
        """
        Initialize the service.
        
        Called once during service registration.
        Setup resources, validate config, etc.
        """
        pass
    
    @abstractmethod
    def start(self) -> None:
        """
        Start the service.
        
        Called when the service should begin operation.
        """
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """
        Stop the service.
        
        Called when the service should stop operation.
        Should be idempotent.
        """
        pass
    
    def health_check(self) -> Dict[str, Any]:
        """
        Check service health.
        
        Returns:
            Dict with health status information
        """
        return {
            "name": self.name,
            "state": self._state.value,
            "is_running": self.is_running,
            "uptime": self._metrics.uptime,
            "error_rate": self._metrics.error_rate,
            "request_count": self._metrics.request_count,
        }
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, state={self._state.value})"


class ServiceError(Exception):
    """Base exception for service errors"""
    
    def __init__(self, service_name: str, message: str, cause: Optional[Exception] = None):
        self.service_name = service_name
        self.message = message
        self.cause = cause
        super().__init__(f"[{service_name}] {message}")


# Type alias for Service
Service = ServiceBase[ServiceConfig]
