"""Plugin Loader - File System Discovery

Based on Claude Code's skills/ loader pattern:
- Scan plugins/ directory for PLUGIN.md files
- Load plugin class from plugin.py
- Validate metadata
- Register with PluginManager

Directory structure:
    plugins/
    ├── reward-logger/
    │   ├── PLUGIN.md
    │   └── plugin.py
    ├── stage-tracker/
    │   ├── PLUGIN.md
    │   └── plugin.py
    └── experiment-filter/
        ├── PLUGIN.md
        └── plugin.py
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type
import os
import sys
import importlib.util
import logging

from .plugin_system import Plugin, PluginMeta, PluginManager

logger = logging.getLogger(__name__)


@dataclass
class PluginLoadResult:
    """Result of loading a plugin from disk"""
    name: str
    path: str
    success: bool
    plugin: Optional[Plugin] = None
    error: Optional[str] = None


def _parse_plugin_md(path: str) -> Dict[str, Any]:
    """
    Parse PLUGIN.md for metadata.
    
    Format:
        ---
        name: my-plugin
        version: 1.0.0
        description: What this plugin does
        hooks:
          - env:before_generate
          - exp:after_run
        priority: 50
        ---
    """
    meta: Dict[str, Any] = {}
    
    try:
        with open(path, 'r') as f:
            content = f.read()
        
        # Extract YAML front matter
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                front_matter = parts[1].strip()
                current_key = None
                
                for line in front_matter.splitlines():
                    # List item
                    if line.strip().startswith('- ') and current_key:
                        if not isinstance(meta.get(current_key), list):
                            meta[current_key] = []
                        meta[current_key].append(line.strip()[2:].strip())
                    elif ':' in line and not line.strip().startswith('-'):
                        key, _, val = line.partition(':')
                        key = key.strip()
                        val = val.strip()
                        current_key = key
                        if val:
                            meta[key] = val
                        else:
                            meta[key] = []  # Will be filled by list items
    except Exception as e:
        logger.warning(f"Failed to parse PLUGIN.md at {path}: {e}")
    
    return meta


def _load_plugin_class(plugin_py_path: str) -> Optional[Type[Plugin]]:
    """Load Plugin class from plugin.py"""
    try:
        spec = importlib.util.spec_from_file_location("plugin_module", plugin_py_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Find Plugin subclass
        for name, obj in vars(module).items():
            if (
                isinstance(obj, type)
                and issubclass(obj, Plugin)
                and obj is not Plugin
            ):
                return obj
        
        logger.warning(f"No Plugin subclass found in {plugin_py_path}")
        return None
        
    except Exception as e:
        logger.error(f"Failed to load plugin from {plugin_py_path}: {e}")
        return None


def load_plugin_from_dir(plugin_dir: str) -> PluginLoadResult:
    """
    Load a single plugin from a directory.
    
    Expects:
        plugin_dir/PLUGIN.md  (metadata)
        plugin_dir/plugin.py  (implementation)
    """
    name = os.path.basename(plugin_dir)
    plugin_md = os.path.join(plugin_dir, 'PLUGIN.md')
    plugin_py = os.path.join(plugin_dir, 'plugin.py')
    
    # Check files exist
    if not os.path.exists(plugin_py):
        return PluginLoadResult(
            name=name, path=plugin_dir, success=False,
            error=f"plugin.py not found in {plugin_dir}"
        )
    
    # Load class
    plugin_class = _load_plugin_class(plugin_py)
    if not plugin_class:
        return PluginLoadResult(
            name=name, path=plugin_dir, success=False,
            error=f"No Plugin subclass found in {plugin_py}"
        )
    
    # Override meta from PLUGIN.md if present
    if os.path.exists(plugin_md):
        md_meta = _parse_plugin_md(plugin_md)
        if md_meta:
            hooks = md_meta.get('hooks', plugin_class.meta.hooks)
            if isinstance(hooks, str):
                hooks = [hooks]
            
            plugin_class.meta = PluginMeta(
                name=md_meta.get('name', plugin_class.meta.name),
                version=md_meta.get('version', plugin_class.meta.version),
                description=md_meta.get('description', plugin_class.meta.description),
                hooks=hooks,
                priority=int(md_meta.get('priority', plugin_class.meta.priority)),
            )
    
    # Instantiate
    try:
        plugin = plugin_class()
        return PluginLoadResult(
            name=plugin.meta.name, path=plugin_dir,
            success=True, plugin=plugin
        )
    except Exception as e:
        return PluginLoadResult(
            name=name, path=plugin_dir, success=False,
            error=f"Failed to instantiate plugin: {e}"
        )


def discover_plugins(plugins_dir: str) -> List[PluginLoadResult]:
    """
    Discover and load all plugins from a directory.
    
    Scans for subdirectories containing plugin.py.
    
    Args:
        plugins_dir: Root directory to scan
    
    Returns:
        List of load results
    """
    results = []
    
    if not os.path.isdir(plugins_dir):
        logger.warning(f"Plugins directory not found: {plugins_dir}")
        return results
    
    for entry in sorted(os.listdir(plugins_dir)):
        entry_path = os.path.join(plugins_dir, entry)
        
        # Skip non-directories and hidden dirs
        if not os.path.isdir(entry_path) or entry.startswith('.'):
            continue
        
        # Skip __pycache__
        if entry == '__pycache__':
            continue
        
        result = load_plugin_from_dir(entry_path)
        results.append(result)
        
        if result.success:
            logger.info(f"Discovered plugin: {result.name} at {entry_path}")
        else:
            logger.warning(f"Failed to load plugin from {entry_path}: {result.error}")
    
    return results


def load_plugins_into_manager(
    manager: PluginManager,
    plugins_dir: str,
    auto_initialize: bool = True,
) -> Dict[str, Any]:
    """
    Discover plugins and register them with a PluginManager.
    
    Args:
        manager: PluginManager to register plugins into
        plugins_dir: Directory to scan
        auto_initialize: Whether to initialize plugins after loading
    
    Returns:
        Summary dict with loaded/failed counts
    """
    results = discover_plugins(plugins_dir)
    
    loaded = []
    failed = []
    
    for result in results:
        if result.success and result.plugin:
            manager.register(result.plugin)
            loaded.append(result.name)
        else:
            failed.append({'name': result.name, 'error': result.error})
    
    if auto_initialize and loaded:
        manager.initialize_all()
    
    summary = {
        'loaded': loaded,
        'failed': failed,
        'total': len(results),
        'success_count': len(loaded),
        'fail_count': len(failed),
    }
    
    logger.info(
        f"Plugin discovery complete: {len(loaded)} loaded, {len(failed)} failed"
    )
    
    return summary
