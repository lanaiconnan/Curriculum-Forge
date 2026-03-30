"""Agent B - 学习者（集成 Scratchpad 日志）"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import time as time_module
import random
import os
import sys

# 添加项目路径以导入 Scratchpad
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from shared.scratchpad import Scratchpad
    SCRATCHPAD_AVAILABLE = True
except ImportError:
    SCRATCHPAD_AVAILABLE = False
    Scratchpad = None


@dataclass
class ExperimentIdea:
    id: str
    description: str
    implementation: str
    expected: str
    priority: str = "medium"


@dataclass
class ExperimentResult:
    idea: ExperimentIdea
    commit: str
    status: str  # keep/discard/timeout/crash
    metrics: Dict[str, float]
    output: str
    reward: float = 0.0
    
    def to_tsv(self) -> str:
        return f"{self.commit}\t{self.metrics.get('score', 0)}\t{self.metrics.get('memory', 0)}\t{self.status}\t{self.idea.description}"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.commit,
            'status': self.status,
            'score': self.metrics.get('score', 0),
            'reward': self.reward,
            'predicted_tools': self.idea.implementation.split('→') if '→' in self.idea.implementation else [],
            'ground_truth_tools': self.idea.expected.split('→'),
        }


class AgentB:
    """
    学习者 Agent - 带超时控制和 Scratchpad 日志
    
    Agent B 负责：
    1. 根据环境运行实验
    2. 收集实验结果
    3. 计算奖励
    4. 记录执行日志
    """
    
    def __init__(self, workspace: str = ".", tools=None, max_experiment_time: int = 300, scratchpad: Scratchpad = None):
        """
        初始化 Agent B
        
        Args:
            workspace: 工作区路径
            tools: 工具注册表
            max_experiment_time: 单次实验最大时间（秒），默认 5 分钟
            scratchpad: Scratchpad 日志实例（可选）
        """
        self.workspace = workspace
        self.tools = tools
        self.baseline: Optional[float] = None
        self.ideas: List[ExperimentIdea] = []
        self.max_experiment_time = max_experiment_time
        self.total_time: float = 0
        self.timeout_count: int = 0
        
        # 初始化 Scratchpad 日志
        if scratchpad is not None:
            self.scratchpad = scratchpad
        elif SCRATCHPAD_AVAILABLE:
            self.scratchpad = Scratchpad(base_dir=os.path.join(workspace, '.scratchpad'))
        else:
            self.scratchpad = None
    
    def _log_thinking(self, thought: str, confidence: float = None):
        """记录思考日志"""
        if self.scratchpad:
            self.scratchpad.log_thinking(
                thought=thought,
                confidence=confidence,
                context='Agent B - 学习者'
            )
    
    def _log_tool_call(self, tool: str, args: Dict):
        """记录工具调用日志"""
        if self.scratchpad:
            self.scratchpad.log_tool_call(tool, args)
    
    def set_baseline(self, score: float):
        """设置基准分数"""
        self._log_thinking(f'设置基准分数: {score}', confidence=1.0)
        self.baseline = score
    
    def propose_ideas(self, env) -> List[ExperimentIdea]:
        """根据环境生成实验想法"""
        # 记录思考
        self._log_thinking(f'根据环境生成实验想法：{env.name}', confidence=0.9)
        
        ideas = []
        for task in env.tasks:
            idea = ExperimentIdea(
                id=f"idea-{len(self.ideas) + 1}",
                description=task["description"],
                implementation=f"# TODO: {task['description']}",
                expected=task.get("target", "improvement"),
                priority="high" if task.get("type") == "optimize" else "medium",
            )
            ideas.append(idea)
            self.ideas.append(idea)
        
        # 记录工具调用
        self._log_tool_call('propose_ideas', {
            'env_id': env.id,
            'ideas_count': len(ideas),
            'task_types': [t.get('type') for t in env.tasks],
        })
        
        return ideas
    
    def run_experiment(self, idea: ExperimentIdea, env) -> ExperimentResult:
        """运行单个实验，带超时控制"""
        start_time = time_module.time()
        
        # 记录思考
        self._log_thinking(
            f'开始实验: {idea.description}',
            confidence=0.7
        )
        
        # 模拟实验耗时（0.5-2秒）
        experiment_duration = random.uniform(0.5, 2.0)
        
        # 检查是否会导致超时
        if self.total_time + experiment_duration > self.max_experiment_time:
            elapsed = time_module.time() - start_time
            self.total_time += elapsed
            self.timeout_count += 1
            
            # 记录超时
            self._log_tool_call('experiment_timeout', {
                'idea_id': idea.id,
                'elapsed': elapsed,
                'total_time': self.total_time,
            })
            
            self._log_thinking(
                f'实验超时: {idea.id}, 已用 {self.total_time:.1f}s / {self.max_experiment_time}s',
                confidence=1.0
            )
            
            return ExperimentResult(
                idea=idea,
                commit=f"timeout-{idea.id}",
                status="timeout",
                metrics={"score": 0, "memory": 0},
                output=f"⏱ Would exceed time budget ({self.total_time:.1f}s / {self.max_experiment_time}s)",
                reward=0.0,
            )
        
        # 记录实验开始
        self._log_tool_call('experiment_start', {
            'idea_id': idea.id,
            'expected_duration': experiment_duration,
        })
        
        # 模拟实验
        time_module.sleep(experiment_duration)
        
        status = random.choice(["keep", "keep", "discard"])  # 60% keep
        metrics = {"score": 100 + random.random() * 10, "memory": 45000}
        reward = random.uniform(0.4, 0.9) if status == "keep" else random.uniform(0.1, 0.4)
        
        elapsed = time_module.time() - start_time
        self.total_time += elapsed
        
        if status == "keep" and self.baseline:
            if metrics["score"] <= self.baseline:
                status = "discard"
        
        # 记录实验结果
        self._log_tool_call('experiment_result', {
            'idea_id': idea.id,
            'status': status,
            'score': metrics["score"],
            'reward': reward,
            'elapsed': elapsed,
        })
        
        self._log_thinking(
            f'实验完成: {idea.id} -> {status}, score={metrics["score"]:.1f}, reward={reward:.3f}',
            confidence=0.9
        )
        
        return ExperimentResult(
            idea=idea,
            commit=f"sim-{idea.id}",
            status=status,
            metrics=metrics,
            output=f"{status}: score={metrics['score']:.1f}, time={elapsed:.1f}s",
            reward=reward,
        )
    
    def autoresearch_loop(self, env, max_iterations: int = 10) -> List[ExperimentResult]:
        """
        运行 autoresearch 循环，带超时控制
        
        Args:
            env: 训练环境
            max_iterations: 最大迭代次数
        
        Returns:
            List[ExperimentResult]: 实验结果列表
        """
        results = []
        if self.baseline is None:
            self.baseline = env.reward_config.get("baseline", 100.0)
        
        ideas = self.propose_ideas(env)
        
        print(f"\n[Agent B] Starting experiments (time budget: {self.max_experiment_time}s)")
        
        # 记录开始
        self._log_thinking(
            f'开始实验循环: {env.name}, 最大迭代 {max_iterations}',
            confidence=0.9
        )
        
        for i, idea in enumerate(ideas[:max_iterations]):
            # 检查总时间是否超限
            remaining_time = self.max_experiment_time - self.total_time
            if remaining_time <= 0:
                print(f"\n⏱ Time budget exhausted! Stopping experiments.")
                self._log_thinking('时间预算耗尽，停止实验', confidence=1.0)
                break
            
            print(f"[{i+1}/{len(ideas)}] {idea.description} (remaining: {remaining_time:.1f}s)")
            
            result = self.run_experiment(idea, env)
            results.append(result)
            
            if result.status == "keep" and self.baseline:
                self.baseline = max(self.baseline, result.metrics.get("score", self.baseline))
            
            # 根据状态选择图标
            if result.status == "keep":
                icon = "✅"
            elif result.status == "discard":
                icon = "❌"
            elif result.status == "timeout":
                icon = "⏱"
            else:
                icon = "💥"
            
            print(f"    -> {icon} {result.output}")
        
        # 记录循环完成
        if self.scratchpad:
            self.scratchpad.log_result(
                status='success' if results else 'no_results',
                message=f'完成 {len(results)} 个实验',
                metrics={
                    'keep_rate': sum(1 for r in results if r.status == 'keep') / len(results) if results else 0,
                    'avg_reward': sum(r.reward for r in results) / len(results) if results else 0,
                }
            )
        
        # 打印时间统计
        if results:
            timeout_results = [r for r in results if r.status == "timeout"]
            if timeout_results:
                print(f"\n⏱ Timeouts: {len(timeout_results)}/{len(results)}")
            print(f"⏱ Total experiment time: {self.total_time:.1f}s / {self.max_experiment_time}s")
            print(f"⏱ Time utilization: {self.total_time / self.max_experiment_time * 100:.1f}%")
        
        return results
    
    def get_time_stats(self) -> Dict[str, Any]:
        """获取时间统计"""
        return {
            "total_time": self.total_time,
            "max_time": self.max_experiment_time,
            "remaining": self.max_experiment_time - self.total_time,
            "timeout_count": self.timeout_count,
            "utilization": self.total_time / self.max_experiment_time if self.max_experiment_time > 0 else 0,
        }
    
    def reset_timer(self):
        """重置计时器"""
        self.total_time = 0
        self.timeout_count = 0
