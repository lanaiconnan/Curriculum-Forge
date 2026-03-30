"""工具层"""

import os
from .base import Tool, ToolResult
from .git import GitTool
from .moon import MoonTool
from .memory import MemoryManager, MemoryBlock, CoreMemory, ArchivalMemory, RecallMemory


class ToolRegistry:
    """工具注册表"""
    
    def __init__(self, cwd: str = ".", agent_id: str = "default"):
        self.cwd = cwd
        self.agent_id = agent_id
        self._tools = {}
        self._memory_managers = {}  # 每个 Agent 的记忆管理器
        self._enabled = []
        self._register_defaults()
    
    def _register_defaults(self):
        self.register(GitTool(self.cwd))
        self.register(MoonTool(self.cwd))
    
    def register(self, tool: Tool):
        self._tools[tool.name] = tool
    
    def enable(self, name: str):
        if name in self._tools and name not in self._enabled:
            self._enabled.append(name)
    
    def disable(self, name: str):
        if name in self._enabled:
            self._enabled.remove(name)
    
    def execute(self, name: str, params: dict) -> ToolResult:
        if name not in self._enabled:
            return ToolResult(False, "", f"Tool '{name}' not enabled")
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(False, "", f"Tool '{name}' not found")
        return tool.execute(params)
    
    # ========== Memory Management ==========
    
    def get_memory_manager(self, agent_id: str = None) -> MemoryManager:
        """获取或创建记忆管理器"""
        agent_id = agent_id or self.agent_id
        if agent_id not in self._memory_managers:
            self._memory_managers[agent_id] = MemoryManager(
                agent_id=agent_id,
                storage_dir=os.path.join(self.cwd, f".memory/{agent_id}")
            )
        return self._memory_managers[agent_id]
    
    def save_all_memories(self):
        """保存所有 Agent 的记忆"""
        for manager in self._memory_managers.values():
            manager.save()


def create_registry(cwd: str = ".", tools: list = None, agent_id: str = "default") -> ToolRegistry:
    """创建工具注册表"""
    import os
    registry = ToolRegistry(cwd, agent_id)
    if tools:
        registry._enabled = []
        for t in tools:
            registry.enable(t)
    else:
        registry._enabled = list(registry._tools.keys())
    return registry
