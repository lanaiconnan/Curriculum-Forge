"""Forge Adapters — 横向对比工具

在多个 Agent Adapter 上运行同一 HarnessSuite，返回对比报告。

使用方式：
    from forge.adapters import AgentBenchmark

    benchmark = AgentBenchmark(
        adapters={
            "Curriculum-Forge": create_adapter("mock"),
            "Claude-Code":      create_adapter("claude-code", config={...}),
            "Letta":           create_adapter("letta", config={...}),
            "Goose":           create_adapter("goose", config={...}),
        },
        harness_suite=suite,
    )

    report = benchmark.run(verbose=True)
    print(report.summary())

    # 导出 CSV
    report.to_csv("benchmark_results.csv")
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, TYPE_CHECKING
from concurrent.futures import ThreadPoolExecutor, as_completed

if TYPE_CHECKING:
    from services.harness import HarnessSuite, HarnessCase, HarnessReport

logger = logging.getLogger(__name__)


# ─── 数据结构 ──────────────────────────────────────────────────────────────

@dataclass
class AdapterScore:
    """单个 Adapter 的评分"""
    adapter_name: str
    tool_accuracy: float = 0.0
    avg_rname: float = 0.0
    avg_rparam: float = 0.0
    avg_rfinal: float = 0.0
    pass_rate: float = 0.0
    total_cases: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    error_count: int = 0
    duration: float = 0.0
    # 每个 case 的结果
    case_results: Dict[str, str] = field(default_factory=dict)  # case_id → verdict


@dataclass
class BenchmarkReport:
    """横向对比报告"""
    adapters: Dict[str, AdapterScore]
    suite_name: str
    total_duration: float
    timestamp: float = field(default_factory=time.time)

    def summary(self) -> str:
        lines = [
            f"{'='*65}",
            f"Benchmark Report: {self.suite_name}",
            f"{'='*65}",
            f"{'Adapter':<22} {'Acc':>6} {'rname':>7} {'rparam':>7} {'rfinal':>8} {'Pass%':>6}  {'Time':>7}",
            f"{'-'*65}",
        ]

        # 按 tool_accuracy 排序
        sorted_adapters = sorted(
            self.adapters.values(),
            key=lambda a: a.tool_accuracy,
            reverse=True,
        )

        for score in sorted_adapters:
            lines.append(
                f"{score.adapter_name:<22} "
                f"{score.tool_accuracy:>6.1%} "
                f"{score.avg_rname:>+7.3f} "
                f"{score.avg_rparam:>+7.3f} "
                f"{score.avg_rfinal:>+8.3f} "
                f"{score.pass_rate:>6.1%} "
                f"{score.duration:>6.1f}s"
            )

        lines.append(f"{'='*65}")
        lines.append(f"Total duration: {self.total_duration:.1f}s")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suite": self.suite_name,
            "total_duration": round(self.total_duration, 2),
            "timestamp": self.timestamp,
            "adapters": {
                name: {
                    "tool_accuracy": round(s.tool_accuracy, 4),
                    "avg_rname": round(s.avg_rname, 4),
                    "avg_rparam": round(s.avg_rparam, 4),
                    "avg_rfinal": round(s.avg_rfinal, 4),
                    "pass_rate": round(s.pass_rate, 4),
                    "passed": s.passed,
                    "failed": s.failed,
                    "skipped": s.skipped,
                    "errors": s.error_count,
                    "duration": round(s.duration, 2),
                    "case_results": s.case_results,
                }
                for name, s in self.adapters.items()
            },
        }

    def to_csv(self, path: str) -> None:
        """导出为 CSV"""
        import csv

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # Header
            writer.writerow([
                "adapter", "case_id", "verdict",
                "rname", "rparam", "rfinal",
                "actual_tool", "expected_tool",
            ])

            for name, score in self.adapters.items():
                for case_id, verdict in score.case_results.items():
                    writer.writerow([
                        name, case_id, verdict,
                        "", "", "",
                        "", "",
                    ])

    def winner(self) -> str:
        """返回准确率最高的 Adapter 名称"""
        if not self.adapters:
            return ""
        return max(
            self.adapters,
            key=lambda n: self.adapters[n].tool_accuracy
        )


# ─── Benchmark 引擎 ─────────────────────────────────────────────────────────

class AgentBenchmark:
    """
    跨 Agent Harness 对比引擎。

    功能：
    - 同一 HarnessSuite 在多个 Adapter 上运行
    - 并行或串行执行
    - 生成对比报告
    - 支持 partial scoring（正确工具但错误参数 → 部分得分）
    """

    def __init__(
        self,
        adapters: Dict[str, Any],
        harness_suite: 'HarnessSuite',
        parallel: bool = True,
        max_workers: int = 4,
        verbose: bool = False,
    ):
        """
        Args:
            adapters: {名称: AgentAdapter 实例}
            harness_suite: HarnessSuite 实例
            parallel: 是否并行执行各 Adapter
            max_workers: 并行 worker 数
            verbose: 是否打印详细日志
        """
        self.adapters = adapters
        self.suite = harness_suite
        self.parallel = parallel
        self.max_workers = max_workers
        self.verbose = verbose

        # Harness 报告缓存（每个 Adapter 一个）
        self._reports: Dict[str, Any] = {}

    # ── 单 Adapter 运行 ──────────────────────────────────────────────────

    def _run_single(self, name: str, adapter: Any) -> AdapterScore:
        """
        在单个 Adapter 上运行整个 suite。
        """
        from services.harness import HarnessRunner
        from services.query_engine import TokenUsage

        # 把 Adapter 包装成 HarnessRunner 兼容的 engine
        harness_wrapper = self._wrap_adapter(adapter)

        runner = HarnessRunner(harness_wrapper)
        cases = self.suite.cases()

        start = time.time()

        try:
            report = runner.run(cases, suite_name=f"{self.suite.name}_{name}")
        except Exception as e:
            logger.error(f"Benchmark '{name}' failed: {e}")
            return AdapterScore(adapter_name=name, error_count=len(cases))

        duration = time.time() - start
        self._reports[name] = report

        # 转换为 AdapterScore
        score = AdapterScore(
            adapter_name=name,
            tool_accuracy=report.tool_accuracy,
            avg_rname=report.avg_rname,
            avg_rparam=report.avg_rparam,
            avg_rfinal=report.avg_rfinal,
            pass_rate=report.pass_rate,
            total_cases=report.total,
            passed=report.passed,
            failed=report.failed,
            skipped=report.skipped,
            error_count=report.errors,
            duration=duration,
        )

        # 每个 case 的结果
        for r in report.results:
            score.case_results[r.case_id] = r.verdict.value

        return score

    def _wrap_adapter(self, adapter):
        """
        将 AgentAdapter 包装为 HarnessRunner 兼容的 engine。
        """
        from services.harness import QueryResult
        from services.query_engine import TokenUsage

        class HarnessWrapper:
            def __init__(self, adap):
                self._adapter = adap
                self._usage = TokenUsage()

            def reset(self):
                self._adapter.reset()
                self._usage = TokenUsage()

            def submit(self, prompt, extra_system=None):
                result = self._adapter.submit(prompt, extra_system)
                self._usage.input_tokens += len(prompt) // 4
                self._usage.output_tokens += len(result.final_response) // 4

                return QueryResult(
                    final_response=result.final_response,
                    turns=result.turns,
                    tool_calls=[
                        {"name": tc.name, "input": tc.input}
                        for tc in result.tool_calls
                    ],
                    usage=self._usage,
                    success=result.success,
                    error=result.error,
                )

        return HarnessWrapper(adapter)

    # ── 主入口 ──────────────────────────────────────────────────────────

    def run(self) -> BenchmarkReport:
        """
        在所有 Adapter 上运行 benchmark。

        Returns:
            BenchmarkReport
        """
        start = time.time()
        scores: Dict[str, AdapterScore] = {}

        if self.parallel:
            # 并行
            with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                futures = {
                    pool.submit(self._run_single, name, adapter): name
                    for name, adapter in self.adapters.items()
                }
                for future in as_completed(futures):
                    name = futures[future]
                    try:
                        score = future.result()
                        scores[name] = score
                        if self.verbose:
                            print(f"  ✅ {name}: accuracy={score.tool_accuracy:.1%}  "
                                  f"rfinal={score.avg_rfinal:+.3f}  "
                                  f"{score.passed}/{score.total_cases} passed")
                    except Exception as e:
                        logger.error(f"{name} failed: {e}")
                        scores[name] = AdapterScore(adapter_name=name)
        else:
            # 串行
            for name, adapter in self.adapters.items():
                try:
                    score = self