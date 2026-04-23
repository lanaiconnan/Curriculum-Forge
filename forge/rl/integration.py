"""Forge RL — 与 DualAgentCoordinator 的集成

将 HarnessFeedbackLoop 无缝嵌入现有训练流程。

使用方式：

    from forge.rl import attach_feedback_loop, forge_train

    # 方式1：装饰器风格
    coordinator = attach_feedback_loop(coordinator)

    # 方式2：CLI 入口（推荐）
    results = forge_train(
        coordinator=coordinator,
        engine=engine,
        episodes=20,
        harness_suite=suite,
    )

    # 方式3：独立运行（不修改现有 coordinator）
    loop = HarnessFeedbackLoop(rl_trainer, generator)
    loop.run_and_feedback(engine, harness_suite)
"""

import sys
import os

# 将 forge 添加到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from forge.rl import (
    HarnessFeedbackLoop,
    RLHyperTuner,
    FeedbackTrigger,
    FeedbackAction,
    LoopStats,
    HyperParams,
)

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from services.dual_agent import DualAgentCoordinator, EpisodeResult
    from services.harness import HarnessReport, HarnessSuite, HarnessRunner


# ─── 主入口函数 ───────────────────────────────────────────────────────────────

def forge_train(
    coordinator: 'DualAgentCoordinator',
    engine,
    episodes: int = 10,
    harness_suite: Optional['HarnessSuite'] = None,
    harness_after_episode: int = 1,
    verbose: bool = True,
    early_stop: bool = True,
) -> Dict[str, Any]:
    """
    Forge 风格的训练入口：RL ↔ Harness 闭环驱动。

    对比原始 coordinator.run_training()：
    - 多了一步：每次 episode 后运行 Harness 评估
    - 多了一步：Harness 报告触发超参/难度自适应
    - 多了 early_stop：plateau/degradation 时自动停止

    Args:
        coordinator:    DualAgentCoordinator 实例
        engine:         QueryEngine 实例（用于 HarnessRunner）
        episodes:       最大训练轮数
        harness_suite: HarnessSuite 实例（None 则跳过 Harness 评估）
        harness_after_episode: 每隔几轮跑一次 Harness（默认1=每轮都跑）
        verbose:        是否打印诊断报告
        early_stop:     是否启用自动早停

    Returns:
        {
            "episodes": [EpisodeResult, ...],
            "harness_reports": [HarnessReport, ...],
            "feedback_actions": [FeedbackAction, ...],
            "loop_diagnosis": {...},
            "total_duration": float,
        }
    """
    # ── 1. 构建闭环 ────────────────────────────────────────────────────────
    rl_trainer = coordinator.trainer_service
    generator  = coordinator.env_service

    loop = HarnessFeedbackLoop(
        rl_trainer=rl_trainer,
        generator=generator,
    )

    # 默认钩子（可覆盖）
    tuner = loop.hyper_tuner

    loop.register_hook(FeedbackTrigger.LOW_ACCURACY.value,  lambda s: tuner.lower_lr(s))
    loop.register_hook(FeedbackTrigger.EXCELLENT.value,     lambda s: tuner.raise_lr(s))
    loop.register_hook(FeedbackTrigger.STAGNATION.value,   lambda s: tuner.reduce_batch(s))
    loop.register_hook(FeedbackTrigger.DEGRADATION.value,   lambda s: tuner.loosen_clip(s))

    # ── 2. 准备 Harness Runner ─────────────────────────────────────────────
    if harness_suite is not None:
        from services.harness import HarnessRunner
        harness_runner = HarnessRunner(engine)
    else:
        harness_runner = None

    # ── 3. 训练循环 ───────────────────────────────────────────────────────
    episodes_results: List['EpisodeResult'] = []
    harness_reports: List[Any] = []
    all_feedback: List['FeedbackAction'] = []

    import time
    start_time = time.time()

    for i in range(1, episodes + 1):
        # Run one RL episode
        episode = coordinator.run_episode()
        episodes_results.append(episode)

        if verbose:
            print(f"\n[Forge] Episode {i}/{episodes}  "
                  f"keep_rate={episode.keep_rate:.1%}  "
                  f"reward={episode.total_reward:.3f}  "
                  f"stage={episode.stage}")

        # Run Harness every N episodes
        if harness_runner and harness_suite and (i % harness_after_episode == 0):
            harness_report = harness_runner.run(
                harness_suite.cases(),
                suite_name=f"{harness_suite.name}_ep{i}",
            )
            harness_reports.append(harness_report)

            if verbose:
                print(f"[Forge] Harness  →  "
                      f"accuracy={harness_report.tool_accuracy:.1%}  "
                      f"rfinal={harness_report.avg_rfinal:+.3f}  "
                      f"pass_rate={harness_report.pass_rate:.1%}")

            # 触发闭环
            feedback = loop.on_harness_report(harness_report)
            all_feedback.extend(feedback)

            # 打印诊断
            if verbose and i % 5 == 0:
                loop.print_diagnosis()

            # Early stop
            if early_stop and not loop.should_continue_training():
                print(f"\n[Forge] 🚫 Early stop triggered at episode {i}")
                print(f"        原因: {loop.get_diagnosis()['recommended_stage']}")
                break

    duration = time.time() - start_time

    # ── 4. 返回汇总 ────────────────────────────────────────────────────────
    result = {
        "episodes": episodes_results,
        "harness_reports": harness_reports,
        "feedback_actions": all_feedback,
        "loop_diagnosis": loop.get_diagnosis(),
        "total_episodes": len(episodes_results),
        "total_harness_runs": len(harness_reports),
        "total_duration": round(duration, 2),
        "loop_stats": loop.stats.to_dict(),
    }

    if verbose:
        print("\n" + "=" * 60)
        print("Forge Training Complete")
        print("=" * 60)
        print(f"  Episodes:      {result['total_episodes']}/{episodes}")
        print(f"  Harness runs:  {result['total_harness_runs']}")
        print(f"  Total time:    {result['total_duration']:.1f}s")
        print(f"  Feedback fires: {len(all_feedback)}")
        diag = loop.get_diagnosis()
        print(f"  Final accuracy: {diag['latest_accuracy']:.1%}")
        print(f"  Recommended:    {diag['recommended_stage']}")
        print(f"  Should continue: {diag['should_continue']}")
        print("=" * 60)

    return result


# ─── 装饰器：给已有 Coordinator 附加闭环 ────────────────────────────────────

def attach_feedback_loop(
    coordinator: 'DualAgentCoordinator',
    engine,
    harness_suite: Optional['HarnessSuite'] = None,
    hooks: Optional[Dict[str, callable]] = None,
) -> 'DualAgentCoordinator':
    """
    给 DualAgentCoordinator 附加 HarnessFeedbackLoop。

    修改 coordinator.run_training() 的行为：
    - 训练结束后自动运行 Harness
    - Harness 报告触发超参/难度自适应
    - 添加 forge_* 属性

    Args:
        coordinator:    要改造的 coordinator
        engine:         QueryEngine（用于 HarnessRunner）
        harness_suite: 可选，指定 HarnessSuite
        hooks:          可选，覆盖默认钩子 {trigger_name: fn}

    Returns:
        改造后的 coordinator（同一对象，in-place 修改）
    """
    # 初始化 loop
    loop = HarnessFeedbackLoop(
        rl_trainer=coordinator.trainer_service,
        generator=coordinator.env_service,
    )

    # 注册钩子
    tuner = loop.hyper_tuner
    default_hooks = {
        FeedbackTrigger.LOW_ACCURACY.value: lambda s: tuner.lower_lr(s),
        FeedbackTrigger.EXCELLENT.value:     lambda s: (tuner.raise_lr(s), tuner.current.apply(coordinator.trainer_service)),
        FeedbackTrigger.STAGNATION.value:   lambda s: tuner.reduce_batch(s),
        FeedbackTrigger.DEGRADATION.value:   lambda s: tuner.loosen_clip(s),
    }
    if hooks:
        default_hooks.update(hooks)

    for trigger, fn in default_hooks.items():
        loop.register_hook(trigger, fn)

    # 注入到 coordinator
    coordinator.forge_loop = loop          # type: ignore[attr-defined]
    coordinator.forge_engine = engine      # type: ignore[attr-defined]
    coordinator.forge_suite = harness_suite # type: ignore[attr-defined]

    # Patch run_training to add harness step
    _original_run_training = coordinator.run_training

    def _forge_run_training(episodes: int = 10, **kwargs) -> List['EpisodeResult']:
        if harness_suite is None:
            return _original_run_training(episodes=episodes, **kwargs)

        from services.harness import HarnessRunner
        harness_runner = HarnessRunner(engine)

        results = []
        for i in range(1, episodes + 1):
            episode = coordinator.run_episode()
            results.append(episode)

            if i % 1 == 0:  # 每轮都跑
                harness_report = harness_runner.run(
                    harness_suite.cases(),
                    suite_name=f"forge_ep{i}",
                )
                loop.on_harness_report(harness_report)

                if not loop.should_continue_training():
                    print(f"[Forge] Early stop at episode {i}")
                    break

        return results

    coordinator.run_training = _forge_run_training  # type: ignore[method-assign]

    return coordinator


# ─── CLI 入口（可通过 main.py 调用）────────────────────────────────────────

if __name__ == "__main__":
    print("Usage:")
    print("  from forge.rl.integration import forge_train, attach_feedback_loop")
    print()
    print("  # 推荐：直接调用 forge_train")
    print("  results = forge_train(coordinator, engine, episodes=20, harness_suite=suite)")
    print()
    print("  # 或：改造现有 coordinator")
    print("  attach_feedback_loop(coordinator, engine, harness_suite=suite)")
    print("  coordinator.run_training(episodes=20)  # 已含 Harness 闭环")
