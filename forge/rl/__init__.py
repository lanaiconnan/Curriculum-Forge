"""Forge RL — RL↔Harness 闭环反馈层

核心思路：
    Harness 报告是 RL 训练的「裁判打分卡」。
    每次 RL checkpoint 都对应一个 HarnessReport，
    报告中的指标直接驱动 RL 超参调整和课程策略更新。

Architecture：
    ┌──────────────────────────────────────────────────────────┐
    │               HarnessFeedbackLoop                         │
    │                                                           │
    │  RL Training ──▶ Agent B ──▶ Harness Runner              │
    │                                     │                     │
    │                              HarnessReport               │
    │                                     │                     │
    │                        ┌────────────▼─────────────┐     │
    │                        │   Feedback Analyzer        │     │
    │                        │   (on_report hook)         │     │
    │                        └────────────┬─────────────┘     │
    │                                  │                      │
    │          ┌───────────────────────┼──────────────────┐   │
    │          │                       │                   │   │
    │    ┌─────▼─────┐          ┌──────▼──────┐    ┌──────▼──┐│
    │    │ RL Tuner  │          │Curriculum  │    │ Early   ││
    │    │ (超参)    │          │ Escalator  │    │ Stopper ││
    │    └───────────┘          │ (难度)      │    └─────────┘│
    │                            └────────────┘              │
    └──────────────────────────────────────────────────────────┘

Usage：
    from forge.rl import HarnessFeedbackLoop, RLHyperTuner

    tuner = RLHyperTuner()
    loop  = HarnessFeedbackLoop(rl_trainer=trainer, generator=generator)
    loop.register_hook('low_accuracy', tuner.lower_lr)
    loop.register_hook('stagnation',  tuner.reduce_batch)

    # RL 训练后立即运行 Harness 评估
    harness_report = loop.run_harness(engine, suite)
    loop.on_harness_report(harness_report)
"""

import time
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from enum import Enum

logger = logging.getLogger(__name__)


# ─── Trigger ──────────────────────────────────────────────────────────────────

class FeedbackTrigger(Enum):
    """闭环触发器类型"""
    LOW_ACCURACY       = "low_accuracy"      # tool_accuracy < 阈值
    STAGNATION         = "stagnation"        # 多轮无提升
    PLATEAU            = "plateau"           # 高原（长期无提升）
    EXCELLENT          = "excellent"         # 连续高精度 → 升难度
    DEGRADATION        = "degradation"       # 性能下降
    FIRST_RUN          = "first_run"         # 首轮基准


@dataclass
class FeedbackAction:
    """一次反馈动作"""
    trigger: FeedbackTrigger
    hook_name: str
    reason: str
    metrics: Dict[str, float]
    action_taken: Optional[str] = None
    ts: float = field(default_factory=time.time)


# ─── RLHyperTuner ─────────────────────────────────────────────────────────────

@dataclass
class HyperParams:
    """RL 超参快照"""
    learning_rate: float
    entropy_coef: float
    batch_size: int
    group_size: int
    clip_ratio: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lr": self.learning_rate,
            "entropy_coef": self.entropy_coef,
            "batch_size": self.batch_size,
            "group_size": self.group_size,
            "clip_ratio": self.clip_ratio,
        }

    def apply(self, trainer) -> None:
        """将超参应用到 RLTrainerService"""
        trainer.config.learning_rate = self.learning_rate
        trainer.config.batch_size = self.batch_size
        trainer.config.epsilon = self.clip_ratio
        # 如果 trainer 有 entropy_coef 也一并更新
        if hasattr(trainer, 'entropy_coef'):
            trainer.entropy_coef = self.entropy_coef


class RLHyperTuner:
    """
    基于 Harness 反馈的 RL 超参自动调节器。

    策略：
    - 工具准确率低 → 增大 entropy 探索，降低学习率
    - 连续高精度 → 提高学习率 + 升难度
    - 性能高原 → 切换课程策略（回退或分叉）
    """

    def __init__(
        self,
        base_lr: float = 3e-4,
        base_entropy: float = 0.01,
        base_batch: int = 32,
        base_group: int = 4,
        base_clip: float = 0.2,
    ):
        self.base = HyperParams(base_lr, base_entropy, base_batch, base_group, base_clip)
        self.current = HyperParams(base_lr, base_entropy, base_batch, base_group, base_clip)
        self.history: List[HyperParams] = []

        # 调节记录
        self._adjustment_log: List[Dict[str, Any]] = []

    # ── 预设策略 ──────────────────────────────────────────────────────────────

    def lower_lr(self, severity: float = 1.0) -> HyperParams:
        """
        工具准确率低 → 降低学习率，增加探索。

        severity ∈ [0, 1]，0=轻微，1=严重。
        """
        lr = self.current.learning_rate * max(0.5, 1.0 - severity * 0.3)
        entropy = self.current.entropy_coef * (1.0 + severity * 0.5)
        self._update(HyperParams(
            learning_rate=lr,
            entropy_coef=entropy,
            batch_size=self.current.batch_size,
            group_size=self.current.group_size,
            clip_ratio=self.current.clip_ratio,
        ), reason=f"lower_lr(severity={severity:.2f})")
        return self.current

    def raise_lr(self, severity: float = 1.0) -> HyperParams:
        """
        连续高精度 → 提高学习率，加快收敛。
        """
        lr = min(self.current.learning_rate * (1.0 + severity * 0.5), self.base.learning_rate * 3)
        entropy = max(self.current.entropy_coef * 0.7, self.base.entropy_coef * 0.5)
        self._update(HyperParams(
            learning_rate=lr,
            entropy_coef=entropy,
            batch_size=self.current.batch_size,
            group_size=self.current.group_size,
            clip_ratio=self.current.clip_ratio,
        ), reason=f"raise_lr(severity={severity:.2f})")
        return self.current

    def reduce_batch(self, severity: float = 1.0) -> HyperParams:
        """
        性能高原 → 减小 batch_size，增加更新频率。
        """
        batch = max(8, int(self.current.batch_size * (1.0 - severity * 0.3)))
        self._update(HyperParams(
            learning_rate=self.current.learning_rate,
            entropy_coef=self.current.entropy_coef,
            batch_size=batch,
            group_size=self.current.group_size,
            clip_ratio=self.current.clip_ratio,
        ), reason=f"reduce_batch(severity={severity:.2f})")
        return self.current

    def expand_group(self, severity: float = 1.0) -> HyperParams:
        """
        方差大 → 增大 group_size，减少方差。
        """
        group = min(16, int(self.current.group_size * (1.0 + severity * 0.5)))
        self._update(HyperParams(
            learning_rate=self.current.learning_rate,
            entropy_coef=self.current.entropy_coef,
            batch_size=self.current.batch_size,
            group_size=group,
            clip_ratio=self.current.clip_ratio,
        ), reason=f"expand_group(severity={severity:.2f})")
        return self.current

    def loosen_clip(self, severity: float = 1.0) -> HyperParams:
        """
        探索不足 → 放宽 clip 比率，允许更大策略变动。
        """
        clip = min(0.4, self.current.clip_ratio * (1.0 + severity * 0.3))
        self._update(HyperParams(
            learning_rate=self.current.learning_rate,
            entropy_coef=self.current.entropy_coef,
            batch_size=self.current.batch_size,
            group_size=self.current.group_size,
            clip_ratio=clip,
        ), reason=f"loosen_clip(severity={severity:.2f})")
        return self.current

    def tighten_clip(self, severity: float = 1.0) -> HyperParams:
        """
        策略震荡 → 收紧 clip 比率，限制策略变动。
        """
        clip = max(0.05, self.current.clip_ratio * (1.0 - severity * 0.3))
        self._update(HyperParams(
            learning_rate=self.current.learning_rate,
            entropy_coef=self.current.entropy_coef,
            batch_size=self.current.batch_size,
            group_size=self.current.group_size,
            clip_ratio=clip,
        ), reason=f"tighten_clip(severity={severity:.2f})")
        return self.current

    def reset(self) -> HyperParams:
        """恢复基线超参"""
        self._update(self.base, reason="reset_to_base")
        return self.current

    # ── 内部 ──────────────────────────────────────────────────────────────────

    def _update(self, params: HyperParams, reason: str) -> None:
        self.current = params
        self.history.append(params)
        self._adjustment_log.append({
            "reason": reason,
            "params": params.to_dict(),
            "ts": time.time(),
        })
        logger.info(
            f"[RLHyperTuner] {reason} → "
            f"lr={params.learning_rate:.2e}  "
            f"entropy={params.entropy_coef:.4f}  "
            f"batch={params.batch_size}"
        )

    def get_log(self) -> List[Dict[str, Any]]:
        return self._adjustment_log


# ─── HarnessFeedbackLoop ──────────────────────────────────────────────────────

@dataclass
class LoopStats:
    """闭环运行统计"""
    runs: int = 0
    triggers: int = 0
    actions_taken: int = 0
    escalations: int = 0
    early_stops: int = 0
    stagnation_count: int = 0
    last_report_ts: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "runs": self.runs,
            "triggers": self.triggers,
            "actions_taken": self.actions_taken,
            "escalations": self.escalations,
            "early_stops": self.early_stops,
            "stagnation_count": self.stagnation_count,
        }


class HarnessFeedbackLoop:
    """
    RL ↔ Harness 闭环执行器。

    生命周期：
        loop = HarnessFeedbackLoop(rl_trainer, generator)

        # 注册回调
        loop.register_hook('low_accuracy',  lambda s: tuner.lower_lr(s))
        loop.register_hook('excellent',     lambda s: tuner.raise_lr(s))
        loop.register_hook('stagnation',    lambda s: tuner.reduce_batch(s))
        loop.register_hook('plateau',       generator.escalate_difficulty)
        loop.register_hook('degradation',   tuner.loosen_clip)

        # RL 训练后调用
        harness_report = loop.run_harness(engine, suite)
        feedback = loop.on_harness_report(harness_report)

        # 闭环决策
        should_continue = loop.should_continue_training()
        next_stage      = loop.get_recommended_stage()
    """

    # 默认阈值
    DEFAULT_ACCURACY_THRESHOLD   = 0.70
    DEFAULT_EXCELLENT_THRESHOLD  = 0.90
    DEFAULT_PLATEAU_ROUNDS       = 8
    DEFAULT_STAGNATION_ROUNDS    = 3
    DEFAULT_DEGRADATION_THRESHOLD = 0.05

    def __init__(
        self,
        rl_trainer,
        generator,
        accuracy_threshold: float = DEFAULT_ACCURACY_THRESHOLD,
        excellent_threshold: float = DEFAULT_EXCELLENT_THRESHOLD,
        plateau_rounds: int = DEFAULT_PLATEAU_ROUNDS,
        stagnation_rounds: int = DEFAULT_STAGNATION_ROUNDS,
        degradation_threshold: float = DEFAULT_DEGRADATION_THRESHOLD,
        store = None,   # ForgeStore 实例（可选）
    ):
        self.rl_trainer = rl_trainer
        self.generator = generator
        self.store = store  # ForgeStore 用于持久化

        # 阈值
        self.accuracy_threshold   = accuracy_threshold
        self.excellent_threshold = excellent_threshold
        self.plateau_rounds      = plateau_rounds
        self.stagnation_rounds   = stagnation_rounds
        self.degradation_threshold = degradation_threshold

        # 钩子：trigger_name → [callable]
        self._hooks: Dict[str, List[Callable]] = {}

        # 状态追踪
        self._report_history: List[Any] = []     # HarnessReport 列表
        self._accuracy_history: List[float] = []  # tool_accuracy 序列
        self._reward_history: List[float] = []    # avg_reward 序列
        self._round_scores: List[float] = []       # 每轮最佳分数

        # 闭环决策
        self._stagnation_count   = 0
        self._plateau_count      = 0
        self._excellent_count    = 0
        self._degradation_count  = 0
        self._last_action: Optional[FeedbackAction] = None
        self._stop_signaled       = False

        # 统计
        self.stats = LoopStats()

        # 内置超参调节器（默认实例化）
        self.hyper_tuner = RLHyperTuner()

    # ── Hooks ─────────────────────────────────────────────────────────────────

    def register_hook(self, trigger: str, fn: Callable[[float], Any]) -> None:
        """注册闭环钩子。trigger ∈ FeedbackTrigger values。"""
        if trigger not in [t.value for t in FeedbackTrigger]:
            logger.warning(f"[HarnessFeedbackLoop] Unknown trigger '{trigger}', still registering.")
        self._hooks.setdefault(trigger, []).append(fn)

    def _dispatch(self, trigger: FeedbackTrigger, severity: float) -> List[Any]:
        """触发钩子链"""
        results = []
        for fn in self._hooks.get(trigger.value, []):
            try:
                r = fn(severity)
                results.append(r)
                logger.info(f"[HarnessFeedbackLoop] Hook '{trigger.value}' fired (severity={severity:.2f}) → {fn.__name__}")
            except Exception as e:
                logger.error(f"[HarnessFeedbackLoop] Hook error in {fn.__name__}: {e}")
        return results

    # ── 核心：处理 Harness 报告 ───────────────────────────────────────────────

    def on_harness_report(self, report: Any) -> List[FeedbackAction]:
        """
        处理 Harness 报告，触发相应的反馈动作。

        Args:
            report: HarnessReport 实例（来自 services/harness.py）

        Returns:
            List[FeedbackAction]: 所有触发器及采取的动作
        """
        self.stats.runs += 1
        self.stats.last_report_ts = time.time()

        accuracy = report.tool_accuracy
        rfinal   = report.avg_rfinal
        pass_rate = report.pass_rate
        prev_accuracy = self._accuracy_history[-1] if self._accuracy_history else 0.0

        # 记录历史
        self._accuracy_history.append(accuracy)
        self._reward_history.append(rfinal)
        best = max(self._round_scores) if self._round_scores else rfinal
        self._round_scores.append(rfinal)

        actions: List[FeedbackAction] = []
        triggered: List[FeedbackTrigger] = []

        # ── 判断触发器 ──────────────────────────────────────────────────────

        # 1. 首轮基准
        if self.stats.runs == 1:
            t = FeedbackTrigger.FIRST_RUN
            triggered.append(t)
            actions.append(FeedbackAction(
                trigger=t,
                hook_name="first_run",
                reason="首轮基准记录",
                metrics={"accuracy": accuracy, "rfinal": rfinal},
            ))

        # 2. 性能下降
        degradation = prev_accuracy - accuracy
        if degradation > self.degradation_threshold:
            self._degradation_count += 1
            severity = min(1.0, degradation / 0.2)
            t = FeedbackTrigger.DEGRADATION
            triggered.append(t)
            actions.append(FeedbackAction(
                trigger=t,
                hook_name=t.value,
                reason=f"性能下降 {degradation:.3f}",
                metrics={"accuracy": accuracy, "prev": prev_accuracy, "degradation": degradation},
                action_taken=None,
            ))
            self._dispatch(t, severity)
        else:
            self._degradation_count = 0

        # 3. 低准确率
        if accuracy < self.accuracy_threshold:
            severity = (self.accuracy_threshold - accuracy) / self.accuracy_threshold
            t = FeedbackTrigger.LOW_ACCURACY
            triggered.append(t)
            actions.append(FeedbackAction(
                trigger=t,
                hook_name=t.value,
                reason=f"工具准确率 {accuracy:.1%} < {self.accuracy_threshold:.1%}",
                metrics={"accuracy": accuracy, "threshold": self.accuracy_threshold, "severity": severity},
                action_taken=None,
            ))
            self._dispatch(t, severity)

            # 低准确率 → 放宽 clip，允许更大探索
            self.hyper_tuner.loosen_clip(severity)
            self.hyper_tuner.current.apply(self.rl_trainer)

        # 4. 连续高精度 → 升难度
        if accuracy >= self.excellent_threshold and rfinal > best * 0.95:
            self._excellent_count += 1
            self._stagnation_count = 0
            self._plateau_count = 0
            if self._excellent_count >= 2:
                severity = min(1.0, (accuracy - self.excellent_threshold) / 0.1)
                t = FeedbackTrigger.EXCELLENT
                triggered.append(t)
                actions.append(FeedbackAction(
                    trigger=t,
                    hook_name=t.value,
                    reason=f"连续高精度 ({self._excellent_count} 轮 >= {self.excellent_threshold:.0%})",
                    metrics={"accuracy": accuracy, "excellent_streak": self._excellent_count},
                    action_taken=None,
                ))
                self._dispatch(t, severity)
                self.hyper_tuner.raise_lr(severity)
                self.hyper_tuner.current.apply(self.rl_trainer)
                # 生成器升难度
                if hasattr(self.generator, 'escalate_difficulty'):
                    self.generator.escalate_difficulty()
                self.stats.escalations += 1
        else:
            self._excellent_count = 0

        # 5. 停滞检测
        if len(self._round_scores) >= self.stagnation_rounds + 1:
            recent = self._round_scores[-(self.stagnation_rounds + 1):]
            improvement = recent[-1] - recent[0]
            if abs(improvement) < 0.02:
                self._stagnation_count += 1
                if self._stagnation_count >= self.stagnation_rounds:
                    severity = min(1.0, self._stagnation_count / 5)
                    t = FeedbackTrigger.STAGNATION
                    triggered.append(t)
                    actions.append(FeedbackAction(
                        trigger=t,
                        hook_name=t.value,
                        reason=f"连续 {self._stagnation_count} 轮无提升",
                        metrics={"improvement": improvement, "streak": self._stagnation_count},
                        action_taken=None,
                    ))
                    self._dispatch(t, severity)
                    self.hyper_tuner.reduce_batch(severity)
                    self.hyper_tuner.current.apply(self.rl_trainer)
                    self._stagnation_count = 0  # 重置（已处理）
                    self.stats.stagnation_count += 1
            else:
                self._stagnation_count = 0

        # 6. 高原检测
        if self._round_scores and len(self._round_scores) >= self.plateau_rounds:
            plateau_window = self._round_scores[-self.plateau_rounds:]
            variance = sum((s - sum(plateau_window)/len(plateau_window))**2 for s in plateau_window) / len(plateau_window)
            if variance < 0.005 and accuracy >= self.accuracy_threshold:
                self._plateau_count += 1
                if self._plateau_count >= 2:
                    t = FeedbackTrigger.PLATEAU
                    triggered.append(t)
                    severity = 1.0
                    actions.append(FeedbackAction(
                        trigger=t,
                        hook_name=t.value,
                        reason=f"高原期：连续 {self.plateau_rounds} 轮方差 < 0.005",
                        metrics={"variance": variance, "plateau_count": self._plateau_count},
                        action_taken=None,
                    ))
                    self._dispatch(t, severity)
                    if hasattr(self.generator, 'fork_branch'):
                        self.generator.fork_branch()  # 分叉探索新策略
                    self._plateau_count = 0

        # ── 更新状态 ──────────────────────────────────────────────────────
        self.stats.triggers += len(triggered)
        self.stats.actions_taken += sum(1 for a in actions if a.action_taken)

        logger.info(
            f"[HarnessFeedbackLoop] run={self.stats.runs}  "
            f"accuracy={accuracy:.1%}  rfinal={rfinal:+.3f}  "
            f"triggers={len(triggered)}: {[t.value for t in triggered]}"
        )

        # ── 持久化：保存报告到 ForgeStore ────────────────────────────────
        if self.store is not None:
            try:
                agent_name = getattr(engine, "backend", None)
                agent_name = getattr(agent_name, "model_name", None) if agent_name else "unknown"
                self.store.save_harness_report(
                    report,
                    agent_name=str(agent_name),
                    tags=[self.get_recommended_stage()] + [t.value for t in triggered],
                    episode_ref=getattr(report, "episode_id", None),
                )
            except Exception as e:
                logger.warning(f"[ForgeStore] Failed to save report: {e}")

        return actions

    # ── 快捷入口：一步完成 Harness + 反馈 ─────────────────────────────────────

    def run_and_feedback(
        self,
        engine,
        harness_suite,
        extra_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        一步完成：运行 Harness → 处理报告 → 触发反馈。

        Returns:
            包含 harness_report + feedback_actions + recommendations 的字典。
        """
        from services.harness import HarnessRunner

        runner = HarnessRunner(engine)
        report = runner.run(harness_suite.cases(), suite_name=harness_suite.name)

        actions = self.on_harness_report(report)

        return {
            "report": report,
            "actions": actions,
            "should_continue": self.should_continue_training(),
            "recommended_stage": self.get_recommended_stage(),
            "hyper_params": self.hyper_tuner.current.to_dict(),
            "stats": self.stats.to_dict(),
            "store_ref": getattr(report, '_forge_ref', None),
        }

    # ── 决策辅助 ──────────────────────────────────────────────────────────────

    def should_continue_training(self) -> bool:
        """基于当前状态判断是否继续训练"""
        if self._stop_signaled:
            return False

        # 连续高原 → 停止
        if self._plateau_count >= 2:
            logger.info("[HarnessFeedbackLoop] Stop: plateau detected")
            return False

        # 连续降级且已达上限
        if self._degradation_count >= 3:
            logger.info("[HarnessFeedbackLoop] Stop: degradation")
            self.stats.early_stops += 1
            return False

        # 连续 20 轮无明显进步
        if len(self._accuracy_history) >= 20:
            recent = self._accuracy_history[-20:]
            if max(recent) - min(recent) < 0.03:
                logger.info("[HarnessFeedbackLoop] Stop: no progress in 20 rounds")
                return False

        return True

    def get_recommended_stage(self) -> str:
        """根据当前准确率推荐下一个课程阶段"""
        if not self._accuracy_history:
            return "beginner"
        accuracy = self._accuracy_history[-1]
        if accuracy >= self.excellent_threshold:
            return "advanced"
        elif accuracy >= self.accuracy_threshold:
            return "intermediate"
        else:
            return "beginner"

    def signal_stop(self) -> None:
        """人工发出停止信号"""
        self._stop_signaled = True

    def get_diagnosis(self) -> Dict[str, Any]:
        """获取当前诊断报告"""
        latest_accuracy = self._accuracy_history[-1] if self._accuracy_history else 0.0
        latest_rfinal   = self._reward_history[-1]   if self._reward_history   else 0.0

        diagnosis = {
            "runs": self.stats.runs,
            "latest_accuracy": latest_accuracy,
            "latest_rfinal": latest_rfinal,
            "stagnation_count": self._stagnation_count,
            "plateau_count": self._plateau_count,
            "excellent_count": self._excellent_count,
            "degradation_count": self._degradation_count,
            "should_continue": self.should_continue_training(),
            "recommended_stage": self.get_recommended_stage(),
            "hyper_params": self.hyper_tuner.current.to_dict(),
            "accuracy_trend": self._get_trend(self._accuracy_history),
            "reward_trend": self._get_trend(self._reward_history),
            "recent_actions": [
                {"trigger": a.trigger.value, "reason": a.reason}
                for a in [self._last_action] if a
            ] if self._last_action else [],
        }
        return diagnosis

    def _get_trend(self, values: List[float]) -> str:
        if len(values) < 3:
            return "insufficient_data"
        recent = values[-3:]
        slope = (recent[-1] - recent[0]) / len(recent)
        if slope > 0.01:
            return "increasing"
        elif slope < -0.01:
            return "decreasing"
        return "stable"

    def print_diagnosis(self) -> None:
        d = self.get_diagnosis()
        print("\n" + "=" * 55)
        print("HarnessFeedbackLoop 诊断报告")
        print("=" * 55)
        print(f"  运行轮数:       {d['runs']}")
        print(f"  工具准确率:     {d['latest_accuracy']:.1%}  ({d['accuracy_trend']})")
        print(f"  平均 rfinal:   {d['latest_rfinal']:+.3f}  ({d['reward_trend']})")
        print(f"  推荐阶段:       {d['recommended_stage']}")
        print(f"  是否继续:       {'✅ 是' if d['should_continue'] else '❌ 否'}")
        print(f"  当前超参:")
        hp = d['hyper_params']
        print(f"    lr={hp['lr']:.2e}  entropy={hp['entropy_coef']:.4f}  "
              f"batch={hp['batch_size']}  clip={hp['clip_ratio']:.2f}")
        if d['recent_actions']:
            print(f"  最近动作:       {d['recent_actions']}")
        print("=" * 55)
