"""工具基类 - ToolRL 核心组件"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    output: str
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_context(self) -> str:
        if self.success:
            return f"OK: {self.output}"
        else:
            return f"ERROR: {self.error}"


class Tool(ABC):
    """工具基类"""
    
    name: str = "base_tool"
    description: str = "Tool description"
    
    @abstractmethod
    def execute(self, params: Dict) -> ToolResult:
        pass
    
    def validate_params(self, params: Dict) -> tuple:
        # 返回 (bool, Optional[str])
        return (True, None)
    
    def get_prompt_description(self) -> str:
        return f"Tool: {self.name}\n{self.description}"
