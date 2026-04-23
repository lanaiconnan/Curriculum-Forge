#!/usr/bin/env python3
"""完整的性能对比和超参数优化脚本"""

import sys
import argparse
from benchmark import BenchmarkRunner, BenchmarkConfig, HyperparameterOptimizer


def run_algorithm_comparison():
    """对比 GRPO vs GAE"""
    print("\n" + "="*70)
    print("Algorithm Comparison: GRPO vs GAE")
    print("="*70)
    
    runner = BenchmarkRunner("benchmarks/algorithm_comparison")
    
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
        print(f"\n[Running] {config.name}")
        result = runner.run_benchmark(config)
        print(f"  ✓ Keep rate: {result.keep_rate:.1%}")
        print(f"  ✓ Avg reward: {result.avg_reward:.2f}")
        print(f"  ✓ Training time: {result.training_time:.1f}s")
    
    runner.print_summary()
    runner.save_results("algorithm_comparison.json")


def run_mode_comparison():
    """对比 Cold Start vs SFT+RL"""
    print("\n" + "="*70)
    print("Mode Comparison: Cold Start vs SFT+RL")
    print("="*70)
    
    runner = BenchmarkRunner("benchmarks/mode_comparison")
    
    configs = [
        BenchmarkConfig(
            name="cold_start_grpo",
            mode="cold_start",
            algorithm="grpo",
            iterations=5,
            description="GRPO with cold start (no SFT pretraining)",
        ),
        BenchmarkConfig(
            name="sft_pretrain_grpo",
            mode="sft_pretrain",
            algorithm="grpo",
            iterations=5,
            description="GRPO with SFT pretraining",
        ),
    ]
    
    for config in configs:
        print(f"\n[Running] {config.name}")
        result = runner.run_benchmark(config)
        print(f"  ✓ Keep rate: {result.keep_rate:.1%}")
        print(f"  ✓ Avg reward: {result.avg_reward:.2f}")
        print(f"  ✓ Training time: {result.training_time:.1f}s")
    
    runner.print_summary()
    runner.save_results("mode_comparison.json")


def run_hyperparameter_optimization():
    """运行超参数优化"""
    print("\n" + "="*70)
    print("Hyperparameter Optimization")
    print("="*70)
    
    optimizer = HyperparameterOptimizer("benchmarks/hyperparameter_optimization")
    
    # 优化奖励尺度
    print("\n[Step 1] Optimizing Reward Scales")
    reward_scales = [0.5, 0.7, 1.0, 1.3, 1.5]
    reward_results = optimizer.optimize_reward_scales(reward_scales, iterations=3)
    
    # 优化学习阶段阈值
    print("\n[Step 2] Optimizing Stage Thresholds")
    thresholds = [(0.2, 0.5), (0.3, 0.6), (0.4, 0.7)]
    threshold_results = optimizer.optimize_stage_thresholds(thresholds, iterations=3)
    
    # 打印总结
    optimizer.runner.print_summary()
    optimizer.runner.save_results("hyperparameter_optimization.json")


def main():
    parser = argparse.ArgumentParser(
        description="Performance Comparison and Hyperparameter Optimization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 对比 GRPO vs GAE
  python3 compare.py --algorithm
  
  # 对比 Cold Start vs SFT+RL
  python3 compare.py --mode
  
  # 超参数优化
  python3 compare.py --hyperparameter
  
  # 运行所有对比
  python3 compare.py --all
        """
    )
    
    parser.add_argument("--algorithm", action="store_true",
                        help="Compare GRPO vs GAE")
    parser.add_argument("--mode", action="store_true",
                        help="Compare Cold Start vs SFT+RL")
    parser.add_argument("--hyperparameter", action="store_true",
                        help="Run hyperparameter optimization")
    parser.add_argument("--all", action="store_true",
                        help="Run all comparisons")
    
    args = parser.parse_args()
    
    if args.all or not any([args.algorithm, args.mode, args.hyperparameter]):
        run_algorithm_comparison()
        run_mode_comparison()
        run_hyperparameter_optimization()
    else:
        if args.algorithm:
            run_algorithm_comparison()
        if args.mode:
            run_mode_comparison()
        if args.hyperparameter:
            run_hyperparameter_optimization()
    
    print("\n" + "="*70)
    print("✅ All benchmarks completed!")
    print("="*70)


if __name__ == "__main__":
    main()
