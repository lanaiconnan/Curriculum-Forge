"""Tenant Monitor Plugin

Monitors tenant lifecycle events and quota checks.
Provides alerts for quota warnings and tenant suspensions.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List

from services.plugin_system import (
    PluginHook,
    PluginMeta,
    register_plugin,
)


class TenantMonitorPlugin:
    """Plugin that monitors tenant events and quota usage."""
    
    name = "tenant-monitor"
    version = "1.0.0"
    description = "Monitors tenant lifecycle and quota events"
    author = "Curriculum Forge Team"
    
    hooks = [
        PluginHook.TENANT_CREATED,
        PluginHook.TENANT_UPDATED,
        PluginHook.TENANT_SUSPENDED,
        PluginHook.TENANT_QUOTA_CHECK,
    ]
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.alert_threshold = self.config.get("alert_threshold", 0.8)  # 80%
        self.log_file = self.config.get("log_file", "data/tenant_monitor.jsonl")
        self._alerts: List[Dict[str, Any]] = []
        
    def on_hook(self, hook: PluginHook, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tenant hooks."""
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "hook": hook.value,
            "context": context,
        }
        
        # Check for quota warnings
        if hook == PluginHook.TENANT_QUOTA_CHECK:
            usage = context.get("usage", 0)
            limit = context.get("limit", 1)
            ratio = usage / limit if limit > 0 else 0
            
            if ratio >= self.alert_threshold:
                alert = {
                    "timestamp": event["timestamp"],
                    "type": "quota_warning",
                    "tenant_id": context.get("tenant_id"),
                    "usage": usage,
                    "limit": limit,
                    "ratio": ratio,
                }
                self._alerts.append(alert)
                event["alert"] = True
        
        # Log event
        self._write_event(event)
        
        return context
    
    def _write_event(self, event: Dict[str, Any]):
        """Write event to JSONL log file."""
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        with open(self.log_file, "a") as f:
            f.write(json.dumps(event) + "\n")
    
    def get_alerts(self, clear: bool = False) -> List[Dict[str, Any]]:
        """Return pending alerts."""
        alerts = self._alerts.copy()
        if clear:
            self._alerts.clear()
        return alerts
    
    def get_stats(self) -> Dict[str, Any]:
        """Return plugin statistics."""
        return {
            "name": self.name,
            "alerts_count": len(self._alerts),
            "alert_threshold": self.alert_threshold,
            "log_file": self.log_file,
        }


# Register plugin
plugin_instance = TenantMonitorPlugin()
register_plugin(
    PluginMeta(
        name=plugin_instance.name,
        version=plugin_instance.version,
        description=plugin_instance.description,
        author=plugin_instance.author,
        hooks=plugin_instance.hooks,
    ),
    plugin_instance.on_hook,
    config={},
)