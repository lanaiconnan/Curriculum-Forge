"""Analyst Agent - 智能分析

来自 AgentLaboratory 的灵感：
- 趋势分析
- 模式识别
- 洞察生成
- 异常检测
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from enum import Enum
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from shared.scratchpad import Scratchpad
    SCRATCHPAD_AVAILABLE = True
except ImportError:
    SCRATCHPAD_AVAILABLE = False
    Scratchpad = None


class TrendDirection(Enum):
    """趋势方向"""
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"
    UNKNOWN = "unknown"


class AnomalyType(Enum):
    """异常类型"""
    PERFORMANCE_DROP = "performance_drop"      # 性能骤降
    OVERFITTING = "overfitting"               # 过拟合
    PLATEAU = "plateau"                        #  plateau
    VOLATILITY = "volatility"                  # 波动过大


@dataclass
class TrendAnalysis:
    """趋势分析结果"""
    direction: TrendDirection
    slope: float          # 斜率（正=改善，负=下降）
    volatility: float     # 波动性
    confidence: float     # 置信度
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'direction': self.direction.value,
            'slope': self.slope,
            'volatility': self.volatility,
            'confidence': self.confidence,
        }


@dataclass
class Pattern:
    """识别出的模式"""
    name: str
    description: str
    frequency: float      # 出现频率
    impact: str           # high/medium/low
    evidence: List[str]    # 证据列表
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'description': self.description,
            'frequency': f"{self.frequency:.1%}",
            'impact': self.impact,
            'evidence': self.evidence,
        }


@dataclass
class Anomaly:
    """异常检测结果"""
    type: AnomalyType
    severity: str         # critical/major/minor
    description: str
    evidence: List[str]
    timestamp: str
    suggested_action: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': self.type.value,
            'severity': self.severity,
            'description': self.description,
            'evidence': self.evidence,
            'timestamp': self.timestamp,
            'suggested_action': self.suggested_action,
        }


@dataclass
class Insight:
    """洞察"""
    category: str          # strategy/difficulty/reward/pattern
    title: str
    description: str
    confidence: float
    actionable: bool       # 是否可执行
    recommendations: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'category': self.category,
            'title': self.title,
            'description': self.description,
            'confidence': f"{self.confidence:.1%}",
            'actionable': self.actionable,
            'recommendations': self.recommendations,
        }


@dataclass
class AnalysisReport:
    """完整分析报告"""
    timestamp: str
    experiment_count: int
    trend_analysis: Dict[str, TrendAnalysis]
    patterns: List[Pattern]
    anomalies: List[Anomaly]
    insights: List[Insight]
    summary: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'experiment_count': self.experiment_count,
            'trend_analysis': {
                k: v.to_dict() for k, v in self.trend_analysis.items()
            },
            'patterns': [p.to_dict() for p in self.patterns],
            'anomalies': [a.to_dict() for a in self.anomalies],
            'insights': [i.to_dict() for i in self.insights],
            'summary': self.summary,
        }


class AnalystAgent:
    """
    Analyst Agent - 智能分析器
    
    核心功能：
    1. 趋势分析 - 分析奖励、保留率等指标的趋势
    2. 模式识别 - 识别成功和失败模式
    3. 异常检测 - 检测性能骤降、过拟合等问题
    4. 洞察生成 - 生成可执行的改进建议
    """
    
    def __init__(self, scratchpad: Scratchpad = None):
        self.scratchpad = scratchpad
        self.history: List[AnalysisReport] = []
        
        # 配置参数
        self.volatility_threshold = 0.3      # 波动阈值
        self.slope_threshold = 0.05          # 趋势斜率阈值
        self.anomaly_window = 5               # 异常检测窗口大小
        self.confidence_threshold = 0.6        # 置信度阈值
    
    def _log_thinking(self, thought: str, confidence: float = None):
        """记录思考日志"""
        if self.scratchpad:
            self.scratchpad.log_thinking(
                thought=thought,
                confidence=confidence,
                context='Analyst - 分析'
            )
    
    def analyze(self, results: List[Dict[str, Any]]) -> AnalysisReport:
        """
        完整分析
        
        Args:
            results: 实验结果列表
        
        Returns:
            AnalysisReport: 完整分析报告
        """
        self._log_thinking(f'开始分析 {len(results)} 个实验结果', confidence=0.9)
        
        # 1. 趋势分析
        trend_analysis = self._analyze_trends(results)
        
        # 2. 模式识别
        patterns = self._identify_patterns(results)
        
        # 3. 异常检测
        anomalies = self._detect_anomalies(results)
        
        # 4. 洞察生成
        insights = self._generate_insights(results, trend_analysis, patterns, anomalies)
        
        # 5. 生成摘要
        summary = self._generate_summary(trend_analysis, patterns, anomalies, insights)
        
        # 构建报告
        report = AnalysisReport(
            timestamp=datetime.now().isoformat(),
            experiment_count=len(results),
            trend_analysis=trend_analysis,
            patterns=patterns,
            anomalies=anomalies,
            insights=insights,
            summary=summary,
        )
        
        self.history.append(report)
        self._log_thinking(f'分析完成：{summary}', confidence=0.95)
        
        return report
    
    def _analyze_trends(self, results: List[Dict[str, Any]]) -> Dict[str, TrendAnalysis]:
        """分析趋势"""
        trends = {}
        
        if len(results) < 3:
            return {
                'reward': TrendAnalysis(TrendDirection.UNKNOWN, 0, 0, 0),
                'keep_rate': TrendAnalysis(TrendDirection.UNKNOWN, 0, 0, 0),
            }
        
        # 分析奖励趋势
        rewards = [r.get('reward', 0) for r in results]
        reward_trend = self._calculate_trend(rewards)
        trends['reward'] = reward_trend
        
        # 分析保留率趋势（滑动窗口）
        keep_rates = self._calculate_sliding_keep_rate(results)
        keep_rate_trend = self._calculate_trend(keep_rates)
        trends['keep_rate'] = keep_rate_trend
        
        self._log_thinking(
            f'趋势分析：奖励={reward_trend.direction.value}({reward_trend.slope:.3f})，'
            f'保留率={keep_rate_trend.direction.value}({keep_rate_trend.slope:.3f})',
            confidence=0.85
        )
        
        return trends
    
    def _calculate_trend(self, values: List[float]) -> TrendAnalysis:
        """计算趋势（简单线性回归斜率）"""
        n = len(values)
        if n < 2:
            return TrendAnalysis(TrendDirection.UNKNOWN, 0, 0, 0)
        
        # 计算均值
        mean = sum(values) / n
        
        # 计算标准差（波动性）
        variance = sum((v - mean) ** 2 for v in values) / n
        volatility = variance ** 0.5
        
        # 计算斜率（简化版：首尾差值）
        slope = (values[-1] - values[0]) / (n - 1) if n > 1 else 0
        
        # 确定方向
        if slope > self.slope_threshold:
            direction = TrendDirection.IMPROVING
        elif slope < -self.slope_threshold:
            direction = TrendDirection.DECLINING
        else:
            direction = TrendDirection.STABLE
        
        # 计算置信度（基于数据点数量）
        confidence = min(1.0, n / 10)
        
        return TrendAnalysis(
            direction=direction,
            slope=slope,
            volatility=volatility,
            confidence=confidence,
        )
    
    def _calculate_sliding_keep_rate(self, results: List[Dict[str, Any]], window: int = 5) -> List[float]:
        """计算滑动窗口保留率"""
        keep_rates = []
        for i in range(window - 1, len(results)):
            window_results = results[i - window + 1:i + 1]
            keeps = sum(1 for r in window_results if r.get('status') == 'keep')
            keep_rates.append(keeps / window)
        return keep_rates
    
    def _identify_patterns(self, results: List[Dict[str, Any]]) -> List[Pattern]:
        """识别模式"""
        patterns = []
        
        if len(results) < 5:
            return patterns
        
        # 识别成功模式
        success_patterns = self._find_success_patterns(results)
        patterns.extend(success_patterns)
        
        # 识别失败模式
        failure_patterns = self._find_failure_patterns(results)
        patterns.extend(failure_patterns)
        
        # 识别工具使用模式
        tool_patterns = self._find_tool_patterns(results)
        patterns.extend(tool_patterns)
        
        self._log_thinking(
            f'模式识别：{len(patterns)} 个模式（成功={len(success_patterns)}，'
            f'失败={len(failure_patterns)}，工具={len(tool_patterns)}）',
            confidence=0.8
        )
        
        return patterns
    
    def _find_success_patterns(self, results: List[Dict[str, Any]]) -> List[Pattern]:
        """识别成功模式"""
        patterns = []
        
        # 获取成功的实验
        successes = [r for r in results if r.get('status') == 'keep']
        if not successes:
            return patterns
        
        # 分析成功的工具组合
        tool_combinations = {}
        for r in successes:
            tools = tuple(sorted(r.get('tools_used', [])))
            tool_combinations[tools] = tool_combinations.get(tools, 0) + 1
        
        if tool_combinations:
            most_common = max(tool_combinations.items(), key=lambda x: x[1])
            freq = most_common[1] / len(successes)
            
            patterns.append(Pattern(
                name="successful_tool_combination",
                description=f"工具组合 {most_common[0]} 在 {freq:.1%} 的成功实验中使用",
                frequency=freq,
                impact="high" if freq > 0.5 else "medium",
                evidence=[f"出现次数: {most_common[1]}", f"频率: {freq:.1%}"]
            ))
        
        return patterns
    
    def _find_failure_patterns(self, results: List[Dict[str, Any]]) -> List[Pattern]:
        """识别失败模式"""
        patterns = []
        
        # 获取失败的实验
        failures = [r for r in results if r.get('status') == 'discard']
        if not failures:
            return patterns
        
        # 分析失败原因
        failure_reasons = {}
        for r in failures:
            reason = r.get('failure_reason', 'unknown')
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
        
        for reason, count in failure_reasons.items():
            freq = count / len(failures)
            
            patterns.append(Pattern(
                name="failure_pattern",
                description=f"失败原因 '{reason}' 占 {freq:.1%}",
                frequency=freq,
                impact="high" if freq > 0.3 else "medium",
                evidence=[f"出现次数: {count}", f"占比: {freq:.1%}"]
            ))
        
        return patterns
    
    def _find_tool_patterns(self, results: List[Dict[str, Any]]) -> List[Pattern]:
        """识别工具使用模式"""
        patterns = []
        
        # 分析工具使用频率
        tool_usage = {}
        for r in results:
            for tool in r.get('tools_used', []):
                tool_usage[tool] = tool_usage.get(tool, {'total': 0, 'success': 0})
                tool_usage[tool]['total'] += 1
                if r.get('status') == 'keep':
                    tool_usage[tool]['success'] += 1
        
        # 识别高效工具
        for tool, stats in tool_usage.items():
            if stats['total'] >= 3:
                success_rate = stats['success'] / stats['total']
                
                if success_rate > 0.7:
                    patterns.append(Pattern(
                        name="effective_tool",
                        description=f"工具 '{tool}' 成功率达到 {success_rate:.1%}",
                        frequency=stats['total'] / len(results),
                        impact="medium",
                        evidence=[f"使用次数: {stats['total']}", f"成功率: {success_rate:.1%}"]
                    ))
        
        return patterns
    
    def _detect_anomalies(self, results: List[Dict[str, Any]]) -> List[Anomaly]:
        """检测异常"""
        anomalies = []
        
        if len(results) < self.anomaly_window:
            return anomalies
        
        # 检测性能骤降
        drop_anomalies = self._detect_performance_drop(results)
        anomalies.extend(drop_anomalies)
        
        # 检测 plateau
        plateau_anomalies = self._detect_plateau(results)
        anomalies.extend(plateau_anomalies)
        
        # 检测波动过大
        volatility_anomalies = self._detect_volatility(results)
        anomalies.extend(volatility_anomalies)
        
        self._log_thinking(
            f'异常检测：发现 {len(anomalies)} 个异常',
            confidence=0.8
        )
        
        return anomalies
    
    def _detect_performance_drop(self, results: List[Dict[str, Any]]) -> List[Anomaly]:
        """检测性能骤降"""
        anomalies = []
        
        rewards = [r.get('reward', 0) for r in results]
        
        # 检查最近的结果是否显著低于平均值
        recent = rewards[-self.anomaly_window:]
        avg = sum(rewards) / len(rewards)
        recent_avg = sum(recent) / len(recent)
        
        if recent_avg < avg * 0.7:  # 下降超过 30%
            anomalies.append(Anomaly(
                type=AnomalyType.PERFORMANCE_DROP,
                severity="major",
                description=f"性能骤降：最近平均 {recent_avg:.3f} 低于总体平均 {avg:.3f}",
                evidence=[
                    f"总体平均: {avg:.3f}",
                    f"最近平均: {recent_avg:.3f}",
                    f"下降幅度: {(1 - recent_avg/avg)*100:.1f}%"
                ],
                timestamp=datetime.now().isoformat(),
                suggested_action="检查最近生成的实验是否有问题，考虑回滚到之前的环境配置"
            ))
        
        return anomalies
    
    def _detect_plateau(self, results: List[Dict[str, Any]]) -> List[Anomaly]:
        """检测 plateau（停滞）"""
        anomalies = []
        
        if len(results) < 10:
            return anomalies
        
        # 检查最近的结果是否几乎没有变化
        recent = results[-self.anomaly_window:]
        rewards = [r.get('reward', 0) for r in recent]
        
        variance = sum((r - sum(rewards)/len(rewards))**2 for r in rewards) / len(rewards)
        
        if variance < 0.01:  # 方差过小
            anomalies.append(Anomaly(
                type=AnomalyType.PLATEAU,
                severity="minor",
                description="训练可能进入 plateau，奖励几乎没有变化",
                evidence=[f"最近 {self.anomaly_window} 个结果方差: {variance:.4f}"],
                timestamp=datetime.now().isoformat(),
                suggested_action="尝试增加环境难度或调整学习率"
            ))
        
        return anomalies
    
    def _detect_volatility(self, results: List[Dict[str, Any]]) -> List[Anomaly]:
        """检测波动过大"""
        anomalies = []
        
        rewards = [r.get('reward', 0) for r in results]
        
        if len(rewards) < 5:
            return anomalies
        
        # 计算变异系数
        mean = sum(rewards) / len(rewards)
        variance = sum((r - mean) ** 2 for r in rewards) / len(rewards)
        std_dev = variance ** 0.5
        cv = std_dev / mean if mean > 0 else 0
        
        if cv > self.volatility_threshold:
            anomalies.append(Anomaly(
                type=AnomalyType.VOLATILITY,
                severity="minor",
                description=f"训练波动较大，变异系数 {cv:.2f}",
                evidence=[f"标准差: {std_dev:.3f}", f"均值: {mean:.3f}", f"变异系数: {cv:.2f}"],
                timestamp=datetime.now().isoformat(),
                suggested_action="考虑降低学习率或增加训练稳定性"
            ))
        
        return anomalies
    
    def _generate_insights(
        self,
        results: List[Dict[str, Any]],
        trends: Dict[str, TrendAnalysis],
        patterns: List[Pattern],
        anomalies: List[Anomaly]
    ) -> List[Insight]:
        """生成洞察"""
        insights = []
        
        # 基于趋势生成洞察
        if 'reward' in trends:
            trend = trends['reward']
            if trend.direction == TrendDirection.IMPROVING:
                insights.append(Insight(
                    category="strategy",
                    title="奖励持续改善",
                    description=f"奖励呈上升趋势（斜率: {trend.slope:.4f}），当前策略有效",
                    confidence=trend.confidence,
                    actionable=True,
                    recommendations=["继续保持当前策略", "可以适当增加探索"]
                ))
            elif trend.direction == TrendDirection.DECLINING:
                insights.append(Insight(
                    category="strategy",
                    title="奖励下降警告",
                    description=f"奖励呈下降趋势（斜率: {trend.slope:.4f}），需要调整策略",
                    confidence=trend.confidence,
                    actionable=True,
                    recommendations=["检查最近的环境配置", "考虑回滚到之前的设置"]
                ))
        
        # 基于模式生成洞察
        for pattern in patterns:
            if pattern.impact == "high":
                insights.append(Insight(
                    category="pattern",
                    title=f"发现重要模式: {pattern.name}",
                    description=pattern.description,
                    confidence=pattern.frequency,
                    actionable=True,
                    recommendations=[f"重点关注: {pattern.description}"]
                ))
        
        # 基于异常生成洞察
        if anomalies:
            major_anomalies = [a for a in anomalies if a.severity in ["major", "critical"]]
            if major_anomalies:
                insights.append(Insight(
                    category="difficulty",
                    title="检测到需要关注的异常",
                    description=f"发现 {len(major_anomalies)} 个主要异常",
                    confidence=0.9,
                    actionable=True,
                    recommendations=[a.suggested_action for a in major_anomalies]
                ))
        
        # 默认洞察
        if not insights:
            insights.append(Insight(
                category="strategy",
                title="训练正常进行",
                description="未检测到明显问题，继续当前策略",
                confidence=0.8,
                actionable=False,
                recommendations=["保持当前训练配置"]
            ))
        
        self._log_thinking(f'生成 {len(insights)} 条洞察', confidence=0.85)
        
        return insights
    
    def _generate_summary(
        self,
        trends: Dict[str, TrendAnalysis],
        patterns: List[Pattern],
        anomalies: List[Anomaly],
        insights: List[Insight]
    ) -> str:
        """生成分析摘要"""
        parts = []
        
        # 趋势摘要
        if 'reward' in trends:
            direction = trends['reward'].direction.value
            parts.append(f"奖励趋势: {direction}")
        
        # 模式摘要
        if patterns:
            parts.append(f"发现 {len(patterns)} 个模式")
        
        # 异常摘要
        if anomalies:
            critical = len([a for a in anomalies if a.severity == "critical"])
            major = len([a for a in anomalies if a.severity == "major"])
            parts.append(f"异常: {critical} 严重, {major} 主要")
        else:
            parts.append("无异常")
        
        # 洞察摘要
        if insights:
            parts.append(f"{len(insights)} 条洞察")
        
        return " | ".join(parts)
    
    def print_report(self, report: AnalysisReport):
        """打印分析报告"""
        print("\n" + "=" * 60)
        print("📊 Analyst Report")
        print("=" * 60)
        
        print(f"\n⏰ {report.timestamp}")
        print(f"📈 实验数量: {report.experiment_count}")
        
        # 趋势分析
        print(f"\n【趋势分析】")
        for name, trend in report.trend_analysis.items():
            emoji = {
                'IMPROVING': '📈',
                'STABLE': '➡️',
                'DECLINING': '📉',
                'UNKNOWN': '❓'
            }.get(trend.direction.value, '❓')
            print(f"   {emoji} {name}: {trend.direction.value}")
            print(f"      斜率: {trend.slope:.4f}, 波动: {trend.volatility:.3f}")
        
        # 模式识别
        if report.patterns:
            print(f"\n【模式识别】({len(report.patterns)} 个)")
            for p in report.patterns[:3]:  # 只显示前 3 个
                print(f"   • {p.name}: {p.description}")
        
        # 异常检测
        if report.anomalies:
            print(f"\n【异常检测】({len(report.anomalies)} 个)")
            for a in report.anomalies:
                severity_icon = {'critical': '🔴', 'major': '🟠', 'minor': '🟡'}.get(a.severity, '⚪')
                print(f"   {severity_icon} {a.type.value}: {a.description}")
        
        # 洞察
        if report.insights:
            print(f"\n【洞察】({len(report.insights)} 条)")
            for i in report.insights[:3]:  # 只显示前 3 个
                print(f"   💡 {i.title}")
        
        # 摘要
        print(f"\n📋 摘要: {report.summary}")
        print("=" * 60)
