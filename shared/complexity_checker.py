"""简洁性准则检查器

借鉴 Karpathy 的理念：
"A small improvement that adds ugly complexity is not worth it."

评估添加新功能时的复杂度收益比。
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import re


@dataclass
class ComplexityScore:
    """复杂度评分"""
    total: float
    breakdown: Dict[str, float]
    details: str


@dataclass
class ImprovementScore:
    """改进评分"""
    total: float
    breakdown: Dict[str, float]
    details: str


@dataclass
class SimplicityEvaluation:
    """简洁性评估结果"""
    is_worth_it: bool
    improvement: ImprovementScore
    complexity: ComplexityScore
    penalty_threshold: float
    ratio: float
    recommendation: str


class ComplexityChecker:
    """简洁性准则检查器"""
    
    # 复杂度维度权重
    COMPLEXITY_WEIGHTS = {
        'code_lines': 0.2,
        'dependencies': 0.3,
        'abstractions': 0.2,
        'special_cases': 0.3,
    }
    
    # 改进维度权重
    IMPROVEMENT_WEIGHTS = {
        'performance': 0.4,
        'readability': 0.2,
        'maintainability': 0.2,
        'functionality': 0.2,
    }
    
    def __init__(self, penalty_threshold: float = 1.5):
        """
        初始化检查器
        
        Args:
            penalty_threshold: 复杂度惩罚阈值
                              改进 > 复杂度 * threshold 时才值得
        """
        self.penalty_threshold = penalty_threshold
    
    def evaluate_code_complexity(self, code: str) -> ComplexityScore:
        """
        评估代码复杂度
        
        Args:
            code: 代码字符串
        
        Returns:
            ComplexityScore: 复杂度评分
        """
        breakdown = {}
        
        # 1. 代码行数
        lines = code.split('\n')
        code_lines = len([l for l in lines if l.strip() and not l.strip().startswith('#')])
        breakdown['code_lines'] = self._normalize_code_lines(code_lines)
        
        # 2. 依赖数量
        imports = len(re.findall(r'^\s*(?:import|from)\s+', code, re.MULTILINE))
        breakdown['dependencies'] = self._normalize_dependencies(imports)
        
        # 3. 抽象层数量（类、装饰器、元类）
        classes = len(re.findall(r'^\s*class\s+\w+', code, re.MULTILINE))
        decorators = len(re.findall(r'^\s*@\w+', code, re.MULTILINE))
        breakdown['abstractions'] = self._normalize_abstractions(classes + decorators)
        
        # 4. 特殊处理数量（if/else、try/except、特殊分支）
        if_statements = len(re.findall(r'\bif\b', code))
        try_statements = len(re.findall(r'\btry\b', code))
        special_cases = if_statements + try_statements * 2
        breakdown['special_cases'] = self._normalize_special_cases(special_cases)
        
        # 计算总分
        total = sum(
            breakdown[dim] * weight
            for dim, weight in self.COMPLEXITY_WEIGHTS.items()
        )
        
        details = self._format_complexity_details(breakdown)
        
        return ComplexityScore(total=total, breakdown=breakdown, details=details)
    
    def evaluate_improvement(
        self,
        performance_gain: float = 0.0,
        readability_gain: float = 0.0,
        maintainability_gain: float = 0.0,
        functionality_gain: float = 0.0,
    ) -> ImprovementScore:
        """
        评估改进程度
        
        Args:
            performance_gain: 性能提升（0-1）
            readability_gain: 可读性提升（0-1）
            maintainability_gain: 可维护性提升（0-1）
            functionality_gain: 功能提升（0-1）
        
        Returns:
            ImprovementScore: 改进评分
        """
        breakdown = {
            'performance': max(0, min(1, performance_gain)),
            'readability': max(0, min(1, readability_gain)),
            'maintainability': max(0, min(1, maintainability_gain)),
            'functionality': max(0, min(1, functionality_gain)),
        }
        
        # 计算总分
        total = sum(
            breakdown[dim] * weight
            for dim, weight in self.IMPROVEMENT_WEIGHTS.items()
        )
        
        details = self._format_improvement_details(breakdown)
        
        return ImprovementScore(total=total, breakdown=breakdown, details=details)
    
    def evaluate(
        self,
        improvement: ImprovementScore,
        complexity: ComplexityScore,
    ) -> SimplicityEvaluation:
        """
        评估是否值得
        
        Args:
            improvement: 改进评分
            complexity: 复杂度评分
        
        Returns:
            SimplicityEvaluation: 评估结果
        """
        ratio = improvement.total / (complexity.total + 0.01)  # 避免除零
        is_worth_it = improvement.total > complexity.total * self.penalty_threshold
        
        if is_worth_it:
            if ratio > 2.0:
                recommendation = "✅ 强烈推荐：改进远大于复杂度"
            elif ratio > 1.5:
                recommendation = "✅ 推荐：改进大于复杂度"
            else:
                recommendation = "✅ 可接受：改进略大于复杂度"
        else:
            if ratio > 1.0:
                recommendation = "⚠️ 谨慎：复杂度略高于改进"
            elif ratio > 0.5:
                recommendation = "❌ 不推荐：复杂度明显高于改进"
            else:
                recommendation = "❌ 强烈不推荐：复杂度远高于改进"
        
        return SimplicityEvaluation(
            is_worth_it=is_worth_it,
            improvement=improvement,
            complexity=complexity,
            penalty_threshold=self.penalty_threshold,
            ratio=ratio,
            recommendation=recommendation,
        )
    
    def check_feature(
        self,
        code: str,
        performance_gain: float = 0.0,
        readability_gain: float = 0.0,
        maintainability_gain: float = 0.0,
        functionality_gain: float = 0.0,
    ) -> SimplicityEvaluation:
        """
        检查新功能是否值得添加
        
        Args:
            code: 新功能代码
            performance_gain: 性能提升（0-1）
            readability_gain: 可读性提升（0-1）
            maintainability_gain: 可维护性提升（0-1）
            functionality_gain: 功能提升（0-1）
        
        Returns:
            SimplicityEvaluation: 评估结果
        """
        complexity = self.evaluate_code_complexity(code)
        improvement = self.evaluate_improvement(
            performance_gain=performance_gain,
            readability_gain=readability_gain,
            maintainability_gain=maintainability_gain,
            functionality_gain=functionality_gain,
        )
        
        return self.evaluate(improvement, complexity)
    
    def _normalize_code_lines(self, lines: int) -> float:
        """标准化代码行数"""
        # 50 行以内：低复杂度
        # 50-100 行：中等复杂度
        # 100-200 行：高复杂度
        # 200+ 行：超高复杂度
        if lines <= 50:
            return lines / 50 * 0.3
        elif lines <= 100:
            return 0.3 + (lines - 50) / 50 * 0.3
        elif lines <= 200:
            return 0.6 + (lines - 100) / 100 * 0.3
        else:
            return 0.9 + min((lines - 200) / 200 * 0.1, 0.1)
    
    def _normalize_dependencies(self, count: int) -> float:
        """标准化依赖数量"""
        # 0-3 个：低复杂度
        # 3-7 个：中等复杂度
        # 7+ 个：高复杂度
        if count <= 3:
            return count / 3 * 0.3
        elif count <= 7:
            return 0.3 + (count - 3) / 4 * 0.3
        else:
            return 0.6 + min((count - 7) / 10 * 0.4, 0.4)
    
    def _normalize_abstractions(self, count: int) -> float:
        """标准化抽象层数量"""
        # 0-2 个：低复杂度
        # 2-5 个：中等复杂度
        # 5+ 个：高复杂度
        if count <= 2:
            return count / 2 * 0.3
        elif count <= 5:
            return 0.3 + (count - 2) / 3 * 0.3
        else:
            return 0.6 + min((count - 5) / 5 * 0.4, 0.4)
    
    def _normalize_special_cases(self, count: int) -> float:
        """标准化特殊处理数量"""
        # 0-5 个：低复杂度
        # 5-15 个：中等复杂度
        # 15+ 个：高复杂度
        if count <= 5:
            return count / 5 * 0.3
        elif count <= 15:
            return 0.3 + (count - 5) / 10 * 0.3
        else:
            return 0.6 + min((count - 15) / 15 * 0.4, 0.4)
    
    def _format_complexity_details(self, breakdown: Dict[str, float]) -> str:
        """格式化复杂度详情"""
        lines = ["Complexity Breakdown:"]
        for dim, score in breakdown.items():
            bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
            lines.append(f"  {dim:20s}: {bar} {score:.2f}")
        return "\n".join(lines)
    
    def _format_improvement_details(self, breakdown: Dict[str, float]) -> str:
        """格式化改进详情"""
        lines = ["Improvement Breakdown:"]
        for dim, score in breakdown.items():
            bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
            lines.append(f"  {dim:20s}: {bar} {score:.2f}")
        return "\n".join(lines)


# 全局检查器实例
_default_checker = ComplexityChecker()


def get_simplicity_checker() -> ComplexityChecker:
    """获取全局简洁性检查器"""
    return _default_checker


def is_worth_it(
    improvement: float,
    complexity: float,
    threshold: float = 1.5,
) -> bool:
    """
    快速判断是否值得
    
    Args:
        improvement: 改进分数（0-1）
        complexity: 复杂度分数（0-1）
        threshold: 惩罚阈值
    
    Returns:
        bool: 是否值得
    """
    return improvement > complexity * threshold


# 快捷函数：评估代码是否值得
def check_code(code: str) -> SimplicityEvaluation:
    """快速检查代码简洁性"""
    checker = get_simplicity_checker()
    return checker.evaluate_code_complexity(code)
