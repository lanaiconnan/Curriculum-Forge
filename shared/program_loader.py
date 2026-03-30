"""Program Loader - program.md 加载和验证

将 program.md 工作手册集成到 Agent A/B 的代码中，
实现自动加载和运行时验证。
"""

import os
import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple


@dataclass
class ProgramConstraints:
    """程序约束"""
    allowed: List[str]  # 能做什么
    forbidden: List[str]  # 不能做什么
    boundary_conditions: Dict[str, str]  # 边界条件


@dataclass
class ProgramMetrics:
    """程序指标"""
    primary: str  # 主要指标
    secondary: List[str]  # 次要指标
    thresholds: Dict[str, float]  # 阈值


@dataclass
class ProgramInfo:
    """程序信息"""
    agent_type: str  # Agent 类型
    version: str  # 版本
    constraints: ProgramConstraints  # 约束
    metrics: ProgramMetrics  # 指标
    raw_content: str  # 原始内容


class ProgramLoader:
    """program.md 加载器"""
    
    def __init__(self, base_path: str = None):
        """
        初始化加载器
        
        Args:
            base_path: 基础路径，默认当前目录
        """
        self.base_path = base_path or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    def load(self, agent_type: str) -> str:
        """
        加载指定 Agent 的 program.md
        
        Args:
            agent_type: Agent 类型 (agent_a, agent_b, shared)
        
        Returns:
            str: program.md 内容
        
        Raises:
            FileNotFoundError: 如果文件不存在
        """
        path = os.path.join(self.base_path, agent_type, 'program.md')
        
        if not os.path.exists(path):
            raise FileNotFoundError(f"program.md not found: {path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def load_info(self, agent_type: str) -> ProgramInfo:
        """
        加载并解析 program.md
        
        Args:
            agent_type: Agent 类型
        
        Returns:
            ProgramInfo: 解析后的程序信息
        """
        content = self.load(agent_type)
        
        # 提取版本
        version = self._extract_version(content)
        
        # 提取约束
        constraints = self._extract_constraints(content)
        
        # 提取指标
        metrics = self._extract_metrics(content)
        
        return ProgramInfo(
            agent_type=agent_type,
            version=version,
            constraints=constraints,
            metrics=metrics,
            raw_content=content,
        )
    
    def _extract_version(self, content: str) -> str:
        """提取版本号"""
        match = re.search(r'version：?\s*v?(\d+\.\d+)', content)
        if match:
            return match.group(1)
        
        match = re.search(r'>\s*version：?\s*v?(\d+\.\d+)', content)
        if match:
            return match.group(1)
        
        return "1.0"
    
    def _extract_constraints(self, content: str) -> ProgramConstraints:
        """提取约束列表"""
        allowed = []
        forbidden = []
        boundary_conditions = {}
        
        # 提取 ✅ 能做什么
        allowed_section = re.search(r'能做什么(.*?)(?=不能做什么|边界条件|##|\n\n|$)', content, re.DOTALL)
        if allowed_section:
            allowed = self._extract_lines_with_prefix(allowed_section.group(1), ['✅', '- '])
        
        # 提取 ❌ 不能做什么
        forbidden_section = re.search(r'不能做什么(.*?)(?=边界条件|##|\n\n|$)', content, re.DOTALL)
        if forbidden_section:
            forbidden = self._extract_lines_with_prefix(forbidden_section.group(1), ['❌', '- '])
        
        # 提取边界条件
        boundary_section = re.search(r'边界条件(.*?)(?=##|\n\n|$)', content, re.DOTALL)
        if boundary_section:
            boundary_conditions = self._extract_boundary_conditions(boundary_section.group(1))
        
        return ProgramConstraints(
            allowed=allowed,
            forbidden=forbidden,
            boundary_conditions=boundary_conditions,
        )
    
    def _extract_checkmarks(self, text: str, mark: str) -> List[str]:
        """提取标记项"""
        items = []
        pattern = rf'{mark}\s*(.+?)(?={mark}|✅|❌|[\n\n]|$)'
        matches = re.findall(pattern, text, re.DOTALL)
        
        for match in matches:
            item = match.strip()
            if item and len(item) > 2:
                items.append(item)
        
        return items
    
    def _extract_lines_with_prefix(self, text: str, prefixes: List[str]) -> List[str]:
        """提取带有指定前缀的行"""
        items = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            for prefix in prefixes:
                if line.startswith(prefix):
                    item = line[len(prefix):].strip()
                    if item and len(item) > 2:
                        items.append(item)
                    break
        
        return items
    
    def _extract_boundary_conditions(self, text: str) -> Dict[str, str]:
        """提取边界条件"""
        conditions = {}
        
        lines = text.split('\n')
        for line in lines:
            if ':' in line:
                key, value = line.split(':', 1)
                conditions[key.strip()] = value.strip()
        
        return conditions
    
    def _extract_metrics(self, content: str) -> ProgramMetrics:
        """提取指标"""
        primary = "keep_rate"
        secondary = []
        thresholds = {}
        
        # 提取主要指标
        primary_section = re.search(r'##\s*指标(.*?)(?=##|---|$)', content, re.DOTALL | re.IGNORECASE)
        if primary_section:
            section = primary_section.group(1)
            
            # 查找表格
            table = re.search(r'\|.*?\|.*?\|.*?\|', section)
            if table:
                lines = table.group(0).split('\n')
                for line in lines[1:]:  # 跳过表头
                    if '|' in line:
                        parts = [p.strip() for p in line.split('|') if p.strip()]
                        if len(parts) >= 2:
                            metric_name = parts[0]
                            description = parts[1]
                            
                            if 'keep_rate' in metric_name.lower():
                                primary = metric_name
                            
                            secondary.append(metric_name)
                            
                            # 提取阈值
                            threshold_match = re.search(r'>=?\s*([\d.]+)', description)
                            if threshold_match:
                                thresholds[metric_name] = float(threshold_match.group(1))
        
        return ProgramMetrics(
            primary=primary,
            secondary=secondary,
            thresholds=thresholds,
        )


class ProgramValidator:
    """program.md 验证器"""
    
    # Agent A 禁止修改的文件（硬编码，与 program.md 保持一致）
    AGENT_A_FORBIDDEN = ['agent_b', 'rl/trainer.py', 'shared/results.py']
    
    # Agent B 禁止修改的文件
    AGENT_B_FORBIDDEN = ['agent_a', 'tools/base.py', 'shared/results.py']
    
    def __init__(self, loader: ProgramLoader = None):
        """
        初始化验证器
        
        Args:
            loader: program.md 加载器
        """
        self.loader = loader or ProgramLoader()
        self._cache: Dict[str, ProgramInfo] = {}
    
    def get_info(self, agent_type: str) -> ProgramInfo:
        """
        获取程序信息（带缓存）
        
        Args:
            agent_type: Agent 类型
        
        Returns:
            ProgramInfo: 程序信息
        """
        if agent_type not in self._cache:
            self._cache[agent_type] = self.loader.load_info(agent_type)
        
        return self._cache[agent_type]
    
    def validate_action(self, agent_type: str, action: str) -> Tuple[bool, Optional[str]]:
        """
        验证动作是否符合手册
        
        Args:
            agent_type: Agent 类型
            action: 动作描述
        
        Returns:
            Tuple[bool, Optional[str]]: (是否允许, 原因)
        """
        # 首先检查硬编码的禁止规则
        if agent_type == 'agent_a':
            for forbidden in self.AGENT_A_FORBIDDEN:
                if forbidden in action:
                    return False, f"Action '{action}' is forbidden by program.md: Agent A cannot modify {forbidden}"
        
        elif agent_type == 'agent_b':
            for forbidden in self.AGENT_B_FORBIDDEN:
                if forbidden in action:
                    return False, f"Action '{action}' is forbidden by program.md: Agent B cannot modify {forbidden}"
        
        # 然后检查从 program.md 解析的约束
        try:
            info = self.get_info(agent_type)
            constraints = info.constraints
            
            # 检查禁止的动作
            for forbidden in constraints.forbidden:
                if self._matches_action(action, forbidden):
                    return False, f"Action '{action}' is forbidden by program.md: {forbidden}"
            
            # 检查是否在允许列表中（如果列表非空）
            if constraints.allowed:
                for allowed in constraints.allowed:
                    if self._matches_action(action, allowed):
                        return True, None
                
                # 如果有允许列表但不在其中，则不允许
                return False, f"Action '{action}' is not in the allowed list"
        except Exception as e:
            # 如果解析失败，使用硬编码规则
            pass
        
        # 没有明确的禁止，则允许
        return True, None
    
    def _matches_action(self, action: str, pattern: str) -> bool:
        """
        检查动作是否匹配模式
        
        Args:
            action: 动作描述
            pattern: 模式（可以是正则表达式）
        
        Returns:
            bool: 是否匹配
        """
        # 简单包含检查
        if pattern.lower() in action.lower():
            return True
        
        # 正则表达式匹配
        try:
            if re.search(pattern, action, re.IGNORECASE):
                return True
        except:
            pass
        
        return False
    
    def validate_file_modification(self, agent_type: str, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        验证文件修改是否允许
        
        Args:
            agent_type: Agent 类型
            file_path: 文件路径
        
        Returns:
            Tuple[bool, Optional[str]]: (是否允许, 原因)
        """
        action = f"modify:{file_path}"
        return self.validate_action(agent_type, action)
    
    def validate_metric(self, agent_type: str, metric_name: str, value: float) -> Tuple[bool, str]:
        """
        验证指标是否达标
        
        Args:
            agent_type: Agent 类型
            metric_name: 指标名称
            value: 指标值
        
        Returns:
            Tuple[bool, str]: (是否达标, 状态描述)
        """
        info = self.get_info(agent_type)
        thresholds = info.metrics.thresholds
        
        if metric_name not in thresholds:
            return True, f"Metric '{metric_name}' has no threshold defined"
        
        threshold = thresholds[metric_name]
        
        if 'keep_rate' in metric_name:
            if value >= threshold:
                return True, f"✅ {metric_name}: {value:.1%} >= {threshold:.1%}"
            else:
                return False, f"❌ {metric_name}: {value:.1%} < {threshold:.1%}"
        else:
            if value >= threshold:
                return True, f"✅ {metric_name}: {value:.2f} >= {threshold:.2f}"
            else:
                return False, f"❌ {metric_name}: {value:.2f} < {threshold:.2f}"
    
    def get_allowed_files(self, agent_type: str) -> List[str]:
        """
        获取允许修改的文件列表
        
        Args:
            agent_type: Agent 类型
        
        Returns:
            List[str]: 允许修改的文件列表
        """
        info = self.get_info(agent_type)
        
        # 从约束中提取文件列表
        allowed_files = []
        for allowed in info.constraints.allowed:
            if 'modify' in allowed.lower() or '.py' in allowed.lower():
                allowed_files.append(allowed)
        
        return allowed_files
    
    def get_forbidden_files(self, agent_type: str) -> List[str]:
        """
        获取禁止修改的文件列表
        
        Args:
            agent_type: Agent 类型
        
        Returns:
            List[str]: 禁止修改的文件列表
        """
        info = self.get_info(agent_type)
        
        # 从约束中提取文件列表
        forbidden_files = []
        for forbidden in info.constraints.forbidden:
            if 'modify' in forbidden.lower() or '.py' in forbidden.lower():
                forbidden_files.append(forbidden)
        
        return forbidden_files
    
    def print_summary(self, agent_type: str):
        """
        打印程序摘要
        
        Args:
            agent_type: Agent 类型
        """
        info = self.get_info(agent_type)
        
        print(f"\n📋 Program Summary: {agent_type}")
        print(f"   Version: {info.version}")
        print(f"\n✅ Allowed Actions ({len(info.constraints.allowed)}):")
        for action in info.constraints.allowed[:5]:
            print(f"   • {action[:60]}")
        if len(info.constraints.allowed) > 5:
            print(f"   ... and {len(info.constraints.allowed) - 5} more")
        
        print(f"\n❌ Forbidden Actions ({len(info.constraints.forbidden)}):")
        for action in info.constraints.forbidden[:5]:
            print(f"   • {action[:60]}")
        if len(info.constraints.forbidden) > 5:
            print(f"   ... and {len(info.constraints.forbidden) - 5} more")
        
        print(f"\n📊 Metrics Thresholds:")
        for metric, threshold in info.metrics.thresholds.items():
            if 'keep_rate' in metric:
                print(f"   • {metric}: {threshold:.1%}")
            else:
                print(f"   • {metric}: {threshold:.2f}")


# 全局实例
_default_loader = None
_default_validator = None


def get_program_loader() -> ProgramLoader:
    """获取全局加载器"""
    global _default_loader
    if _default_loader is None:
        _default_loader = ProgramLoader()
    return _default_loader


def get_program_validator() -> ProgramValidator:
    """获取全局验证器"""
    global _default_validator
    if _default_validator is None:
        _default_validator = ProgramValidator()
    return _default_validator
