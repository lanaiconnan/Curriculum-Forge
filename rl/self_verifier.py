"""SelfVerifier - 自我验证机制

基于 AutoDidact 的自验证理念，
验证 Agent 决策的正确性。
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime


@dataclass
class VerificationIssue:
    """验证问题"""
    severity: str  # critical, major, minor
    category: str  # tool_selection, parameter, logic, timing
    description: str
    affected_item: str
    suggestion: str


@dataclass
class VerificationResult:
    """验证结果"""
    verified: bool  # 是否通过验证
    confidence: float  # 置信度 0-1
    exact_match: bool  # 精确匹配
    partial_match: float  # 部分匹配
    issues: List[VerificationIssue]  # 发现的问题
    suggestions: List[str]  # 改进建议
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_verdict(self) -> str:
        """获取判定结果"""
        if self.confidence >= 0.8 and self.verified:
            return "excellent"
        elif self.confidence >= 0.6:
            return "good"
        elif self.confidence >= 0.4:
            return "fair"
        else:
            return "poor"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'verified': self.verified,
            'confidence': self.confidence,
            'exact_match': self.exact_match,
            'partial_match': self.partial_match,
            'verdict': self.get_verdict(),
            'issues': [
                {
                    'severity': i.severity,
                    'category': i.category,
                    'description': i.description,
                    'suggestion': i.suggestion,
                }
                for i in self.issues
            ],
            'suggestions': self.suggestions,
        }


@dataclass
class VerificationContext:
    """验证上下文"""
    trajectory: Dict[str, Any]  # 轨迹数据
    expected: Dict[str, Any]  # 期望结果
    actual: Dict[str, Any]  # 实际结果
    metadata: Dict[str, Any] = field(default_factory=dict)


class SelfVerifier:
    """
    自我验证器
    
    功能：
    1. 验证工具选择的正确性
    2. 验证参数的正确性
    3. 识别问题并提供建议
    4. 计算置信度
    """
    
    # 验证阈值
    VERIFICATION_THRESHOLD = 0.7
    EXACT_MATCH_THRESHOLD = 0.9
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化验证器
        
        Args:
            config: 配置字典
        """
        self.config = config or {}
        self.history: List[VerificationResult] = []
    
    def verify(self, context: VerificationContext) -> VerificationResult:
        """
        验证决策的正确性
        
        Args:
            context: 验证上下文
        
        Returns:
            VerificationResult: 验证结果
        """
        # 1. 验证工具选择
        tool_verification = self._verify_tools(
            context.trajectory.get('predicted_tools', []),
            context.expected.get('tools', [])
        )
        
        # 2. 验证参数
        param_verification = self._verify_params(
            context.trajectory.get('predicted_params', {}),
            context.expected.get('params', {})
        )
        
        # 3. 识别问题
        issues = self._identify_issues(
            tool_verification,
            param_verification
        )
        
        # 4. 生成建议
        suggestions = self._generate_suggestions(issues)
        
        # 5. 计算置信度
        confidence = self._calculate_confidence(
            tool_verification,
            param_verification
        )
        
        # 6. 综合判定
        verified = confidence >= self.VERIFICATION_THRESHOLD
        
        result = VerificationResult(
            verified=verified,
            confidence=confidence,
            exact_match=tool_verification['exact_match'],
            partial_match=tool_verification['partial_match'],
            issues=issues,
            suggestions=suggestions,
            metadata={
                'tool_match': tool_verification,
                'param_match': param_verification,
                'timestamp': datetime.now().isoformat(),
            }
        )
        
        # 保存历史
        self.history.append(result)
        
        return result
    
    def _verify_tools(
        self,
        predicted: List[str],
        expected: List[str]
    ) -> Dict[str, Any]:
        """验证工具选择"""
        predicted_set = set(predicted) if predicted else set()
        expected_set = set(expected) if expected else set()
        
        if not predicted_set and not expected_set:
            return {
                'exact_match': True,
                'partial_match': 1.0,
                'missing': [],
                'extra': [],
                'correct': [],
            }
        
        # 计算匹配
        correct = predicted_set & expected_set
        missing = expected_set - predicted_set
        extra = predicted_set - expected_set
        
        # Jaccard 相似度
        union = predicted_set | expected_set
        jaccard = len(correct) / len(union) if union else 0
        
        # 精确匹配
        exact_match = predicted_set == expected_set
        
        return {
            'exact_match': exact_match,
            'partial_match': jaccard,
            'missing': list(missing),
            'extra': list(extra),
            'correct': list(correct),
        }
    
    def _verify_params(
        self,
        predicted: Dict[str, Any],
        expected: Dict[str, Any]
    ) -> Dict[str, Any]:
        """验证参数"""
        pred_keys = set(predicted.keys()) if predicted else set()
        exp_keys = set(expected.keys()) if expected else set()
        
        if not pred_keys and not exp_keys:
            return {
                'exact_match': True,
                'partial_match': 1.0,
                'missing_keys': [],
                'extra_keys': [],
                'matching_params': {},
                'mismatching_params': {},
            }
        
        # 计算匹配
        common_keys = pred_keys & exp_keys
        missing_keys = exp_keys - pred_keys
        extra_keys = pred_keys - exp_keys
        
        matching = {}
        mismatching = {}
        
        for key in common_keys:
            if predicted[key] == expected[key]:
                matching[key] = predicted[key]
            else:
                mismatching[key] = {
                    'predicted': predicted[key],
                    'expected': expected[key]
                }
        
        # 计算匹配率
        total_keys = len(pred_keys | exp_keys)
        match_ratio = len(common_keys) / total_keys if total_keys > 0 else 0
        
        return {
            'exact_match': pred_keys == exp_keys and not mismatching,
            'partial_match': match_ratio,
            'missing_keys': list(missing_keys),
            'extra_keys': list(extra_keys),
            'matching_params': matching,
            'mismatching_params': mismatching,
        }
    
    def _identify_issues(
        self,
        tool_verification: Dict,
        param_verification: Dict
    ) -> List[VerificationIssue]:
        """识别问题"""
        issues = []
        
        # 检查工具问题
        if tool_verification['missing']:
            issues.append(VerificationIssue(
                severity="major" if len(tool_verification['missing']) > 1 else "minor",
                category="tool_selection",
                description=f"缺少工具: {', '.join(tool_verification['missing'])}",
                affected_item="predicted_tools",
                suggestion="考虑添加这些工具到预测中"
            ))
        
        if tool_verification['extra']:
            issues.append(VerificationIssue(
                severity="minor",
                category="tool_selection",
                description=f"多余工具: {', '.join(tool_verification['extra'])}",
                affected_item="predicted_tools",
                suggestion="检查是否需要这些工具"
            ))
        
        # 检查参数问题
        if param_verification['missing_keys']:
            issues.append(VerificationIssue(
                severity="major",
                category="parameter",
                description=f"缺少参数: {', '.join(param_verification['missing_keys'])}",
                affected_item="predicted_params",
                suggestion="添加缺失的参数"
            ))
        
        if param_verification['extra_keys']:
            issues.append(VerificationIssue(
                severity="minor",
                category="parameter",
                description=f"多余参数: {', '.join(param_verification['extra_keys'])}",
                affected_item="predicted_params",
                suggestion="移除不必要的参数"
            ))
        
        if param_verification['mismatching_params']:
            issues.append(VerificationIssue(
                severity="major",
                category="parameter",
                description=f"参数值不匹配: {', '.join(param_verification['mismatching_params'].keys())}",
                affected_item="predicted_params",
                suggestion="调整参数值以匹配期望"
            ))
        
        return issues
    
    def _generate_suggestions(self, issues: List[VerificationIssue]) -> List[str]:
        """生成建议"""
        suggestions = []
        
        # 基于问题数量生成建议
        if not issues:
            suggestions.append("当前决策完全正确，继续保持")
            return suggestions
        
        major_issues = [i for i in issues if i.severity in ['major', 'critical']]
        minor_issues = [i for i in issues if i.severity == 'minor']
        
        if major_issues:
            suggestions.append(f"发现 {len(major_issues)} 个主要问题，需要优先修复")
        
        if minor_issues:
            suggestions.append(f"发现 {len(minor_issues)} 个次要问题，可以逐步优化")
        
        # 基于问题类别生成建议
        categories = set(i.category for i in issues)
        
        if 'tool_selection' in categories:
            suggestions.append("建议重新审视工具选择策略")
        
        if 'parameter' in categories:
            suggestions.append("建议检查参数设置的合理性")
        
        return suggestions
    
    def _calculate_confidence(
        self,
        tool_verification: Dict,
        param_verification: Dict
    ) -> float:
        """计算置信度"""
        # 工具匹配权重
        tool_weight = 0.6
        param_weight = 0.4
        
        # 计算工具置信度
        tool_confidence = tool_verification['partial_match']
        if tool_verification['exact_match']:
            tool_confidence = 1.0
        
        # 计算参数置信度
        param_confidence = param_verification['partial_match']
        if param_verification['exact_match']:
            param_confidence = 1.0
        
        # 加权平均
        confidence = (
            tool_confidence * tool_weight +
            param_confidence * param_weight
        )
        
        return min(1.0, max(0.0, confidence))
    
    def get_history(self) -> List[VerificationResult]:
        """获取验证历史"""
        return self.history
    
    def get_latest(self) -> Optional[VerificationResult]:
        """获取最新验证结果"""
        return self.history[-1] if self.history else None
    
    def get_average_confidence(self) -> float:
        """获取平均置信度"""
        if not self.history:
            return 0.0
        return sum(r.confidence for r in self.history) / len(self.history)
    
    def get_verification_rate(self) -> float:
        """获取验证通过率"""
        if not self.history:
            return 0.0
        return sum(1 for r in self.history if r.verified) / len(self.history)
    
    def print_summary(self):
        """打印验证摘要"""
        print(f"\n📊 SelfVerifier Summary")
        print(f"   Total verifications: {len(self.history)}")
        
        if self.history:
            avg_confidence = self.get_average_confidence()
            verification_rate = self.get_verification_rate()
            
            print(f"   Average confidence: {avg_confidence:.1%}")
            print(f"   Verification rate: {verification_rate:.1%}")
            
            # 统计问题
            all_issues = []
            for result in self.history:
                all_issues.extend(result.issues)
            
            if all_issues:
                print(f"\n   Issues breakdown:")
                categories = {}
                for issue in all_issues:
                    categories[issue.category] = categories.get(issue.category, 0) + 1
                
                for cat, count in sorted(categories.items()):
                    print(f"      - {cat}: {count}")
        else:
            print("   No verifications yet")


class ConfidenceTracker:
    """
    置信度追踪器
    
    功能：
    1. 追踪置信度变化
    2. 检测趋势
    3. 提供预警
    """
    
    def __init__(self, window_size: int = 10):
        """
        初始化追踪器
        
        Args:
            window_size: 滑动窗口大小
        """
        self.window_size = window_size
        self.scores: List[float] = []
        self.timestamps: List[str] = []
    
    def add(self, confidence: float, metadata: Dict[str, Any] = None):
        """
        添加置信度记录
        
        Args:
            confidence: 置信度值 (0-1)
            metadata: 元数据
        """
        self.scores.append(confidence)
        self.timestamps.append(datetime.now().isoformat())
        
        # 保持窗口大小
        if len(self.scores) > self.window_size:
            self.scores = self.scores[-self.window_size:]
            self.timestamps = self.timestamps[-self.window_size:]
    
    def get_trend(self) -> str:
        """
        获取置信度趋势
        
        Returns:
            str: 趋势 (increasing, decreasing, stable, insufficient_data)
        """
        if len(self.scores) < 3:
            return "insufficient_data"
        
        # 计算最近的变化
        recent = self.scores[-3:]
        first = recent[0]
        last = recent[-1]
        
        change = (last - first) / first if first > 0 else 0
        
        if change > 0.1:
            return "increasing"
        elif change < -0.1:
            return "decreasing"
        else:
            return "stable"
    
    def get_average(self) -> float:
        """获取平均置信度"""
        if not self.scores:
            return 0.0
        return sum(self.scores) / len(self.scores)
    
    def get_variance(self) -> float:
        """获取置信度方差"""
        if len(self.scores) < 2:
            return 0.0
        
        avg = self.get_average()
        return sum((s - avg) ** 2 for s in self.scores) / len(self.scores)
    
    def get_stability(self) -> float:
        """
        获取稳定性（1 - 归一化方差）
        """
        variance = self.get_variance()
        # 归一化到 0-1
        stability = 1.0 - min(1.0, variance * 10)
        return max(0.0, stability)
    
    def should_alert(self) -> Tuple[bool, str]:
        """
        检查是否应该发出预警
        
        Returns:
            Tuple[bool, str]: (是否预警, 原因)
        """
        if not self.scores:
            return False, ""
        
        # 检查最近置信度
        recent_avg = sum(self.scores[-3:]) / min(3, len(self.scores))
        
        if recent_avg < 0.5:
            return True, f"置信度过低: {recent_avg:.1%}"
        
        # 检查趋势
        trend = self.get_trend()
        if trend == "decreasing":
            # 检查是否持续下降
            if len(self.scores) >= 5:
                last_5 = self.scores[-5:]
                if all(last_5[i] > last_5[i+1] for i in range(len(last_5)-1)):
                    return True, "置信度持续下降"
        
        # 检查方差
        if self.get_variance() > 0.1:
            return True, f"置信度波动较大 (方差: {self.get_variance():.3f})"
        
        return False, ""
    
    def get_summary(self) -> Dict[str, Any]:
        """获取摘要"""
        return {
            'count': len(self.scores),
            'average': self.get_average(),
            'variance': self.get_variance(),
            'stability': self.get_stability(),
            'trend': self.get_trend(),
            'should_alert': self.should_alert()[0],
            'alert_reason': self.should_alert()[1],
        }
    
    def print_summary(self):
        """打印摘要"""
        summary = self.get_summary()
        
        print(f"\n📊 Confidence Tracker Summary")
        print(f"   Records: {summary['count']}")
        print(f"   Average: {summary['average']:.1%}")
        print(f"   Stability: {summary['stability']:.1%}")
        print(f"   Trend: {summary['trend']}")
        
        if summary['should_alert']:
            print(f"\n   ⚠️ ALERT: {summary['alert_reason']}")
        else:
            print(f"\n   ✅ No alerts")
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'scores': self.scores,
            'timestamps': self.timestamps,
            'summary': self.get_summary(),
        }
