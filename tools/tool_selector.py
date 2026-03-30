"""Tool Selector - 智能工具选择器

基于任务描述自动选择最合适的工具
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class ToolCandidate:
    """工具候选"""
    name: str
    score: float
    reason: str
    params: Dict[str, Any] = field(default_factory=dict)


class ToolSelector:
    """
    智能工具选择器
    
    功能：
    1. 基于任务描述选择工具
    2. 参数推断
    3. 工具组合建议
    """
    
    def __init__(self, tools: List[str] = None):
        self.tools = tools or ['git', 'moon', 'memory']
        
        # 工具能力描述
        self.tool_capabilities = {
            'git': {
                'keywords': ['commit', 'push', 'pull', 'branch', 'merge', 'repo', 'git', '版本', '提交'],
                'description': 'Git 版本控制操作',
                'params': ['action', 'repo', 'branch', 'message'],
            },
            'moon': {
                'keywords': ['moon', 'api', 'query', 'search', 'fetch', '数据', '查询'],
                'description': 'Moon API 数据查询',
                'params': ['query', 'filters', 'limit'],
            },
            'memory': {
                'keywords': ['remember', 'recall', 'save', 'load', 'memory', '记忆', '保存'],
                'description': '记忆管理操作',
                'params': ['action', 'key', 'value'],
            },
        }
    
    def select(
        self,
        task_description: str,
        top_k: int = 3,
    ) -> List[ToolCandidate]:
        """
        选择最合适的工具
        
        Args:
            task_description: 任务描述
            top_k: 返回前 k 个候选
        
        Returns:
            List[ToolCandidate]: 工具候选列表
        """
        candidates = []
        
        for tool_name in self.tools:
            capability = self.tool_capabilities.get(tool_name, {})
            keywords = capability.get('keywords', [])
            
            # 计算匹配分数
            score = 0.0
            matched_keywords = []
            
            for keyword in keywords:
                if keyword.lower() in task_description.lower():
                    score += 1.0
                    matched_keywords.append(keyword)
            
            # 归一化
            if keywords:
                score = score / len(keywords)
            
            if score > 0:
                reason = f"匹配关键词: {', '.join(matched_keywords)}"
                candidates.append(ToolCandidate(
                    name=tool_name,
                    score=score,
                    reason=reason,
                ))
        
        # 排序
        candidates.sort(key=lambda x: x.score, reverse=True)
        
        return candidates[:top_k]
    
    def infer_params(
        self,
        tool_name: str,
        task_description: str,
    ) -> Dict[str, Any]:
        """
        推断工具参数
        
        Args:
            tool_name: 工具名称
            task_description: 任务描述
        
        Returns:
            Dict[str, Any]: 推断的参数
        """
        params = {}
        
        if tool_name == 'git':
            # 推断 Git 操作
            if 'commit' in task_description.lower():
                params['action'] = 'commit'
            elif 'push' in task_description.lower():
                params['action'] = 'push'
            elif 'pull' in task_description.lower():
                params['action'] = 'pull'
            
            # 提取分支名
            branch_match = re.search(r'branch[:\s]+(\S+)', task_description, re.I)
            if branch_match:
                params['branch'] = branch_match.group(1)
        
        elif tool_name == 'moon':
            # 推断查询
            params['query'] = task_description
        
        elif tool_name == 'memory':
            # 推断记忆操作
            if 'save' in task_description.lower() or 'remember' in task_description.lower():
                params['action'] = 'save'
            elif 'recall' in task_description.lower() or 'load' in task_description.lower():
                params['action'] = 'load'
        
        return params
    
    def suggest_combination(
        self,
        task_description: str,
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """
        建议工具组合
        
        Args:
            task_description: 任务描述
        
        Returns:
            List[Tuple[str, Dict]]: 工具和参数的组合
        """
        candidates = self.select(task_description, top_k=5)
        
        combination = []
        for candidate in candidates:
            params = self.infer_params(candidate.name, task_description)
            combination.append((candidate.name, params))
        
        return combination