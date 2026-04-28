"""Knowledge Logger Plugin

Logs knowledge layer events (experience storage, page creation, etc.)
for debugging and audit purposes.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict

from services.plugin_system import (
    PluginHook,
    PluginMeta,
    register_plugin,
)


class KnowledgeLoggerPlugin:
    """Plugin that logs all knowledge layer events to a JSONL file."""
    
    name = "knowledge-logger"
    version = "1.0.0"
    description = "Logs knowledge layer events for debugging and audit"
    author = "Curriculum Forge Team"
    
    hooks = [
        PluginHook.KNOWLEDGE_EXPERIENCE_STORED,
        PluginHook.KNOWLEDGE_EXPERIENCE_RETRIEVED,
        PluginHook.KNOWLEDGE_PAGE_CREATED,
        PluginHook.KNOWLEDGE_PAGE_UPDATED,
        PluginHook.KNOWLEDGE_PAGE_DELETED,
    ]
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.log_dir = self.config.get("log_dir", "data/knowledge_logs")
        self.max_entries = self.config.get("max_entries", 10000)
        self._entries_count = 0
        
    def on_hook(self, hook: PluginHook, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle knowledge layer hooks."""
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "hook": hook.value,
            "context": context,
        }
        
        # Write to JSONL file
        self._write_event(event)
        
        # Return context unchanged (observer only)
        return context
    
    def _write_event(self, event: Dict[str, Any]):
        """Write event to JSONL log file."""
        os.makedirs(self.log_dir, exist_ok=True)
        
        log_file = os.path.join(
            self.log_dir,
            f"knowledge_{datetime.utcnow().strftime('%Y%m%d')}.jsonl"
        )
        
        with open(log_file, "a") as f:
            f.write(json.dumps(event) + "\n")
        
        self._entries_count += 1
        
        # Rotate if exceeded max entries
        if self._entries_count >= self.max_entries:
            self._rotate_logs()
    
    def _rotate_logs(self):
        """Rotate log files when max entries reached."""
        # Keep last 7 days of logs
        self._entries_count = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Return plugin statistics."""
        return {
            "name": self.name,
            "entries_logged": self._entries_count,
            "log_dir": self.log_dir,
            "max_entries": self.max_entries,
        }


# Register plugin
plugin_instance = KnowledgeLoggerPlugin()
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