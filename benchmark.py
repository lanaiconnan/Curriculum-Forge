"""性能对比和超参数优化框架"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, asdict


@dataclass
class BenchmarkConfig:
    """基准测试配置"""
    name: str
    mode: str  # "cold_start", "sft_pretrain"
    algorithm: str  # "grpo", "gae"
    reward_scale: float = 1.0
    learning_stage_thresholds: Tuple[float, float] = (0.3, 0.6)
    iterations: int = 10
    description: str = ""


@dataclass
class BenchmarkResult:
    """基准测试结果"""
    config: BenchmarkConfig
    timestamp: str
    total_experiments: int
    keep_rate: float
    avg_reward: float
    total_reward: float
    stage_transitions: int
    final_stage: str
    training_time: float
    notes: str = ""


class BenchmarkRunner:
    """性能对比框架"""
    
    def __init__(self, workspace: str = "benchmarks"):
        self.workspace = workspace
        os.makedirs(workspace, exist_ok=True)
        self.results: List[BenchmarkResult] = []
    
    def run_benchmark(self, config: BenchmarkConfig) -> BenchmarkResult:
        """运行单个基准测试"""
        import time
        from agent_a.generator import AgentA
        from agent_b.learner import AgentB
        from rl.trainer import RLTrainer, RLConfig
        from shared.results import ResultsLog
        from tools import create_registry
        
        start_time = time.time()
        
        # 初始化
        ws = os.path.join(self.workspace, config.name)
        os.makedirs(ws, exist_ok=True)
        os.chdir(ws)
        
        if not os.path.exists(".git"):
            os.system("git init > /dev/null 2>&1")
        
        agent_a = AgentA(ws)
        tools = create_registry(ws, ["git", "moon"])
        agent_b = AgentB(ws, tools)
        trainer = RLTrainer(RLConfig())
        results_log = ResultsLog("results.tsv")
        
        # 修改学习阶段阈值
        agent_a.learning_stage_thresholds = config.learning_stage_thresholds
        
        # 修改奖励尺度
        agent_a.reward_scales['beginner'] *= config.reward_scale
        agent_a.reward_scales['intermediate'] *= config.reward_scale
        agent_a.reward_scales['advanced'] *= config.reward_scale
        
        total_experiments = 0
        total_kept = 0
        stage_transitions = set()
        final_stage = "unknown"
        
        # 运行训练循环
        for epoch in range(config.iterations):
            progress = agent_a.analyze_progress("results.tsv")
            stage = agent_a.get_learning_stage(progress)
            stage_transitions.add(stage)
            final_stage = stage
            
            env = agent_a.generate_environment(progress)
            results = agent_b.autoresearch_loop(env, max_iterations=5)
            
            # 计算奖励
            train_results = [
                {
                    'id': r.get('id', f'exp{i}'),
                    'description': r.get('description', ''),
                    'predicted_tools': r.get('tools_used', []),
                    'ground_truth_tools': r.get('tools_expected', []),
                    'predicted_params': r.get('params_used', {}),
                    'ground_truth_params': r.get('params_expected', {}),
                }
                for i, r in enumerate(results)
            ]
            
            use_grpo = config.algorithm == "grpo"
            stats = trainer.train_step(train_results, use_grpo=use_grpo)
            
            total_experiments += len(results)
            total_kept += sum(1 for r in results if r.get('status') == 'keep')
        
        training_time = time.time() - start_time
        keep_rate = total_kept / total_experiments if total_experiments > 0 else 0.0
        
        result = BenchmarkResult(
            config=config,
            timestamp=datetime.now().isoformat(),
            total_experiments=total_experiments,
            keep_rate=keep_rate,
            avg_reward=stats.get('avg_reward', 0.0),
            total_reward=stats.get('total_reward', 0.0),
            stage_transitions=len(stage_transitions),
            final_stage=final_stage,
            training_time=training_time,
            notes=f"Algorithm: {config.algorithm}, Reward scale: {config.reward_scale}",
        )
        
        self.results.append(result)
        return result
    
    def compare_results(self) -> Dict[str, Any]:
        """对比所有结果"""
        if not self.results:
            return {}
        
        comparison = {
            'timestamp': datetime.now().isoformat(),
            'total_benchmarks': len(self.results),
            'benchmarks': [asdict(r) for r in self.results],
            'summary': self._generate_summary(),
        }
        
        return comparison
    
    def _generate_summary(self) -> Dict[str, Any]:
        """生成对比总结"""
        if not self.results:
            return {}
        
        # 按算法分组
        by_algorithm = {}
        for result in self.results:
            algo = result.config.algorithm
            if algo not in by_algorithm:
                by_algorithm[algo] = []
            by_algorithm[algo].append(result)
        
        # 按模式分组
        by_mode = {}
        for result in self.results:
            mode = result.config.mode
            if mode not in by_mode:
                by_mode[mode] = []
            by_mode[mode].append(result)
        
        summary = {
            'by_algorithm': {},
            'by_mode': {},
            'best_keep_rate': None,
            'best_speed': None,
        }
        
        # 算法对比
        for algo, results in by_algorithm.items():
            avg_keep_rate = sum(r.keep_rate for r in results) / len(results)
            avg_time = sum(r.training_time for r in results) / len(results)
            summary['by_algorithm'][algo] = {
                'count': len(results),
                'avg_keep_rate': avg_keep_rate,
                'avg_training_time': avg_time,
            }
        
        # 模式对比
        for mode, results in by_mode.items():
            avg_keep_rate = sum(r.keep_rate for r in results) / len(results)
            avg_time = sum(r.training_time for r in results) / len(results)
            summary['by_mode'][mode] = {
                'count': len(results),
                'avg_keep_rate': avg_keep_rate,
                'avg_training_time': avg_time,
            }
        
        # 最佳结果
        best_keep = max(self.results, key=lambda r: r.keep_rate)
        best_speed = min(self.results, key=lambda r: r.training_time)
        
        summary['best_keep_rate'] = {
            'config': best_keep.config.name,
            'keep_rate': best_keep.keep_rate,
        }
        summary['best_speed'] = {
            'config': best_speed.config.name,
            'training_time': best_speed.training_time,
        }
        
        return summary
    
    def save_results(self, filename: str = "benchmark_results.json"):
        """保存结果"""
        comparison = self.compare_results()
        filepath = os.path.join(self.workspace, filename)
        
        with open(filepath, 'w') as f:
            json.dump(comparison, f, indent=2)
        
        return filepath
    
    def print_summary(self):
        """打印对比总结"""
        comparison = self.compare_results()
        summary = comparison.get('summary', {})
        
        print("\n" + "="*70)
        print("Benchmark Comparison Summary")
        print("="*70)
        
        # 算法对比
        print("\nBy Algorithm:")
        for algo, stats in summary.get('by_algorithm', {}).items():
            print(f"  {algo.upper()}:")
            print(f"    • Count: {stats['count']}")
            print(f"    • Avg Keep Rate: {stats['avg_keep_rate']:.1%}")
            print(f"    • Avg Training Time: {stats['avg_training_time']:.1f}s")
        
        # 模式对比
        print("\nBy Mode:")
        for mode, stats in summary.get('by_mode', {}).items():
            print(f"  {mode.upper()}:")
            print(f"    • Count: {stats['count']}")
            print(f"    • Avg Keep Rate: {stats['avg_keep_rate']:.1%}")
            print(f"    • Avg Training Time: {stats['avg_training_time']:.1f}s")
        
        # 最佳结果
        best_keep = summary.get('best_keep_rate', {})
        best_speed = summary.get('best_speed', {})
        
        print("\nBest Results:")
        print(f"  • Best Keep Rate: {best_keep.get('config')} ({best_keep.get('keep_rate', 0):.1%})")
        print(f"  • Best Speed: {best_speed.get('config')} ({best_speed.get('training_time', 0):.1f}s)")


class HyperparameterOptimizer:
    """超参数优化框架"""
    
    def __init__(self, workspace: str = "hyperparams"):
        self.workspace = workspace
        os.makedirs(workspace, exist_ok=True)
        self.runner = BenchmarkRunner(workspace)
    
    def optimize_reward_scales(self, scales: List[float], iterations: int = 5) -> Dict[str, Any]:
        """优化奖励尺度"""
        print("\n" + "="*70)
        print("Optimizing Reward Scales")
        print("="*70)
        
        results = {}
        
        for scale in scales:
            config = BenchmarkConfig(
                name=f"reward_scale_{scale}",
                mode="cold_start",
                algorithm="grpo",
                reward_scale=scale,
                iterations=iterations,
                description=f"Testing reward scale: {scale}",
            )
            
            print(f"\nTesting reward scale: {scale}")
            result = self.runner.run_benchmark(config)
            results[scale] = {
                'keep_rate': result.keep_rate,
                'training_time': result.training_time,
                'avg_reward': result.avg_reward,
            }
            print(f"  Keep rate: {result.keep_rate:.1%}")
            print(f"  Training time: {result.training_time:.1f}s")
        
        # 找最优尺度
        best_scale = max(results.keys(), key=lambda s: results[s]['keep_rate'])
        
        print(f"\n✅ Best reward scale: {best_scale} (keep rate: {results[best_scale]['keep_rate']:.1%})")
        
        return results
    
    def optimize_stage_thresholds(self, thresholds: List[Tuple[float, float]], iterations: int = 5) -> Dict[str, Any]:
        """优化学习阶段阈值"""
        print("\n" + "="*70)
        print("Optimizing Stage Thresholds")
        print("="*70)
        
        results = {}
        
        for threshold in thresholds:
            config = BenchmarkConfig(
                name=f"threshold_{threshold[0]}_{threshold[1]}",
                mode="cold_start",
                algorithm="grpo",
                learning_stage_thresholds=threshold,
                iterations=iterations,
                description=f"Testing thresholds: {threshold}",
            )
            
            print(f"\nTesting thresholds: {threshold}")
            result = self.runner.run_benchmark(config)
            results[str(threshold)] = {
                'keep_rate': result.keep_rate,
                'training_time': result.training_time,
                'stage_transitions': result.stage_transitions,
            }
            print(f"  Keep rate: {result.keep_rate:.1%}")
            print(f"  Stage transitions: {result.stage_transitions}")
        
        # 找最优阈值
        best_threshold = max(results.keys(), key=lambda t: results[t]['keep_rate'])
        
        print(f"\n✅ Best thresholds: {best_threshold} (keep rate: {results[best_threshold]['keep_rate']:.1%})")
        
        return results
    
    def run_full_optimization(self) -> Dict[str, Any]:
        """运行完整的超参数优化"""
        print("\n" + "="*70)
        print("Full Hyperparameter Optimization")
        print("="*70)
        
        # 测试不同的奖励尺度
        reward_scales = [0.5, 0.7, 1.0, 1.3, 1.5]
        reward_results = self.optimize_reward_scales(reward_scales, iterations=3)
        
        # 测试不同的学习阶段阈值
        thresholds = [(0.2, 0.5), (0.3, 0.6), (0.4, 0.7)]
        threshold_results = self.optimize_stage_thresholds(thresholds, iterations=3)
        
        # 生成最终报告
        self.runner.print_summary()
        
        return {
            'reward_scales': reward_results,
            'stage_thresholds': threshold_results,
        }


if __name__ == "__main__":
    # 示例：运行性能对比
    runner = BenchmarkRunner()
    
    # 对比 GRPO vs GAE
    configs = [
        BenchmarkConfig(
            name="grpo_cold_start",
            mode="cold_start",
            algorithm="grpo",
            iterations=5,
            description="GRPO with cold start",
        ),
        BenchmarkConfig(
            name="gae_cold_start",
            mode="cold_start",
            algorithm="gae",
            iterations=5,
            description="GAE with cold start",
        ),
    ]
    
    for config in configs:
        print(f"\nRunning: {config.name}")
        result = runner.run_benchmark(config)
        print(f"  Keep rate: {result.keep_rate:.1%}")
        print(f"  Training time: {result.training_time:.1f}s")
    
    # 打印对比总结
    runner.print_summary()
    
    # 保存结果
    filepath = runner.save_results()
    print(f"\nResults saved to: {filepath}")
