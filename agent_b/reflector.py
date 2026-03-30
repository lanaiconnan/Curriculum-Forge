"""反思机制

基于 gpt-researcher 的反思理念，
让 Agent 能够反思自己的行为并提出改进建议。
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import json


@dataclass
class ReflectionIssue:
    """反思问题"""
    severity: str  # critical, major, minor
    title: str
    description: str
    affected_trajectories: List[str]
    root_cause: Optional[str] = None


@dataclass
class ReflectionImprovement:
    """反思改进建议"""
    priority: int  # 1-5, 1 是最高
    title: str
    description: str
    expected_impact: str
    implementation_hint: Optional[str] = None


@dataclass
class ReflectionAnalysis:
    """反思分析结果"""
    trajectory_summary: str
    success_patterns: List[str]
    failure_patterns: List[str]
    issues: List[ReflectionIssue]
    improvements: List[ReflectionImprovement]
    confidence: float  # 0-1


@dataclass
class Reflection:
    """完整反思"""
    timestamp: str
    analysis: ReflectionAnalysis
    metrics: Dict[str, float]
    stage: str
    recommendations: List[str]
    
    def to_markdown(self) -> str:
        """转换为 Markdown 格式"""
        lines = [
            f"# 🔮 反思报告",
            f"\n**生成时间**: {self.timestamp}",
            f"\n**学习阶段**: {self.stage}",
            f"\n---",
            self._generate_summary(),
            self._generate_patterns(),
            self._generate_issues(),
            self._generate_improvements(),
            self._generate_recommendations(),
        ]
        return "\n".join(lines)
    
    def _generate_summary(self) -> str:
        """生成摘要"""
        return f"""
## 📋 执行摘要

### 指标

| 指标 | 数值 |
|------|------|
| 置信度 | {self.analysis.confidence:.1%} |
| 发现问题 | {len(self.analysis.issues)} |
| 改进建议 | {len(self.analysis.improvements)} |
"""
    
    def _generate_patterns(self) -> str:
        """生成模式分析"""
        lines = ["\n## 🎯 成功模式\n"]
        
        if self.analysis.success_patterns:
            for pattern in self.analysis.success_patterns:
                lines.append(f"- ✅ {pattern}")
        else:
            lines.append("- 暂无")
        
        lines.append("\n## ⚠️ 失败模式\n")
        
        if self.analysis.failure_patterns:
            for pattern in self.analysis.failure_patterns:
                lines.append(f"- ❌ {pattern}")
        else:
            lines.append("- 暂无")
        
        return "\n".join(lines)
    
    def _generate_issues(self) -> str:
        """生成问题列表"""
        if not self.analysis.issues:
            return "\n## 🔍 发现的问题\n\n暂无重大问题"
        
        lines = ["\n## 🔍 发现的问题\n"]
        
        for i, issue in enumerate(self.analysis.issues, 1):
            icon = {"critical": "🔴", "major": "🟠", "minor": "🟡"}.get(issue.severity, "⚪")
            lines.append(f"\n### {i}. {icon} {issue.title} ({issue.severity})")
            lines.append(f"\n{issue.description}")
            if issue.root_cause:
                lines.append(f"\n**根因**: {issue.root_cause}")
        
        return "\n".join(lines)
    
    def _generate_improvements(self) -> str:
        """生成改进建议"""
        if not self.analysis.improvements:
            return "\n## 💡 改进建议\n\n暂无改进建议"
        
        lines = ["\n## 💡 改进建议\n"]
        
        for imp in sorted(self.analysis.improvements, key=lambda x: x.priority):
            lines.append(f"\n### {imp.priority}. {imp.title}")
            lines.append(f"\n{imp.description}")
            lines.append(f"\n**预期影响**: {imp.expected_impact}")
            if imp.implementation_hint:
                lines.append(f"\n**实施提示**: {imp.implementation_hint}")
        
        return "\n".join(lines)
    
    def _generate_recommendations(self) -> str:
        """生成最终建议"""
        if not self.recommendations:
            return ""
        
        lines = ["\n## 🚀 最终建议\n"]
        
        for i, rec in enumerate(self.recommendations, 1):
            lines.append(f"\n{i}. {rec}")
        
        return "\n".join(lines)
    
    def to_json(self) -> str:
        """转换为 JSON"""
        return json.dumps({
            'timestamp': self.timestamp,
            'stage': self.stage,
            'metrics': self.metrics,
            'confidence': self.analysis.confidence,
            'success_patterns': self.analysis.success_patterns,
            'failure_patterns': self.analysis.failure_patterns,
            'issues': [
                {
                    'severity': i.severity,
                    'title': i.title,
                    'description': i.description,
                    'root_cause': i.root_cause,
                }
                for i in self.analysis.issues
            ],
            'improvements': [
                {
                    'priority': i.priority,
                    'title': i.title,
                    'description': i.description,
                    'expected_impact': i.expected_impact,
                    'implementation_hint': i.implementation_hint,
                }
                for i in self.analysis.improvements
            ],
            'recommendations': self.recommendations,
        }, indent=2)


class Reflector:
    """反思器"""
    
    def __init__(self):
        self.history: List[Reflection] = []
    
    def reflect(
        self,
        trajectories: List[Dict[str, Any]],
        metrics: Dict[str, float],
        stage: str,
    ) -> Reflection:
        """
        执行反思
        
        Args:
            trajectories: 轨迹列表
            metrics: 指标字典
            stage: 当前学习阶段
        
        Returns:
            Reflection: 反思结果
        """
        # 1. 分析轨迹
        analysis = self._analyze_trajectories(trajectories)
        
        # 2. 识别问题
        issues = self._identify_issues(trajectories, analysis)
        
        # 3. 提出改进
        improvements = self._propose_improvements(issues, analysis)
        
        # 4. 生成建议
        recommendations = self._generate_recommendations(improvements, metrics)
        
        # 构建反思结果
        reflection = Reflection(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            analysis=analysis,
            metrics=metrics,
            stage=stage,
            recommendations=recommendations,
        )
        
        # 保存历史
        self.history.append(reflection)
        
        return reflection
    
    def _analyze_trajectories(self, trajectories: List[Dict[str, Any]]) -> ReflectionAnalysis:
        """分析轨迹"""
        # 统计成功和失败
        successes = []
        failures = []
        
        for traj in trajectories:
            status = traj.get('status', 'unknown')
            tools = traj.get('predicted_tools', [])
            
            if status == 'keep':
                successes.append({
                    'tools': tools,
                    'reward': traj.get('reward', 0),
                    'score': traj.get('score', 0),
                })
            else:
                failures.append({
                    'tools': tools,
                    'reward': traj.get('reward', 0),
                    'status': status,
                })
        
        # 识别成功模式
        success_patterns = self._identify_success_patterns(successes)
        
        # 识别失败模式
        failure_patterns = self._identify_failure_patterns(failures)
        
        # 计算置信度
        confidence = len(successes) / len(trajectories) if trajectories else 0.0
        
        return ReflectionAnalysis(
            trajectory_summary=self._summarize_trajectories(trajectories),
            success_patterns=success_patterns,
            failure_patterns=failure_patterns,
            issues=[],  # 稍后填充
            improvements=[],  # 稍后填充
            confidence=confidence,
        )
    
    def _summarize_trajectories(self, trajectories: List[Dict]) -> str:
        """生成轨迹摘要"""
        total = len(trajectories)
        kept = sum(1 for t in trajectories if t.get('status') == 'keep')
        
        return f"共 {total} 个轨迹，{kept} 个成功（{kept/total*100:.1f}%）"
    
    def _identify_success_patterns(self, successes: List[Dict]) -> List[str]:
        """识别成功模式"""
        patterns = []
        
        if not successes:
            return patterns
        
        # 分析工具组合
        tool_counts = {}
        for s in successes:
            for tool in s.get('tools', []):
                tool_counts[tool] = tool_counts.get(tool, 0) + 1
        
        # 找出最常用的工具
        if tool_counts:
            top_tools = sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            patterns.append(f"成功实验中最常用的工具: {', '.join(t[0] for t in top_tools)}")
        
        # 分析奖励分布
        rewards = [s.get('reward', 0) for s in successes]
        if rewards:
            avg_reward = sum(rewards) / len(rewards)
            if avg_reward > 0.7:
                patterns.append(f"高奖励表现: 平均奖励 {avg_reward:.2f}")
        
        return patterns
    
    def _identify_failure_patterns(self, failures: List[Dict]) -> List[str]:
        """识别失败模式"""
        patterns = []
        
        if not failures:
            return patterns
        
        # 分析失败原因
        status_counts = {}
        for f in failures:
            status = f.get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        for status, count in status_counts.items():
            if status == 'timeout':
                patterns.append(f"超时问题: {count} 个实验超时")
            elif status == 'discard':
                patterns.append(f"丢弃问题: {count} 个实验被丢弃")
        
        return patterns
    
    def _identify_issues(
        self,
        trajectories: List[Dict],
        analysis: ReflectionAnalysis
    ) -> List[ReflectionIssue]:
        """识别问题"""
        issues = []
        
        # 检查超时
        timeouts = [t for t in trajectories if t.get('status') == 'timeout']
        if timeouts:
            issues.append(ReflectionIssue(
                severity="major",
                title="存在超时问题",
                description=f"有 {len(timeouts)} 个实验超时，可能影响训练效率。",
                affected_trajectories=[t.get('id', 'unknown') for t in timeouts],
                root_cause="时间预算不足或实验过于复杂",
            ))
        
        # 检查低奖励
        low_reward = [t for t in trajectories if t.get('reward', 0) < 0.3]
        if len(low_reward) > len(trajectories) * 0.3:
            issues.append(ReflectionIssue(
                severity="critical",
                title="低奖励比例过高",
                description=f"有 {len(low_reward)} 个实验奖励低于 0.3，需要检查奖励计算。",
                affected_trajectories=[t.get('id', 'unknown') for t in low_reward[:5]],
                root_cause="工具选择不正确或参数设置不当",
            ))
        
        # 检查阶段停留
        if analysis.confidence < 0.4:
            issues.append(ReflectionIssue(
                severity="minor",
                title="成功率偏低",
                description=f"当前成功率为 {analysis.confidence:.1%}，建议调整训练策略。",
                affected_trajectories=[],
                root_cause="可能需要降低难度或增加训练",
            ))
        
        return issues
    
    def _propose_improvements(
        self,
        issues: List[ReflectionIssue],
        analysis: ReflectionAnalysis
    ) -> List[ReflectionImprovement]:
        """提出改进建议"""
        improvements = []
        
        # 基于问题的改进
        for issue in issues:
            if issue.severity == "critical":
                improvements.append(ReflectionImprovement(
                    priority=1,
                    title="修复关键问题",
                    description=issue.description,
                    expected_impact="提升整体训练效果",
                    implementation_hint="检查奖励计算和工具选择逻辑",
                ))
            elif issue.severity == "major":
                improvements.append(ReflectionImprovement(
                    priority=2,
                    title="解决主要问题",
                    description=issue.description,
                    expected_impact="改善训练效率",
                    implementation_hint="调整时间预算或简化任务",
                ))
        
        # 基于成功模式的改进
        if analysis.success_patterns:
            improvements.append(ReflectionImprovement(
                priority=3,
                title="强化成功模式",
                description="利用已识别的成功模式来指导训练",
                expected_impact="提升成功率",
                implementation_hint="在奖励函数中增加对成功工具的奖励",
            ))
        
        # 基于置信度的改进
        if analysis.confidence < 0.5:
            improvements.append(ReflectionImprovement(
                priority=4,
                title="提高置信度",
                description=f"当前置信度仅为 {analysis.confidence:.1%}",
                expected_impact="更稳定的学习",
                implementation_hint="增加训练迭代或调整学习率",
            ))
        
        return improvements
    
    def _generate_recommendations(
        self,
        improvements: List[ReflectionImprovement],
        metrics: Dict[str, float]
    ) -> List[str]:
        """生成最终建议"""
        recommendations = []
        
        # 优先级最高的改进
        if improvements:
            top = sorted(improvements, key=lambda x: x.priority)[0]
            recommendations.append(f"首要任务：{top.title} - {top.description}")
        
        # 基于指标的特定建议
        keep_rate = metrics.get('keep_rate', 0)
        if keep_rate < 0.4:
            recommendations.append("建议降低环境难度")
        elif keep_rate > 0.7:
            recommendations.append("可以考虑提升环境难度")
        
        return recommendations
    
    def get_history(self) -> List[Reflection]:
        """获取反思历史"""
        return self.history
    
    def get_latest(self) -> Optional[Reflection]:
        """获取最新反思"""
        return self.history[-1] if self.history else None
