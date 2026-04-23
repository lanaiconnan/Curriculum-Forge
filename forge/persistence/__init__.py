"""Forge Persistence — 训练轨迹与 Harness 报告持久化

目标：每个 RL checkpoint 都对应一个 Harness 报告，
实现科研级别的可复现性和横向对比。

目录结构：
    .forge/                                  # Forge 工作目录（自动创建）
    ├── harness_reports/                     # Harness 报告存档
    │   ├── 2026-04-04/                     # 按日期分目录
    │   │   ├── run_001.json                # 完整报告（含所有 CaseResult）
    │   │   ├── run_002.json
    │   │   └── ...
    │   └── _index.json                     # 全局索引（跨日期）
    ├── episodes/                            # Episode 存档
    │   ├── ep_0001.json
    │   ├── ep_0002.json
    │   └── _index.json
    ├── curriculum_curve/                    # 课程难度曲线
    │   └── curve.json                      # JSON Lines: 每天一条难度记录
    ├── benchmarks/                          # 跨版本/跨 Agent 对比
    │   ├── openclaw_v1_vs_v2.json
    │   └── cross_agent_2026-04.json
    └── forge.toml                          # Forge 全局配置

Usage：

    from forge.persistence import ForgeStore, save_harness_report

    # 方式1：直接保存
    store = ForgeStore(base_dir=".forge")
    store.save_harness_report(report)

    # 方式2：便捷函数（自动使用默认目录）
    path = save_harness_report(report)

    # 方式3：在 FeedbackLoop 中使用（自动追加到索引）
    from forge.rl import HarnessFeedbackLoop
    loop = HarnessFeedbackLoop(trainer, generator, store=store)
"""

import os
import json
import time
import shutil
import logging
from datetime import datetime, date
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from pathlib import Path
from threading import RLock
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# ─── 目录布局常量 ─────────────────────────────────────────────────────────────

FORGE_DIR         = ".forge"
HARNESS_DIR       = "harness_reports"
EPISODES_DIR      = "episodes"
CURRICULUM_DIR    = "curriculum_curve"
BENCHMARKS_DIR    = "benchmarks"

INDEX_NAME        = "_index.json"


# ─── 数据类 ─────────────────────────────────────────────────────────────────

@dataclass
class HarnessReportRef:
    """
    Harness 报告的轻量引用（存入索引）。
    完整数据在单独的 JSON 文件中。
    """
    run_id: str              # 如 "run_001"
    timestamp: str          # ISO 格式
    suite_name: str
    agent_name: str          # Agent 名称（OpenClaw / Claude Code / ...）
    file_path: str          # 相对路径
    summary: Dict[str, Any]  # 预计算汇总（避免每次读完整文件）
    tags: List[str] = field(default_factory=list)
    episode_ref: Optional[str] = None  # 关联的 episode ID（如果有）


@dataclass
class EpisodeRef:
    """Episode 的轻量引用"""
    episode_id: str
    timestamp: str
    stage: str
    keep_rate: float
    total_reward: float
    file_path: str
    harness_run_ref: Optional[str] = None  # 关联的 harness run_id
    metadata: Dict[str, Any] = field(default_factory=dict)


# ─── 索引管理 ───────────────────────────────────────────────────────────────

class IndexManager:
    """
    管理各目录的 _index.json。

    索引结构：
    {
        "updated_at": "ISO timestamp",
        "total": N,
        "entries": [ HarnessReportRef | EpisodeRef, ... ]
    }
    """

    def __init__(self, index_path: str, lock: Optional[RLock] = None):
        self._path = Path(index_path)
        self._lock = lock or RLock()
        self._cache: Optional[Dict[str, Any]] = None

    def _read(self) -> Dict[str, Any]:
        if self._cache is not None:
            return self._cache
        if self._path.exists():
            try:
                with open(self._path) as f:
                    self._cache = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._cache = {"updated_at": "", "total": 0, "entries": []}
        else:
            self._cache = {"updated_at": "", "total": 0, "entries": []}
        return self._cache

    def _write(self, data: Dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self._cache = data

    def append(self, entry: Dict[str, Any]) -> None:
        """追加一条记录到索引"""
        with self._lock:
            idx = self._read()
            idx["entries"].append(entry)
            idx["total"] = len(idx["entries"])
            idx["updated_at"] = datetime.now().isoformat()
            self._write(idx)

    def get_all(self) -> List[Dict[str, Any]]:
        return self._read().get("entries", [])

    def get_latest(self, n: int = 10) -> List[Dict[str, Any]]:
        return self._read().get("entries", [])[-n:]

    def find_by_tag(self, tag: str) -> List[Dict[str, Any]]:
        return [
            e for e in self._read().get("entries", [])
            if tag in e.get("tags", [])
        ]

    def find_by_agent(self, agent_name: str) -> List[Dict[str, Any]]:
        return [
            e for e in self._read().get("entries", [])
            if e.get("agent_name") == agent_name
        ]

    def get_by_id(self, run_id: str) -> Optional[Dict[str, Any]]:
        for e in self._read().get("entries", []):
            if e.get("run_id") == run_id or e.get("episode_id") == run_id:
                return e
        return None


# ─── ForgeStore ─────────────────────────────────────────────────────────────

class ForgeStore:
    """
    Forge 持久化存储。

    提供线程安全的 Harness 报告、Episode、难度曲线保存接口，
    以及查询和对比功能。

    Usage:
        store = ForgeStore(base_dir=".forge")

        # 保存 Harness 报告
        ref = store.save_harness_report(report, agent_name="OpenClaw-v1")

        # 保存 Episode
        store.save_episode(episode_result)

        # 查询
        recent = store.get_recent_harness(n=5)
        by_agent = store.get_by_agent("Claude Code")
        tagged = store.find_by_tag("advanced")

        # 对比两个报告
        diff = store.compare_reports(report_a, report_b)

        # 导出 benchmark
        store.export_benchmark(["run_001", "run_002"], "comparison.json")
    """

    def __init__(
        self,
        base_dir: str = FORGE_DIR,
        create: bool = True,
    ):
        self._base = Path(base_dir).resolve()
        self._lock = RLock()

        # 子目录
        self._harness_dir = self._base / HARNESS_DIR
        self._episodes_dir = self._base / EPISODES_DIR
        self._curve_dir    = self._base / CURRICULUM_DIR
        self._bench_dir    = self._base / BENCHMARKS_DIR

        # 索引管理器（延迟初始化）
        self._harness_idx: Optional[IndexManager] = None
        self._episodes_idx: Optional[IndexManager] = None

        if create:
            self._ensure_dirs()

    # ── 初始化 ─────────────────────────────────────────────────────────────

    def _ensure_dirs(self) -> None:
        for d in [self._harness_dir, self._episodes_dir,
                  self._curve_dir, self._bench_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # 初始化空索引
        self._harness_idx  # trigger lazy init
        self._episodes_idx

    @property
    def _harness_idx(self) -> IndexManager:
        if self._harness_idx_manager is None:
            self._harness_idx_manager = IndexManager(
                str(self._harness_dir / INDEX_NAME), self._lock
            )
        return self._harness_idx_manager

    @_harness_idx.setter
    def _harness_idx(self, v):
        pass  # property only

    # (lazy init pattern workaround — use explicit method)
    def _get_harness_idx(self) -> IndexManager:
        if self._harness_idx_manager is None:
            self._harness_idx_manager = IndexManager(
                str(self._harness_dir / INDEX_NAME), self._lock
            )
        return self._harness_idx_manager

    # (same for episodes)
    _harness_idx_manager: Optional[IndexManager] = None
    _episodes_idx_manager: Optional[IndexManager] = None

    @property
    def _episodes_idx(self) -> IndexManager:
        if self._episodes_idx_manager is None:
            self._episodes_idx_manager = IndexManager(
                str(self._episodes_dir / INDEX_NAME), self._lock
            )
        return self._episodes_idx_manager

    @_episodes_idx.setter
    def _episodes_idx(self, v):
        pass

    def _get_episodes_idx(self) -> IndexManager:
        if self._episodes_idx_manager is None:
            self._episodes_idx_manager = IndexManager(
                str(self._episodes_dir / INDEX_NAME), self._lock
            )
        return self._episodes_idx_manager

    # ── 路径工具 ───────────────────────────────────────────────────────────

    def _today_dir(self, sub: Path) -> Path:
        """返回当日子目录：sub/YYYY-MM-DD/"""
        today = date.today().strftime("%Y-%m-%d")
        d = sub / today
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _next_run_id(self, sub_dir: Path) -> str:
        """生成下一个 run ID：run_001, run_002, ..."""
        existing = list(sub_dir.glob("run_*.json"))
        n = len(existing) + 1
        return f"run_{n:03d}"

    def _next_episode_id(self) -> str:
        """生成下一个 episode ID：ep_0001, ep_0002, ..."""
        idx = self._get_episodes_idx()
        n = idx._read()["total"] + 1
        return f"ep_{n:04d}"

    # ── 保存 Harness 报告 ─────────────────────────────────────────────────

    def save_harness_report(
        self,
        report: Any,
        agent_name: str = "unknown",
        tags: Optional[List[str]] = None,
        episode_ref: Optional[str] = None,
    ) -> HarnessReportRef:
        """
        保存 Harness 报告。

        写入：
        - harness_reports/YYYY-MM-DD/run_XXX.json   ← 完整报告
        - harness_reports/_index.json               ← 索引追加

        Args:
            report:     HarnessReport 实例
            agent_name: Agent 名称（用于多 Agent 对比）
            tags:       标签（如 ["beginner", "RL-run-3"]）
            episode_ref:关联的 episode ID

        Returns:
            HarnessReportRef：报告的轻量引用
        """
        with self._lock:
            target_dir = self._today_dir(self._harness_dir)
            run_id = self._next_run_id(target_dir)
            file_name = f"{run_id}.json"
            file_path = target_dir / file_name

            # 完整报告写入单独文件
            report_data = self._serialize_report(report)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False)

            # 构建相对路径（相对于 .forge/）
            rel_path = str(file_path.relative_to(self._base))

            # 引用写入索引：summary 从序列化后的 dict 读，避免对象属性遗漏
            ref = HarnessReportRef(
                run_id=run_id,
                timestamp=datetime.now().isoformat(),
                suite_name=report_data.get("suite_name", "unknown"),
                agent_name=agent_name,
                file_path=rel_path,
                summary={
                    "total":       report_data.get("total", 0),
                    "passed":      report_data.get("passed", 0),
                    "pass_rate":   round(report_data.get("pass_rate", 0), 4),
                    "tool_accuracy": round(report_data.get("tool_accuracy", 0), 4),
                    "avg_rfinal":  round(report_data.get("avg_rfinal", 0), 4),
                    "avg_rname":   round(report_data.get("avg_rname", 0), 4),
                    "avg_rparam":  round(report_data.get("avg_rparam", 0), 4),
                    "duration_s":  round(report_data.get("duration", 0), 3),
                },
                tags=tags or [],
                episode_ref=episode_ref,
            )
            self._get_harness_idx().append(asdict(ref))

            logger.info(f"[ForgeStore] Saved harness report: {run_id} → {rel_path}")
            return ref

    def _serialize_report(self, obj: Any) -> Any:
        """将 HarnessReport 序列化为 JSON-safe dict。递归处理嵌套结构。"""
        # 基本类型直接返回（不包装）
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        if isinstance(obj, (list, tuple)):
            return [self._serialize_report(v) for v in obj]
        if isinstance(obj, dict):
            return {k: self._serialize_report(v) for k, v in obj.items()}
        # 对象：优先 to_dict，其次遍历属性
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if hasattr(obj, "__dict__"):
            result = {}
            for k in dir(obj):
                if k.startswith("_"):
                    continue
                try:
                    v = getattr(obj, k)
                    if callable(v):
                        continue
                    if k == "accuracy":
                        k = "tool_accuracy"
                    result[k] = self._serialize_report(v)
                except AttributeError:
                    pass
            return result
        # 兜底
        return str(obj)

    def load_harness_report(self, run_id: str) -> Optional[Dict[str, Any]]:
        """按 run_id 读取完整报告"""
        idx = self._get_harness_idx()
        entry = idx.get_by_id(run_id)
        if not entry:
            return None

        full_path = self._base / entry["file_path"]
        if not full_path.exists():
            logger.warning(f"[ForgeStore] Report file not found: {full_path}")
            return None

        with open(full_path) as f:
            return json.load(f)

    # ── 保存 Episode ───────────────────────────────────────────────────────

    def save_episode(
        self,
        episode: Any,
        harness_ref: Optional[str] = None,
    ) -> EpisodeRef:
        """保存 Episode 结果"""
        with self._lock:
            target_dir = self._today_dir(self._episodes_dir)
            ep_id = self._next_episode_id()
            file_name = f"{ep_id}.json"
            file_path = target_dir / file_name
            rel_path = str(file_path.relative_to(self._base))

            episode_data = self._serialize_episode(episode, ep_id)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(episode_data, f, indent=2, ensure_ascii=False)

            ref = EpisodeRef(
                episode_id=ep_id,
                timestamp=datetime.now().isoformat(),
                stage=episode_data.get("stage", "unknown"),
                keep_rate=episode_data.get("keep_rate", 0.0),
                total_reward=episode_data.get("total_reward", 0.0),
                file_path=rel_path,
                harness_run_ref=harness_ref,
                metadata=episode_data.get("metadata", {}),
            )
            self._get_episodes_idx().append(asdict(ref))

            logger.info(f"[ForgeStore] Saved episode: {ep_id}")
            return ref

    def _serialize_episode(self, episode: Any, ep_id: str) -> Dict[str, Any]:
        """序列化 Episode 到 dict"""
        if hasattr(episode, "to_dict"):
            return episode.to_dict()
        if hasattr(episode, "__dict__"):
            return {k: v for k, v in episode.__dict__.items() if not k.startswith("_")}
        return {"episode_id": ep_id, "raw": str(episode)}

    # ── 保存难度曲线 ────────────────────────────────────────────────────────

    def append_curve_point(
        self,
        stage: str,
        difficulty: float,
        keep_rate: float,
        accuracy: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        追加一个难度曲线数据点到 curriculum_curve/curve.jsonl

        格式：JSON Lines（每行一个 JSON 对象）
        """
        self._curve_dir.mkdir(parents=True, exist_ok=True)
        curve_file = self._curve_dir / "curve.jsonl"

        point = {
            "timestamp": datetime.now().isoformat(),
            "stage": stage,
            "difficulty": round(difficulty, 3),
            "keep_rate": round(keep_rate, 3),
            "accuracy": round(accuracy, 4) if accuracy is not None else None,
            **(metadata or {}),
        }

        with self._lock:
            with open(curve_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(point, ensure_ascii=False) + "\n")

        return curve_file.name

    def load_curve(self) -> List[Dict[str, Any]]:
        """读取完整难度曲线"""
        curve_file = self._curve_dir / "curve.jsonl"
        if not curve_file.exists():
            return []

        points = []
        with open(curve_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        points.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return points

    # ── 查询 ────────────────────────────────────────────────────────────────

    def get_recent_harness(self, n: int = 10) -> List[Dict[str, Any]]:
        """获取最近的 N 条 Harness 记录（从索引，非完整文件）"""
        return self._get_harness_idx().get_latest(n=n)

    def get_recent_episodes(self, n: int = 10) -> List[Dict[str, Any]]:
        return self._get_episodes_idx().get_latest(n=n)

    def find_by_tag(self, tag: str) -> List[Dict[str, Any]]:
        return self._get_harness_idx().find_by_tag(tag)

    def find_by_agent(self, agent_name: str) -> List[Dict[str, Any]]:
        return self._get_harness_idx().find_by_agent(agent_name)

    # ── 对比 ──────────────────────────────────────────────────────────────

    def compare_reports(
        self,
        report_a: Any,
        report_b: Any,
    ) -> Dict[str, Any]:
        """
        对比两个 Harness 报告。

        Returns:
            {
                "metrics": {
                    "tool_accuracy": { "a": 0.8, "b": 0.9, "delta": +0.1 },
                    "pass_rate":      { ... },
                    "avg_rfinal":     { ... },
                    ...
                },
                "winner": "b",
                "summary": "Agent B 在 tool_accuracy 上领先 +10%"
            }
        """
        def s(r, k):
            v = getattr(r, k, None)
            return round(v, 4) if v is not None else None

        metrics = ["tool_accuracy", "pass_rate", "avg_rname", "avg_rparam", "avg_rfinal", "duration"]
        comparison = {}
        a_wins = b_wins = 0

        for m in metrics:
            va = s(report_a, m)
            vb = s(report_b, m)
            delta = round(vb - va, 4) if va is not None and vb is not None else None
            comparison[m] = {"a": va, "b": vb, "delta": delta}
            if delta is not None:
                if delta > 0:
                    b_wins += 1
                elif delta < 0:
                    a_wins += 1

        winner = "a" if a_wins > b_wins else ("b" if b_wins > a_wins else "tie")

        return {
            "metrics": comparison,
            "winner": winner,
            "a_wins": a_wins,
            "b_wins": b_wins,
            "compared_at": datetime.now().isoformat(),
        }

    def export_benchmark(
        self,
        run_ids: List[str],
        output_name: str,
    ) -> str:
        """
        将多个 run_id 导出为一个 benchmark 文件。

        Args:
            run_ids:    harness run ID 列表
            output_name:输出文件名（会自动加上日期前缀）

        Returns:
            输出的绝对路径
        """
        reports = []
        for rid in run_ids:
            r = self.load_harness_report(rid)
            if r:
                r["_run_id"] = rid
                reports.append(r)

        self._bench_dir.mkdir(parents=True, exist_ok=True)
        today = date.today().strftime("%Y-%m-%d")
        out_file = self._bench_dir / f"{today}_{output_name}"

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump({
                "exported_at": datetime.now().isoformat(),
                "run_ids": run_ids,
                "reports": reports,
            }, f, indent=2, ensure_ascii=False)

        logger.info(f"[ForgeStore] Exported benchmark: {out_file}")
        return str(out_file)

    # ── 统计 ──────────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """返回存储统计"""
        h_idx = self._get_harness_idx()._read()
        e_idx = self._get_episodes_idx()._read()
        curve = self.load_curve()

        # 按 Agent 分组统计
        agent_stats: Dict[str, Dict[str, int]] = {}
        for e in h_idx.get("entries", []):
            agent = e.get("agent_name", "unknown")
            if agent not in agent_stats:
                agent_stats[agent] = {"runs": 0, "tags": set()}
            agent_stats[agent]["runs"] += 1
            for tag in e.get("tags", []):
                agent_stats[agent]["tags"].add(tag)

        for a in agent_stats.values():
            a["tags"] = sorted(a["tags"])

        return {
            "harness_reports": h_idx.get("total", 0),
            "episodes": e_idx.get("total", 0),
            "curve_points": len(curve),
            "by_agent": agent_stats,
            "forge_dir": str(self._base),
        }

    def print_stats(self) -> None:
        """打印存储统计（CLI 友好）"""
        s = self.stats()
        print(f"\n{'='*50}")
        print(f"ForgeStore @ {s['forge_dir']}")
        print(f"{'='*50}")
        print(f"  Harness reports:  {s['harness_reports']}")
        print(f"  Episodes:         {s['episodes']}")
        print(f"  Curve points:     {s['curve_points']}")
        if s["by_agent"]:
            print(f"  By agent:")
            for agent, stats in s["by_agent"].items():
                print(f"    {agent}: {stats['runs']} runs  tags={stats['tags']}")
        print(f"{'='*50}")

    # ── 上下文管理器 ──────────────────────────────────────────────────────

    @contextmanager
    def transaction(self):
        """提供写事务（目前就是锁）"""
        with self._lock:
            yield self


# ─── 便捷函数 ────────────────────────────────────────────────────────────────

# 全局默认 store（惰性初始化）
_default_store: Optional[ForgeStore] = None


def get_store(base_dir: str = FORGE_DIR) -> ForgeStore:
    """获取（或创建）全局默认 ForgeStore"""
    global _default_store
    if _default_store is None:
        _default_store = ForgeStore(base_dir=base_dir)
    return _default_store


def save_harness_report(
    report: Any,
    agent_name: str = "unknown",
    tags: Optional[List[str]] = None,
    episode_ref: Optional[str] = None,
    store: Optional[ForgeStore] = None,
) -> HarnessReportRef:
    """便捷函数：保存 Harness 报告"""
    s = store or get_store()
    return s.save_harness_report(report, agent_name, tags, episode_ref)


def save_episode(
    episode: Any,
    harness_ref: Optional[str] = None,
    store: Optional[ForgeStore] = None,
) -> EpisodeRef:
    """便捷函数：保存 Episode"""
    s = store or get_store()
    return s.save_episode(episode, harness_ref)


__all__ = [
    "ForgeStore",
    "HarnessReportRef",
    "EpisodeRef",
    "IndexManager",
    "get_store",
    "save_harness_report",
    "save_episode",
]
