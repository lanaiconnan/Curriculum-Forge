"""结构化报告生成器

基于 gpt-researcher 的报告生成理念，
为 Curriculum-Forge 生成格式化的实验报告。
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
import json


@dataclass
class ReportMetrics:
    """报告指标"""
    total_experiments: int
    keep_rate: float
    avg_reward: float
    best_score: float
    stage_transitions: int
    final_stage: str
    training_time: float
    timeout_count: int = 0


@dataclass
class ReportFinding:
    """关键发现"""
    type: str  # success, warning, improvement
    title: str
    description: str
    recommendation: str


@dataclass
class ReportSection:
    """报告章节"""
    title: str
    content: str
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExperimentReport:
    """实验报告"""
    title: str
    timestamp: str
    metrics: ReportMetrics
    findings: List[ReportFinding]
    sections: List[ReportSection]
    recommendations: List[str]
    next_steps: List[str]
    
    def to_markdown(self) -> str:
        """转换为 Markdown 格式"""
        lines = [
            f"# {self.title}",
            f"\n**生成时间**: {self.timestamp}",
            f"\n---",
            self._generate_summary(),
            self._generate_metrics(),
            self._generate_findings(),
            self._generate_sections(),
            self._generate_recommendations(),
            self._generate_next_steps(),
        ]
        return "\n".join(lines)
    
    def _generate_summary(self) -> str:
        """生成执行摘要"""
        return f"""
## 📋 执行摘要

本报告总结了 Curriculum-Forge 实验的完整执行结果。

### 关键指标

| 指标 | 数值 |
|------|------|
| 总实验数 | {self.metrics.total_experiments} |
| 保留率 | {self.metrics.keep_rate:.1%} |
| 平均奖励 | {self.metrics.avg_reward:.3f} |
| 最佳分数 | {self.metrics.best_score:.3f} |
| 阶段转换 | {self.metrics.stage_transitions} |
| 最终阶段 | {self.metrics.final_stage} |
| 训练时间 | {self.metrics.training_time:.1f}s |
| 超时次数 | {self.metrics.timeout_count} |
"""
    
    def _generate_metrics(self) -> str:
        """生成指标详情"""
        # 生成进度条
        keep_bar = "█" * int(self.metrics.keep_rate * 20) + "░" * (20 - int(self.metrics.keep_rate * 20))
        reward_bar = "█" * int(self.metrics.avg_reward * 10) + "░" * (10 - int(self.metrics.avg_reward * 10))
        
        return f"""
## 📊 指标详情

### 保留率
```
[{keep_bar}] {self.metrics.keep_rate:.1%}
```

### 平均奖励
```
[{reward_bar}] {self.metrics.avg_reward:.3f}
```

### 指标对比

| 指标 | 当前值 | 目标值 | 状态 |
|------|--------|--------|------|
| 保留率 | {self.metrics.keep_rate:.1%} | 50.0% | {'✅ 达标' if self.metrics.keep_rate >= 0.5 else '⚠️ 未达标'} |
| 平均奖励 | {self.metrics.avg_reward:.3f} | 0.70 | {'✅ 达标' if self.metrics.avg_reward >= 0.7 else '⚠️ 未达标'} |
"""
    
    def _generate_findings(self) -> str:
        """生成关键发现"""
        if not self.findings:
            return ""
        
        lines = ["\n## 🔍 关键发现\n"]
        
        for i, finding in enumerate(self.findings, 1):
            icon = {"success": "✅", "warning": "⚠️", "improvement": "💡"}.get(finding.type, "📌")
            lines.append(f"\n### {i}. {icon} {finding.title}")
            lines.append(f"\n{finding.description}")
            if finding.recommendation:
                lines.append(f"\n**建议**: {finding.recommendation}")
        
        return "\n".join(lines)
    
    def _generate_sections(self) -> str:
        """生成章节详情"""
        if not self.sections:
            return ""
        
        lines = ["\n## 📑 详细章节\n"]
        
        for section in self.sections:
            lines.append(f"\n### {section.title}")
            lines.append(f"\n{section.content}")
        
        return "\n".join(lines)
    
    def _generate_recommendations(self) -> str:
        """生成改进建议"""
        if not self.recommendations:
            return ""
        
        lines = ["\n## 💡 改进建议\n"]
        
        for i, rec in enumerate(self.recommendations, 1):
            lines.append(f"\n{i}. {rec}")
        
        return "\n".join(lines)
    
    def _generate_next_steps(self) -> str:
        """生成下一步行动"""
        if not self.next_steps:
            return ""
        
        lines = ["\n## 🚀 下一步行动\n"]
        
        for i, step in enumerate(self.next_steps, 1):
            lines.append(f"\n{i}. {step}")
        
        return "\n".join(lines)
    
    def to_json(self) -> str:
        """转换为 JSON 格式"""
        return json.dumps({
            'title': self.title,
            'timestamp': self.timestamp,
            'metrics': {
                'total_experiments': self.metrics.total_experiments,
                'keep_rate': self.metrics.keep_rate,
                'avg_reward': self.metrics.avg_reward,
                'best_score': self.metrics.best_score,
                'stage_transitions': self.metrics.stage_transitions,
                'final_stage': self.metrics.final_stage,
                'training_time': self.metrics.training_time,
                'timeout_count': self.metrics.timeout_count,
            },
            'findings': [
                {
                    'type': f.type,
                    'title': f.title,
                    'description': f.description,
                    'recommendation': f.recommendation,
                }
                for f in self.findings
            ],
            'recommendations': self.recommendations,
            'next_steps': self.next_steps,
        }, indent=2)
    
    def to_html(self) -> str:
        """转换为 HTML 格式"""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>{self.title}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #2563eb; }}
        h2 {{ color: #1e40af; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
        th, td {{ border: 1px solid #e5e7eb; padding: 12px; text-align: left; }}
        th {{ background: #f3f4f6; }}
        .success {{ color: #059669; }}
        .warning {{ color: #d97706; }}
        pre {{ background: #f3f4f6; padding: 16px; border-radius: 8px; overflow-x: auto; }}
    </style>
</head>
<body>
    <h1>{self.title}</h1>
    <p><strong>生成时间</strong>: {self.timestamp}</p>
    
    <h2>📋 执行摘要</h2>
    <table>
        <tr><th>指标</th><th>数值</th></tr>
        <tr><td>总实验数</td><td>{self.metrics.total_experiments}</td></tr>
        <tr><td>保留率</td><td>{self.metrics.keep_rate:.1%}</td></tr>
        <tr><td>平均奖励</td><td>{self.metrics.avg_reward:.3f}</td></tr>
        <tr><td>最佳分数</td><td>{self.metrics.best_score:.3f}</td></tr>
        <tr><td>阶段转换</td><td>{self.metrics.stage_transitions}</td></tr>
        <tr><td>最终阶段</td><td>{self.metrics.final_stage}</td></tr>
        <tr><td>训练时间</td><td>{self.metrics.training_time:.1f}s</td></tr>
        <tr><td>超时次数</td><td>{self.metrics.timeout_count}</td></tr>
    </table>
    
    <h2>💡 改进建议</h2>
    <ol>
        {"".join(f"<li>{r}</li>" for r in self.recommendations)}
    </ol>
    
    <h2>🚀 下一步行动</h2>
    <ol>
        {"".join(f"<li>{s}</li>" for s in self.next_steps)}
    </ol>
</body>
</html>
"""


class ReportGenerator:
    """报告生成器"""
    
    def __init__(self, output_dir: str = "reports"):
        self.output_dir = output_dir
        self._ensure_output_dir()
    
    def _ensure_output_dir(self):
        """确保输出目录存在"""
        import os
        os.makedirs(self.output_dir, exist_ok=True)
    
    def generate(self, results: List[Dict], stats: Dict[str, Any]) -> ExperimentReport:
        """
        生成实验报告
        
        Args:
            results: 实验结果列表
            stats: 统计信息
        
        Returns:
            ExperimentReport: 实验报告
        """
        # 构建指标
        metrics = self._build_metrics(results, stats)
        
        # 生成发现
        findings = self._generate_findings(metrics, results)
        
        # 生成建议
        recommendations = self._generate_recommendations(metrics)
        
        # 生成下一步
        next_steps = self._generate_next_steps(metrics)
        
        # 构建报告
        report = ExperimentReport(
            title="Curriculum-Forge 实验报告",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            metrics=metrics,
            findings=findings,
            sections=[],
            recommendations=recommendations,
            next_steps=next_steps,
        )
        
        return report
    
    def _build_metrics(self, results: List[Dict], stats: Dict[str, Any]) -> ReportMetrics:
        """构建指标"""
        total = len(results)
        kept = sum(1 for r in results if r.get('status') == 'keep')
        keep_rate = kept / total if total > 0 else 0.0
        
        rewards = [r.get('reward', 0) for r in results]
        avg_reward = sum(rewards) / len(rewards) if rewards else 0.0
        
        scores = [r.get('score', 0) for r in results]
        best_score = max(scores) if scores else 0.0
        
        stage_transitions = stats.get('stage_transitions', 0)
        final_stage = stats.get('final_stage', 'unknown')
        training_time = stats.get('training_time', 0.0)
        timeout_count = sum(1 for r in results if r.get('status') == 'timeout')
        
        return ReportMetrics(
            total_experiments=total,
            keep_rate=keep_rate,
            avg_reward=avg_reward,
            best_score=best_score,
            stage_transitions=stage_transitions,
            final_stage=final_stage,
            training_time=training_time,
            timeout_count=timeout_count,
        )
    
    def _generate_findings(self, metrics: ReportMetrics, results: List[Dict]) -> List[ReportFinding]:
        """生成关键发现"""
        findings = []
        
        # 检查保留率
        if metrics.keep_rate >= 0.6:
            findings.append(ReportFinding(
                type="success",
                title="高保留率",
                description=f"保留率达到 {metrics.keep_rate:.1%}，表现优秀。",
                recommendation="继续保持当前的训练策略。"
            ))
        elif metrics.keep_rate >= 0.4:
            findings.append(ReportFinding(
                type="improvement",
                title="中等保留率",
                description=f"保留率为 {metrics.keep_rate:.1%}，有改进空间。",
                recommendation="考虑调整奖励尺度或增加实验次数。"
            ))
        else:
            findings.append(ReportFinding(
                type="warning",
                title="低保留率",
                description=f"保留率仅为 {metrics.keep_rate:.1%}，需要改进。",
                recommendation="检查奖励计算逻辑，考虑降低难度。"
            ))
        
        # 检查超时
        if metrics.timeout_count > 0:
            findings.append(ReportFinding(
                type="warning",
                title="存在超时实验",
                description=f"有 {metrics.timeout_count} 个实验超时。",
                recommendation="考虑增加时间预算或优化实验流程。"
            ))
        
        # 检查阶段转换
        if metrics.stage_transitions >= 2:
            findings.append(ReportFinding(
                type="success",
                title="多阶段学习",
                description=f"完成了 {metrics.stage_transitions} 次阶段转换。",
                recommendation="课程学习正在发挥作用。"
            ))
        
        return findings
    
    def _generate_recommendations(self, metrics: ReportMetrics) -> List[str]:
        """生成改进建议"""
        recommendations = []
        
        if metrics.keep_rate < 0.5:
            recommendations.append("降低环境难度，从 beginner 阶段重新开始")
            recommendations.append("增加每个阶段的训练次数")
            recommendations.append("调整奖励尺度，使用更激进的探索策略")
        
        if metrics.avg_reward < 0.5:
            recommendations.append("检查工具调用的准确性")
            recommendations.append("优化奖励计算逻辑")
        
        if metrics.stage_transitions < 2:
            recommendations.append("当前阶段停留时间过长，考虑调整阈值")
        
        if metrics.timeout_count > 0:
            recommendations.append("增加时间预算或优化训练效率")
        
        if not recommendations:
            recommendations.append("当前表现良好，可以尝试更高难度的环境")
        
        return recommendations
    
    def _generate_next_steps(self, metrics: ReportMetrics) -> List[str]:
        """生成下一步行动"""
        next_steps = []
        
        # 根据阶段推荐下一步
        if metrics.final_stage == 'beginner':
            next_steps.append("进入 intermediate 阶段，增加任务复杂度")
        elif metrics.final_stage == 'intermediate':
            next_steps.append("进入 advanced 阶段，挑战更高难度")
        else:
            next_steps.append("保持 advanced 阶段，进一步优化")
        
        # 通用建议
        next_steps.append("运行更多迭代以验证稳定性")
        next_steps.append("对比 GRPO vs GAE 的效果")
        
        return next_steps
    
    def save(self, report: ExperimentReport, format: str = 'markdown') -> str:
        """
        保存报告
        
        Args:
            report: 实验报告
            format: 保存格式 (markdown, json, html)
        
        Returns:
            str: 保存的文件路径
        """
        import os
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if format == 'markdown':
            filename = f"{self.output_dir}/report_{timestamp}.md"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(report.to_markdown())
        elif format == 'json':
            filename = f"{self.output_dir}/report_{timestamp}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(report.to_json())
        elif format == 'html':
            filename = f"{self.output_dir}/report_{timestamp}.html"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(report.to_html())
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        return filename
