"""Tool Selector - 智能工具选择器 + ReAct 推理模式

基于任务描述自动选择最合适的工具
支持 ReAct (Reasoning + Acting) 推理模式
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import re
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class ToolCandidate:
    """工具候选"""
    name: str
    score: float
    reason: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReActStep:
    """ReAct 推理步骤"""
    step: int
    thought: str
    action: str
    action_input: str
    observation: str = ""
    is_final: bool = False


class ToolSelector:
    """
    智能工具选择器 + ReAct 推理模式
    
    功能：
    1. 基于任务描述选择工具（关键词匹配）
    2. 参数推断
    3. 工具组合建议
    4. ReAct 推理链（新增）
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
    
    # ==================== ReAct 推理模式 ====================
    
    def react_reason(
        self,
        task_description: str,
        max_steps: int = 5,
    ) -> List[ReActStep]:
        """
        ReAct 推理链
        
        流程：Thought → Action → Observation → Thought → ...
        
        来自 "ReAct: Synergizing Reasoning and Acting in Language Models"
        
        Args:
            task_description: 任务描述
            max_steps: 最大推理步数
        
        Returns:
            List[ReActStep]: 推理步骤列表
        """
        steps = []
        
        # Step 1: 初始思考
        initial_thought = self._generate_initial_thought(task_description)
        
        # 选择工具
        candidates = self.select(task_description, top_k=3)
        
        if not candidates:
            # 没有匹配的工具
            steps.append(ReActStep(
                step=1,
                thought=initial_thought,
                action="no_tool",
                action_input="",
                observation="No suitable tools found for this task",
                is_final=True,
            ))
            return steps
        
        # 生成 Action 序列
        for i, candidate in enumerate(candidates[:max_steps]):
            params = self.infer_params(candidate.name, task_description)
            
            thought = self._generate_thought(i, candidate, task_description)
            action = candidate.name
            action_input = json.dumps(params) if params else ""
            
            # 模拟 Observation（实际应用中由工具执行返回）
            observation = self._simulate_observation(candidate.name, params)
            
            is_final = (i == len(candidates[:max_steps]) - 1)
            
            steps.append(ReActStep(
                step=i + 1,
                thought=thought,
                action=action,
                action_input=action_input,
                observation=observation,
                is_final=is_final,
            ))
        
        return steps
    
    def _generate_initial_thought(self, task: str) -> str:
        """生成初始思考"""
        # 分析任务类型
        task_lower = task.lower()
        
        if 'commit' in task_lower or 'push' in task_lower:
            return f"任务涉及版本控制操作。需要使用 git 工具。"
        elif 'query' in task_lower or 'fetch' in task_lower or '数据' in task_lower:
            return f"任务涉及数据查询。需要使用 moon 工具。"
        elif 'memory' in task_lower or 'remember' in task_lower or '保存' in task_lower:
            return f"任务涉及记忆操作。需要使用 memory 工具。"
        else:
            return f"分析任务 '{task[:50]}...'，寻找合适的工具。"
    
    def _generate_thought(
        self,
        step_index: int,
        candidate: ToolCandidate,
        task: str,
    ) -> str:
        """生成推理步骤的思考"""
        templates = [
            f"第一步：使用 {candidate.name} 工具。理由：{candidate.reason}",
            f"第二步：如果 {candidate.name} 成功，继续下一步。",
            f"第三步：综合结果，完成任务。",
        ]
        
        if step_index < len(templates):
            return templates[step_index]
        
        return f"步骤 {step_index + 1}：执行 {candidate.name}。"
    
    def _simulate_observation(
        self,
        tool_name: str,
        params: Dict[str, Any],
    ) -> str:
        """
        模拟 Observation（实际应用中由真实工具执行返回）
        
        在生产环境中，这里应该：
        1. 调用真实工具
        2. 获取执行结果
        3. 返回观察结果
        """
        observations = {
            'git': f"Git 操作完成。参数: {params}",
            'moon': f"Moon 查询完成。返回 10 条结果。",
            'memory': f"记忆操作完成。已 {'保存' if params.get('action') == 'save' else '加载'}。",
        }
        
        return observations.get(tool_name, f"工具 {tool_name} 执行完成。")
    
    def react_execute(
        self,
        task_description: str,
        tool_executor: callable = None,
    ) -> Dict[str, Any]:
        """
        执行 ReAct 推理并返回最终结果
        
        Args:
            task_description: 任务描述
            tool_executor: 工具执行函数（可选）
        
        Returns:
            Dict[str, Any]: 执行结果
        """
        steps = self.react_reason(task_description)
        
        results = {
            'task': task_description,
            'steps': [],
            'final_answer': '',
            'success': False,
        }
        
        for step in steps:
            step_result = {
                'step': step.step,
                'thought': step.thought,
                'action': step.action,
                'action_input': step.action_input,
                'observation': step.observation,
            }
            results['steps'].append(step_result)
            
            # 如果有真实执行器，调用它
            if tool_executor and step.action != "no_tool":
                try:
                    params = json.loads(step.action_input) if step.action_input else {}
                    real_observation = tool_executor(step.action, params)
                    step_result['observation'] = real_observation
                except Exception as e:
                    step_result['observation'] = f"Error: {e}"
        
        # 生成最终答案
        if steps:
            last_step = steps[-1]
            results['final_answer'] = f"完成 {len(steps)} 个步骤。最后操作: {last_step.action}"
            results['success'] = last_step.action != "no_tool"
        
        return results
    
    def react_format(self, steps: List[ReActStep]) -> str:
        """
        格式化 ReAct 推理链为可读文本
        
        Args:
            steps: 推理步骤
        
        Returns:
            str: 格式化文本
        """
        lines = ["=== ReAct 推理链 ==="]
        
        for step in steps:
            lines.append(f"\nStep {step.step}:")
            lines.append(f"  Thought: {step.thought}")
            lines.append(f"  Action: {step.action}")
            if step.action_input:
                lines.append(f"  Action Input: {step.action_input}")
            lines.append(f"  Observation: {step.observation}")
        
        return "\n".join(lines)


class ReActAgent:
    """
    ReAct Agent - 封装完整的 ReAct 推理循环
    
    来自 Flowise 的灵感：
    - Thought → Action → Observation 循环
    - 支持多轮推理
    - 自动终止判断
    """
    
    def __init__(
        self,
        tools: List[str] = None,
        max_iterations: int = 5,
        verbose: bool = False,
    ):
        """
        初始化 ReAct Agent
        
        Args:
            tools: 可用工具列表
            max_iterations: 最大迭代次数
            verbose: 是否输出详细日志
        """
        self.selector = ToolSelector(tools)
        self.max_iterations = max_iterations
        self.verbose = verbose
        self.history: List[ReActStep] = []
    
    def run(self, task: str, tool_executor: callable = None) -> Dict[str, Any]:
        """
        运行 ReAct 循环
        
        Args:
            task: 任务描述
            tool_executor: 工具执行函数
        
        Returns:
            Dict[str, Any]: 执行结果
        """
        self.history = []
        
        # 生成推理步骤
        steps = self.selector.react_reason(task, max_steps=self.max_iterations)
        self.history = steps
        
        # 执行
        result = self.selector.react_execute(task, tool_executor)
        
        if self.verbose:
            print(self.selector.react_format(steps))
        
        return result
    
    def get_history(self) -> List[ReActStep]:
        """获取推理历史"""
        return self.history
    
    def reset(self):
        """重置状态"""
        self.history = []