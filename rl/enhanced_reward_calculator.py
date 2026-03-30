"""增强的奖励计算器（集成验证机制）

基于 AutoDidact 的自验证理念，
增强 ToolRL 的细粒度奖励计算。
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Tuple, Optional
import sys
import os

# 尝试导入 SelfVerifier
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from rl.self_verifier import SelfVerifier, ConfidenceTracker, VerificationContext
    SELF_VERIFIER_AVAILABLE = True
except ImportError:
    SELF_VERIFIER_AVAILABLE = False
    SelfVerifier = None
    ConfidenceTracker = None
    VerificationContext = None


@dataclass
class VerificationResult:
    """验证结果"""
    exact_match: bool
    partial_match: float  # 0-1
    confidence: float  # 0-1
    issues: List[str]
    suggestions: List[str]


@dataclass
class EnhancedReward:
    """增强奖励"""
    rformat: float  # 格式奖励
    rname: float    # 工具名称奖励
    rparam: float   # 参数名称奖励
    rvalue: float   # 参数值奖励
    verification: VerificationResult
    total: float
    breakdown: Dict[str, float]


class EnhancedRewardCalculator:
    """
    增强的奖励计算器
    
    基于 ToolRL 的细粒度奖励设计：
    - Rformat: 格式正确性
    - Rcorrect: 工具正确性
      - rname: 工具名称匹配
      - rparam: 参数名称匹配
      - rvalue: 参数值匹配
    
    增强特性（来自 AutoDidact）：
    - 自验证机制
    - 置信度计算
    - 问题识别
    - 改进建议
    """
    
    # 权重配置
    WEIGHTS = {
        'rformat': 1.0,
        'rname': 1.0,
        'rparam': 1.0,
        'rvalue': 1.0,
    }
    
    # 验证阈值
    VERIFICATION_THRESHOLD = 0.7
    
    def __init__(self, config: Dict[str, float] = None):
        """
        初始化计算器
        
        Args:
            config: 权重配置
        """
        self.config = config or self.WEIGHTS.copy()
        
        # 初始化验证器
        if SELF_VERIFIER_AVAILABLE:
            self.verifier = SelfVerifier()
            self.confidence_tracker = ConfidenceTracker(window_size=10)
        else:
            self.verifier = None
            self.confidence_tracker = None
    
    def calculate(self, trajectory: Dict[str, Any]) -> EnhancedReward:
        """
        计算增强奖励
        
        Args:
            trajectory: 轨迹数据
        
        Returns:
            EnhancedReward: 增强奖励结果
        """
        # 1. 计算 ToolRL 奖励
        rformat = self._calculate_rformat(trajectory)
        rname, rname_issues = self._calculate_rname(trajectory)
        rparam, rparam_issues = self._calculate_rparam(trajectory)
        rvalue, rvalue_issues = self._calculate_rvalue(trajectory)
        
        # 2. 计算总奖励
        total = (
            rformat * self.config['rformat'] +
            rname * self.config['rname'] +
            rparam * self.config['rparam'] +
            rvalue * self.config['rvalue']
        ) / sum(self.config.values())
        
        # 3. 自验证
        verification = self._verify(trajectory, total)
        
        # 4. 追踪置信度
        if self.confidence_tracker:
            self.confidence_tracker.add(verification.confidence)
        
        # 5. 构建结果
        return EnhancedReward(
            rformat=rformat,
            rname=rname,
            rparam=rparam,
            rvalue=rvalue,
            verification=verification,
            total=total,
            breakdown={
                'rformat': rformat,
                'rname': rname,
                'rparam': rparam,
                'rvalue': rvalue,
            }
        )
    
    def _calculate_rformat(self, trajectory: Dict[str, Any]) -> float:
        """计算格式奖励"""
        predicted = trajectory.get('predicted_tools', [])
        return 1.0 if len(predicted) > 0 else 0.0
    
    def _calculate_rname(self, trajectory: Dict[str, Any]) -> Tuple[float, List[str]]:
        """计算工具名称奖励"""
        predicted = trajectory.get('predicted_tools', [])
        ground_truth = trajectory.get('ground_truth_tools', [])
        
        issues = []
        
        if not predicted:
            return 0.0, ["预测工具列表为空"]
        
        if not ground_truth:
            return 0.5, ["缺少真实工具列表"]
        
        exact = predicted == ground_truth
        if exact:
            return 1.0, []
        
        overlap = set(predicted) & set(ground_truth)
        union = set(predicted) | set(ground_truth)
        
        if len(union) == 0:
            return 0.0, ["预测和真实工具都为空"]
        
        jaccard = len(overlap) / len(union)
        
        missing = set(ground_truth) - set(predicted)
        extra = set(predicted) - set(ground_truth)
        
        if missing:
            issues.append(f"缺少工具: {', '.join(missing)}")
        if extra:
            issues.append(f"多余工具: {', '.join(extra)}")
        
        reward = 2 * jaccard - 1
        reward = max(-1.0, min(1.0, reward))
        
        return reward, issues
    
    def _calculate_rparam(self, trajectory: Dict[str, Any]) -> Tuple[float, List[str]]:
        """计算参数名称奖励"""
        predicted_params = trajectory.get('predicted_params', {})
        ground_truth_params = trajectory.get('ground_truth_params', {})
        
        issues = []
        
        if not predicted_params:
            return 0.0, ["预测参数为空"]
        
        if not ground_truth_params:
            return 0.3, ["缺少真实参数"]
        
        pred_keys = set(predicted_params.keys())
        gt_keys = set(ground_truth_params.keys())
        
        if pred_keys == gt_keys:
            return 1.0, []
        
        overlap = pred_keys & gt_keys
        union = pred_keys | gt_keys
        
        if len(union) == 0:
            return 0.0, []
        
        match_ratio = len(overlap) / len(union)
        
        missing = gt_keys - pred_keys
        extra = pred_keys - gt_keys
        
        if missing:
            issues.append(f"缺少参数: {', '.join(missing)}")
        if extra:
            issues.append(f"多余参数: {', '.join(extra)}")
        
        reward = 2 * match_ratio - 1
        reward = max(-1.0, min(1.0, reward))
        
        return reward, issues
    
    def _calculate_rvalue(self, trajectory: Dict[str, Any]) -> Tuple[float, List[str]]:
        """计算参数值奖励"""
        predicted_params = trajectory.get('predicted_params', {})
        ground_truth_params = trajectory.get('ground_truth_params', {})
        
        issues = []
        
        if not predicted_params or not ground_truth_params:
            return 0.0, ["参数为空"]
        
        total_matches = 0
        total_values = 0
        
        for key in set(predicted_params.keys()) & set(ground_truth_params.keys()):
            total_values += 1
            if predicted_params[key] == ground_truth_params[key]:
                total_matches += 1
            else:
                issues.append(f"参数 {key} 值不匹配")
        
        if total_values == 0:
            return 0.0, ["无共同参数"]
        
        exact_match_ratio = total_matches / total_values
        reward = 2 * exact_match_ratio - 1
        reward = max(-1.0, min(1.0, reward))
        
        return reward, issues
    
    def _verify(self, trajectory: Dict[str, Any], total_reward: float) -> VerificationResult:
        """自验证机制"""
        predicted = trajectory.get('predicted_tools', [])
        ground_truth = trajectory.get('ground_truth_tools', [])
        
        exact_match = predicted == ground_truth
        
        if predicted and ground_truth:
            overlap = set(predicted) & set(ground_truth)
            union = set(predicted) | set(ground_truth)
            partial_match = len(overlap) / len(union) if union else 0.0
        else:
            partial_match = 0.0
        
        confidence = 0.5 * (1.0 if exact_match else partial_match) + 0.5 * (total_reward + 1) / 2
        
        issues = []
        suggestions = []
        
        if not exact_match:
            missing = set(ground_truth) - set(predicted)
            extra = set(predicted) - set(ground_truth)
            
            if missing:
                issues.append(f"缺少工具: {', '.join(missing)}")
                suggestions.append("考虑添加这些工具")
            if extra:
                issues.append(f"多余工具: {', '.join(extra)}")
                suggestions.append("检查是否需要这些工具")
        
        if confidence < self.VERIFICATION_THRESHOLD:
            suggestions.append("置信度较低，建议检查工具选择策略")
        
        return VerificationResult(
            exact_match=exact_match,
            partial_match=partial_match,
            confidence=confidence,
            issues=issues,
            suggestions=suggestions,
        )
    
    def get_verdict(self, reward: EnhancedReward) -> str:
        """获取判定结果"""
        if reward.total >= 0.7 and reward.verification.exact_match:
            return "excellent"
        elif reward.total >= 0.4:
            return "good"
        elif reward.total >= 0.0:
            return "fair"
        else:
            return "poor"
    
    def get_confidence_summary(self) -> Dict[str, Any]:
        """获取置信度摘要"""
        if not self.confidence_tracker:
            return {'available': False}
        
        summary = self.confidence_tracker.get_summary()
        summary['available'] = True
        return summary
    
    def get_feedback(self, reward: EnhancedReward) -> str:
        """获取反馈信息"""
        verdict = self.get_verdict(reward)
        
        feedback = f"判定: {verdict}\n"
        feedback += f"总奖励: {reward.total:.3f}\n"
        feedback += f"置信度: {reward.verification.confidence:.1%}\n"
        
        if reward.verification.exact_match:
            feedback += "✅ 工具选择完全正确\n"
        else:
            feedback += f"⚠️ 工具选择部分正确 (Jaccard: {reward.verification.partial_match:.1%})\n"
        
        if reward.verification.issues:
            feedback += "\n问题:\n"
            for issue in reward.verification.issues:
                feedback += f"  - {issue}\n"
        
        if reward.verification.suggestions:
            feedback += "\n建议:\n"
            for suggestion in reward.verification.suggestions:
                feedback += f"  - {suggestion}\n"
        
        return feedback
    
    def __repr__(self) -> str:
        return f"EnhancedRewardCalculator(config={self.config})"


# 兼容原来的 RewardCalculator
class RewardCalculator(EnhancedRewardCalculator):
    """兼容原来的 RewardCalculator"""
    
    def calculate(self, trajectory: Dict[str, Any]) -> float:
        """计算奖励，返回浮点数（兼容旧接口）"""
        enhanced = super().calculate(trajectory)
        return enhanced.total
