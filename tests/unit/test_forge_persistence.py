"""测试 Forge Persistence — 持久化层

验证：
1. ForgeStore 目录结构创建
2. Harness 报告保存 + 索引更新
3. Episode 保存 + 索引更新
4. 难度曲线 JSONL 追加
5. 查询：get_recent / find_by_tag / find_by_agent
6. 对比：compare_reports
7. 导出 benchmark
8. 线程安全
9. 序列化容错（无 to_dict 的对象）
"""

import sys, os, tempfile, shutil, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from dataclasses import dataclass

from forge.persistence import (
    ForgeStore,
    HarnessReportRef,
    EpisodeRef,
    IndexManager,
    save_harness_report,
    get_store,
)


# ─── Mock 对象 ───────────────────────────────────────────────────────────────

class MockReport:
    """模拟 HarnessReport（无 to_dict 方法）"""
    def __init__(self, **kwargs):
        self.suite_name = kwargs.get("suite_name", "mock")
        self.total = kwargs.get("total", 10)
        self.passed = kwargs.get("passed", 7)
        self.partial = kwargs.get("partial", 1)
        self.failed = kwargs.get("failed", 2)
        self.skipped = 0
        self.errors = 0
        self.tool_accuracy = kwargs.get("tool_accuracy", 0.80)
        self.avg_rname = kwargs.get("avg_rname", 0.85)
        self.avg_rparam = kwargs.get("avg_rparam", 0.75)
        self.avg_rfinal = kwargs.get("avg_rfinal", 0.70)
        self.pass_rate = kwargs.get("pass_rate", 0.70)
        self.duration = kwargs.get("duration", 1.5)
        self.results = []


class MockEpisode:
    def __init__(self, **kwargs):
        self.episode_id = kwargs.get("episode_id", "ep_0001")
        self.stage = kwargs.get("stage", "beginner")
        self.keep_rate = kwargs.get("keep_rate", 0.65)
        self.total_reward = kwargs.get("total_reward", 0.7)
        self.tasks_completed = 5
        self.metadata = {}


# ─── Fixture ────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_forge(tmp_path):
    """临时 ForgeStore"""
    store = ForgeStore(base_dir=str(tmp_path / ".forge"))
    return store


# ─── 目录结构测试 ─────────────────────────────────────────────────────────────

class TestForgeStoreInit:
    def test_creates_all_subdirs(self, tmp_path):
        store = ForgeStore(base_dir=str(tmp_path / ".forge"))
        assert (tmp_path / ".forge" / "harness_reports").exists()
        assert (tmp_path / ".forge" / "episodes").exists()
        assert (tmp_path / ".forge" / "curriculum_curve").exists()
        assert (tmp_path / ".forge" / "benchmarks").exists()

    def test_no_create_flag(self, tmp_path):
        store = ForgeStore(base_dir=str(tmp_path / ".forge_no_create"), create=False)
        assert not (tmp_path / ".forge_no_create").exists()

    def test_default_forge_dir(self):
        store = ForgeStore(base_dir=".forge_test_default")
        assert store._base.name == ".forge_test_default"
        shutil.rmtree(str(store._base), ignore_errors=True)


# ─── IndexManager 测试 ───────────────────────────────────────────────────────

class TestIndexManager:
    def test_append_and_read(self, tmp_path):
        idx_path = tmp_path / "_index.json"
        idx = IndexManager(str(idx_path))

        idx.append({"run_id": "run_001", "accuracy": 0.8})
        idx.append({"run_id": "run_002", "accuracy": 0.9})

        all_entries = idx.get_all()
        assert len(all_entries) == 2
        assert all_entries[0]["run_id"] == "run_001"

    def test_get_latest(self, tmp_path):
        idx_path = tmp_path / "_index.json"
        idx = IndexManager(str(idx_path))

        for i in range(20):
            idx.append({"run_id": f"run_{i:03d}"})

        latest = idx.get_latest(n=5)
        assert len(latest) == 5
        assert latest[-1]["run_id"] == "run_019"

    def test_find_by_tag(self, tmp_path):
        idx_path = tmp_path / "_index.json"
        idx = IndexManager(str(idx_path))

        idx.append({"run_id": "r1", "tags": ["beginner"]})
        idx.append({"run_id": "r2", "tags": ["advanced"]})
        idx.append({"run_id": "r3", "tags": ["beginner", "rl"]})

        assert len(idx.find_by_tag("beginner")) == 2
        assert len(idx.find_by_tag("advanced")) == 1
        assert len(idx.find_by_tag("rl")) == 1

    def test_find_by_agent(self, tmp_path):
        idx_path = tmp_path / "_index.json"
        idx = IndexManager(str(idx_path))

        idx.append({"run_id": "r1", "agent_name": "OpenClaw"})
        idx.append({"run_id": "r2", "agent_name": "Claude Code"})
        idx.append({"run_id": "r3", "agent_name": "OpenClaw"})

        assert len(idx.find_by_agent("OpenClaw")) == 2
        assert len(idx.find_by_agent("Claude Code")) == 1

    def test_get_by_id(self, tmp_path):
        idx_path = tmp_path / "_index.json"
        idx = IndexManager(str(idx_path))

        idx.append({"run_id": "run_005", "accuracy": 0.5})
        assert idx.get_by_id("run_005")["accuracy"] == 0.5
        assert idx.get_by_id("nonexistent") is None


# ─── 保存 Harness 报告 ───────────────────────────────────────────────────────

class TestSaveHarnessReport:
    def test_saves_full_report(self, tmp_forge):
        report = MockReport(passed=8, total=10, tool_accuracy=0.85)
        ref = tmp_forge.save_harness_report(report, agent_name="TestAgent")

        assert ref.run_id == "run_001"
        assert ref.agent_name == "TestAgent"
        assert ref.summary["passed"] == 8
        assert ref.summary["total"] == 10

    def test_saves_to_date_subdir(self, tmp_forge):
        report = MockReport()
        ref = tmp_forge.save_harness_report(report)

        # 验证文件在 YYYY-MM-DD 子目录下
        import datetime
        today = datetime.date.today().strftime("%Y-%m-%d")
        expected = tmp_forge._base / "harness_reports" / today / "run_001.json"
        assert expected.exists()

    def test_incremental_run_ids(self, tmp_forge):
        report = MockReport()
        ids = []
        for _ in range(5):
            ref = tmp_forge.save_harness_report(report)
            ids.append(ref.run_id)

        assert ids == ["run_001", "run_002", "run_003", "run_004", "run_005"]

    def test_tags_in_index(self, tmp_forge):
        report = MockReport()
        ref = tmp_forge.save_harness_report(report, tags=["beginner", "rl"])
        assert ref.tags == ["beginner", "rl"]

        # 索引中也应有 tags
        idx = tmp_forge._get_harness_idx()
        entry = idx.get_by_id("run_001")
        assert entry["tags"] == ["beginner", "rl"]

    def test_episode_ref(self, tmp_forge):
        report = MockReport()
        ref = tmp_forge.save_harness_report(report, episode_ref="ep_0003")
        assert ref.episode_ref == "ep_0003"

    def test_load_harness_report(self, tmp_forge):
        report = MockReport(passed=9, total=10)
        tmp_forge.save_harness_report(report)

        loaded = tmp_forge.load_harness_report("run_001")
        assert loaded["passed"] == 9
        assert loaded["total"] == 10

    def test_load_nonexistent(self, tmp_forge):
        assert tmp_forge.load_harness_report("nonexistent") is None


# ─── 保存 Episode ─────────────────────────────────────────────────────────────

class TestSaveEpisode:
    def test_save_and_retrieve(self, tmp_forge):
        episode = MockEpisode(keep_rate=0.72, total_reward=0.85)
        ref = tmp_forge.save_episode(episode)

        assert ref.episode_id == "ep_0001"
        assert ref.keep_rate == 0.72
        assert ref.stage == "beginner"

    def test_episode_with_harness_ref(self, tmp_forge):
        episode = MockEpisode()
        ref = tmp_forge.save_episode(episode, harness_ref="run_003")
        assert ref.harness_run_ref == "run_003"

    def test_episode_incremental_ids(self, tmp_forge):
        episode = MockEpisode()
        ids = []
        for _ in range(3):
            ref = tmp_forge.save_episode(episode)
            ids.append(ref.episode_id)
        assert ids == ["ep_0001", "ep_0002", "ep_0003"]


# ─── 难度曲线 ────────────────────────────────────────────────────────────────

class TestCurriculumCurve:
    def test_append_curve_point(self, tmp_forge):
        from datetime import date
        filename = tmp_forge.append_curve_point(
            stage="intermediate",
            difficulty=0.55,
            keep_rate=0.70,
            accuracy=0.75,
        )
        assert filename == "curve.jsonl"

        curve = tmp_forge.load_curve()
        assert len(curve) == 1
        assert curve[0]["stage"] == "intermediate"
        assert curve[0]["difficulty"] == 0.55

    def test_append_multiple_points(self, tmp_forge):
        for i in range(5):
            tmp_forge.append_curve_point(
                stage="beginner" if i < 3 else "intermediate",
                difficulty=0.3 + i * 0.05,
                keep_rate=0.5 + i * 0.05,
            )
        curve = tmp_forge.load_curve()
        assert len(curve) == 5

    def test_load_empty_curve(self, tmp_forge):
        assert tmp_forge.load_curve() == []


# ─── 查询 ─────────────────────────────────────────────────────────────────────

class TestQueries:
    def setup_method(self):
        self.reports = [
            MockReport(passed=5, total=10, tool_accuracy=0.5),
            MockReport(passed=8, total=10, tool_accuracy=0.8),
            MockReport(passed=9, total=10, tool_accuracy=0.9),
        ]

    def test_get_recent_harness(self, tmp_forge):
        for r in self.reports:
            tmp_forge.save_harness_report(r)

        recent = tmp_forge.get_recent_harness(n=2)
        assert len(recent) == 2
        assert recent[-1]["summary"]["tool_accuracy"] == 0.9  # 最新

    def test_find_by_tag(self, tmp_forge):
        tmp_forge.save_harness_report(self.reports[0], tags=["beginner"])
        tmp_forge.save_harness_report(self.reports[1], tags=["advanced"])
        tmp_forge.save_harness_report(self.reports[2], tags=["beginner", "rl"])

        assert len(tmp_forge.find_by_tag("beginner")) == 2
        assert len(tmp_forge.find_by_tag("rl")) == 1

    def test_find_by_agent(self, tmp_forge):
        tmp_forge.save_harness_report(self.reports[0], agent_name="OpenClaw")
        tmp_forge.save_harness_report(self.reports[1], agent_name="Claude Code")
        tmp_forge.save_harness_report(self.reports[2], agent_name="OpenClaw")

        assert len(tmp_forge.find_by_agent("OpenClaw")) == 2


# ─── 对比 ───────────────────────────────────────────────────────────────────

class TestCompareReports:
    def test_compare_two_reports(self, tmp_forge):
        report_a = MockReport(
            tool_accuracy=0.80,
            pass_rate=0.70,
            avg_rfinal=0.65,
        )
        report_b = MockReport(
            tool_accuracy=0.90,
            pass_rate=0.85,
            avg_rfinal=0.80,
        )

        diff = tmp_forge.compare_reports(report_a, report_b)

        assert diff["winner"] == "b"
        assert diff["a_wins"] == 0
        assert diff["b_wins"] >= 2
        assert diff["metrics"]["tool_accuracy"]["delta"] == 0.1
        assert diff["metrics"]["pass_rate"]["delta"] == 0.15

    def test_compare_tie(self, tmp_forge):
        r = MockReport(tool_accuracy=0.8, pass_rate=0.7)
        diff = tmp_forge.compare_reports(r, r)
        assert diff["winner"] == "tie"


# ─── 导出 Benchmark ─────────────────────────────────────────────────────────

class TestExportBenchmark:
    def test_export_benchmark(self, tmp_forge):
        for i in range(3):
            r = MockReport(passed=6 + i, total=10)
            tmp_forge.save_harness_report(r)

        out_path = tmp_forge.export_benchmark(
            ["run_001", "run_003"],
            "openclaw_comparison.json",
        )

        import os
        assert os.path.exists(out_path)
        with open(out_path) as f:
            data = json.load(f)
        assert len(data["reports"]) == 2
        assert data["run_ids"] == ["run_001", "run_003"]


# ─── 统计 ──────────────────────────────────────────────────────────────────

class TestStats:
    def test_stats_empty(self, tmp_forge):
        s = tmp_forge.stats()
        assert s["harness_reports"] == 0
        assert s["episodes"] == 0

    def test_stats_populated(self, tmp_forge):
        for _ in range(3):
            tmp_forge.save_harness_report(MockReport(), agent_name="OpenClaw")
        for _ in range(2):
            tmp_forge.save_episode(MockEpisode())
        tmp_forge.append_curve_point("beginner", 0.3, 0.5)

        s = tmp_forge.stats()
        assert s["harness_reports"] == 3
        assert s["episodes"] == 2
        assert s["curve_points"] == 1
        assert "OpenClaw" in s["by_agent"]


# ─── 便捷函数 ─────────────────────────────────────────────────────────────

class TestConvenienceFunctions:
    def test_get_store_default(self, tmp_path, monkeypatch):
        # 切换到临时目录，避免污染真实 .forge
        os.chdir(tmp_path)
        store = get_store()
        assert store._base.name == ".forge"

    def test_save_harness_report_function(self, tmp_path):
        os.chdir(tmp_path)
        report = MockReport(passed=5, total=10)
        ref = save_harness_report(report, agent_name="CLI")
        assert ref.agent_name == "CLI"


# ─── 序列化容错 ─────────────────────────────────────────────────────────────

class TestSerializationFallback:
    def test_report_without_to_dict(self, tmp_forge):
        # 无 to_dict 的对象应安全降级
        class RawReport:
            suite_name = "raw"
            total = 5
            passed = 3
            tool_accuracy = 0.6

        # 不应抛出异常
        ref = tmp_forge.save_harness_report(RawReport(), agent_name="raw")
        assert ref.summary["tool_accuracy"] == 0.6


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
