"""Curriculum-Forge Service Architecture - Main Entry Point

This module provides the CLI and programmatic entry point for running
Curriculum-Forge with the service-oriented architecture.

Usage:
    # CLI
    python3 -m services.main summary
    python3 -m services.main run --iterations 10
    python3 -m services.main health

    # Programmatic
    from services.main import run_training
    
    results = run_training(iterations=10)
"""

import argparse
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from . import (
    ServiceProvider,
    EnvironmentService,
    EnvironmentServiceConfig,
    LearnerService,
    LearnerServiceConfig,
    RLTrainerService,
    RLConfig,
    ProgressMetrics,
    ExperimentRecord,
    TrainingStats,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_provider(
    workspace: str = ".",
    max_iterations: int = 5,
) -> ServiceProvider:
    """
    Create and configure the service provider.
    
    Args:
        workspace: Working directory
        max_iterations: Max iterations per experiment
    
    Returns:
        Configured ServiceProvider (not started)
    """
    provider = ServiceProvider()
    
    # Configure EnvironmentService (Agent A)
    env_config = EnvironmentServiceConfig(
        name="environment",
        workspace=workspace,
        max_tasks_beginner=2,
        max_tasks_intermediate=3,
        max_tasks_advanced=5,
    )
    provider.configure(EnvironmentService, env_config)
    
    # Configure LearnerService (Agent B)
    learner_config = LearnerServiceConfig(
        name="learner",
        workspace=workspace,
        max_iterations=max_iterations,
        keep_threshold=0.5,
    )
    provider.configure(LearnerService, learner_config)
    
    # Configure RLTrainerService
    rl_config = RLConfig(
        name="trainer",
        learning_rate=3e-4,
        gamma=0.99,
        epsilon=0.2,
        use_grpo=True,
    )
    provider.configure(RLTrainerService, rl_config)
    
    return provider


def run_training(
    iterations: int = 10,
    workspace: str = ".",
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Run the complete training loop.
    
    This is the main entry point for training.
    
    Args:
        iterations: Number of training iterations
        workspace: Working directory
        verbose: Print progress
    
    Returns:
        Training results and statistics
    """
    logger.info(f"Starting training: {iterations} iterations")
    
    # Create provider
    provider = create_provider(workspace=workspace)
    
    # Start services
    provider.start()
    
    # Get services
    env_service = provider.get(EnvironmentService)
    learner = provider.get(LearnerService)
    trainer = provider.get(RLTrainerService)
    
    all_results: List[ExperimentRecord] = []
    all_stats: List[TrainingStats] = []
    
    try:
        for epoch in range(iterations):
            if verbose:
                print(f"\n{'='*60}")
                print(f"Epoch {epoch + 1}/{iterations}")
                print(f"{'='*60}")
            
            # Get current progress
            progress = learner.get_progress()
            
            if verbose:
                print(f"[Progress] keep_rate={progress.keep_rate:.1%}, stage={progress.current_stage.value}")
            
            # Agent A: Generate environment
            env = env_service.generate_environment(progress)
            
            if verbose:
                print(f"[Environment] {env.name} (difficulty={env.difficulty:.1f})")
            
            # Agent B: Run experiments
            results = learner.run_experiments(env)
            all_results.extend(results)
            
            # RL Trainer: Train step
            stats = trainer.train_step()
            all_stats.append(stats)
            
            if verbose:
                print(f"[Training] avg_reward={stats.avg_reward:.3f}, buffer={stats.experiences}")
        
        # Final summary
        final_progress = learner.get_progress()
        
        return {
            "iterations": iterations,
            "total_experiments": len(all_results),
            "keep_rate": final_progress.keep_rate,
            "final_stage": final_progress.current_stage.value,
            "avg_reward": sum(s.avg_reward for s in all_stats) / len(all_stats) if all_stats else 0.0,
            "total_reward": sum(s.total_reward for s in all_stats),
            "results": [r.to_dict() for r in all_results],
        }
        
    finally:
        provider.stop()


def print_summary() -> None:
    """Print service architecture summary"""
    print("=" * 60)
    print("Curriculum-Forge Service Architecture")
    print("=" * 60)
    print()
    print("Services:")
    print("  ├─ EnvironmentService (Agent A)")
    print("  │    └─ generate_environment(progress) → TrainingEnvironment")
    print("  │")
    print("  ├─ LearnerService (Agent B)")
    print("  │    └─ run_experiments(env) → List[ExperimentRecord]")
    print("  │")
    print("  └─ RLTrainerService")
    print("       └─ train_step() → TrainingStats")
    print()
    print("Models:")
    print("  ├─ TrainingEnvironment")
    print("  ├─ ExperimentRecord")
    print("  ├─ ProgressMetrics")
    print("  └─ RewardBreakdown")
    print()
    print("Container:")
    print("  └─ ServiceProvider")
    print("       ├─ configure(Service, config)")
    print("       ├─ start() / stop()")
    print("       └─ get(Service) → Service")
    print()


def print_health(provider: ServiceProvider) -> None:
    """Print health status of all services"""
    health = provider.health_check()
    
    print("=" * 60)
    print("Service Health Check")
    print("=" * 60)
    print()
    print(f"Overall Status: {health['status'].upper()}")
    print()
    
    for service in health["services"]:
        status_icon = "✅" if service["is_running"] else "❌"
        print(f"{status_icon} {service['name']}")
        print(f"   State: {service['state']}")
        print(f"   Uptime: {service['uptime']:.1f}s")
        print(f"   Error Rate: {service['error_rate']:.1%}")
        print()


def main() -> None:
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Curriculum-Forge Service Architecture"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # summary command
    subparsers.add_parser("summary", help="Print architecture summary")
    
    # run command
    run_parser = subparsers.add_parser("run", help="Run training")
    run_parser.add_argument("--iterations", "-i", type=int, default=10,
                           help="Number of iterations")
    run_parser.add_argument("--workspace", "-w", default=".",
                           help="Working directory")
    run_parser.add_argument("--quiet", "-q", action="store_true",
                           help="Suppress output")
    
    # health command
    subparsers.add_parser("health", help="Check service health")
    
    args = parser.parse_args()
    
    if args.command == "summary":
        print_summary()
    elif args.command == "run":
        results = run_training(
            iterations=args.iterations,
            workspace=args.workspace,
            verbose=not args.quiet,
        )
        if not args.quiet:
            print("\n" + "=" * 60)
            print("Training Complete")
            print("=" * 60)
            print(f"Total experiments: {results['total_experiments']}")
            print(f"Keep rate: {results['keep_rate']:.1%}")
            print(f"Final stage: {results['final_stage']}")
            print(f"Avg reward: {results['avg_reward']:.3f}")
    elif args.command == "health":
        provider = create_provider()
        provider.start()
        try:
            print_health(provider)
        finally:
            provider.stop()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
