"""
Unit Tests for Provider Layer

测试 providers/ 下的所有模块：
- TaskPhase / RunState 枚举
- TaskProvider 基类
- CurriculumProvider
- HarnessProvider
- MemoryProvider
- ReviewProvider
- ProviderRegistry
"""

import pytest
import asyncio

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from providers.base import (
    TaskPhase,
    RunState,
    TaskOutput,
    TaskProvider,
    ProviderConfig,
    ProviderError,
    ProviderRegistry,
)
from providers.curriculum_provider import CurriculumProvider
from providers.harness_provider import (
    HarnessProvider, HarnessCase, HarnessResult, HarnessReport,
    VERDICT_PASS, VERDICT_FAIL,
)
from providers.memory_provider import MemoryProvider
from providers.review_provider import ReviewProvider
from runtimes import CheckpointRecord, AdaptiveRuntime, PipelineConfig
from runtimes.checkpoint_store import CheckpointStore  # direct import to avoid circular


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_runtime():
    """Mock AdaptiveRuntime for Provider tests"""
    import tempfile
    from pathlib import Path
    
    cp = CurriculumProvider()
    store = CheckpointStore(Path(tempfile.mkdtemp()))
    cfg = PipelineConfig(
        profile="test",
        providers=[cp],
        auto_save=False,
    )
    rt = AdaptiveRuntime(cfg, checkpoint_store=store)
    rt._record = CheckpointRecord(
        id="test_run_001",
        created_at="2026-04-22T00:00:00+00:00",
        profile="test",
        phase=TaskPhase.CURRICULUM.value,
        state=RunState.RUNNING,
        config={},
        state_data={},
        metrics={},
    )
    return rt


# ── TaskPhase / RunState ────────────────────────────────────────────────────────

class TestTaskPhase:
    def test_all_phases_exist(self):
        assert TaskPhase.CURRICULUM.value == "curriculum"
        assert TaskPhase.HARNESS.value    == "harness"
        assert TaskPhase.MEMORY.value     == "memory"
        assert TaskPhase.REVIEW.value     == "review"
    
    def test_phase_order(self):
        """字母序 = 执行顺序 curriculum < harness < memory < review"""
        phases = sorted([TaskPhase.CURRICULUM, TaskPhase.HARNESS,
                         TaskPhase.MEMORY, TaskPhase.REVIEW], key=lambda p: p.value)
        assert [p.value for p in phases] == ["curriculum", "harness", "memory", "review"]


class TestRunState:
    def test_all_states_exist(self):
        assert RunState.PENDING.value    == "pending"
        assert RunState.RUNNING.value   == "running"
        assert RunState.WAITING.value   == "waiting"
        assert RunState.COMPLETED.value == "completed"
        assert RunState.FAILED.value    == "failed"
        assert RunState.CANCELLED.value == "cancelled"


# ── TaskOutput ─────────────────────────────────────────────────────────────────

class TestTaskOutput:
    def test_ok_true(self):
        out = TaskOutput(phase=TaskPhase.CURRICULUM, data={"status": "ok"})
        assert out.ok is True
    
    def test_ok_false(self):
        out = TaskOutput(phase=TaskPhase.HARNESS, data={"status": "error"})
        assert out.ok is False
    
    def test_ok_missing_status(self):
        out = TaskOutput(phase=TaskPhase.MEMORY, data={})
        assert out.ok is True  # 默认 ok
    
    def test_to_dict(self):
        out = TaskOutput(
            phase=TaskPhase.CURRICULUM,
            data={"curriculum": {"modules": [1, 2, 3]}},
            metadata={"waiting": True},
        )
        d = out.to_dict()
        assert d["phase"] == "curriculum"
        assert d["data"] == {"curriculum": {"modules": [1, 2, 3]}}
        assert d["metadata"] == {"waiting": True}


# ── CurriculumProvider ─────────────────────────────────────────────────────────

class TestCurriculumProvider:
    def test_phase(self):
        p = CurriculumProvider()
        assert p.phase == TaskPhase.CURRICULUM
    
    def test_can_handle_with_topic(self):
        p = CurriculumProvider()
        assert p.can_handle({"topic": "Python"}) is True
    
    def test_can_handle_without_topic(self):
        p = CurriculumProvider()
        assert p.can_handle({}) is False
    
    @pytest.mark.asyncio
    async def test_execute_basic(self, mock_runtime):
        p = CurriculumProvider()
        config = {"topic": "Python", "difficulty": "beginner"}
        out = await p.execute(config, mock_runtime)
        
        assert out.ok is True
        assert out.phase == TaskPhase.CURRICULUM
        modules = out.data["curriculum"]["modules"]
        assert len(modules) == 3  # beginner → 3 modules
    
    @pytest.mark.asyncio
    async def test_execute_all_difficulties(self, mock_runtime):
        for diff in ["beginner", "intermediate", "advanced", "expert"]:
            p = CurriculumProvider()
            out = await p.execute({"topic": "Test", "difficulty": diff}, mock_runtime)
            assert out.ok is True, f"Failed on {diff}"
            assert len(out.data["curriculum"]["modules"]) >= 3
    
    def test_validate_config_missing_topic(self):
        p = CurriculumProvider()
        with pytest.raises(ValueError, match="topic is required"):
            p.validate_config({})


# ── HarnessProvider ─────────────────────────────────────────────────────────────

class TestHarnessProvider:
    def test_phase(self):
        p = HarnessProvider()
        assert p.phase == TaskPhase.HARNESS
    
    def test_can_handle_with_modules(self):
        p = HarnessProvider()
        assert p.can_handle({"modules": []}) is True
    
    def test_generate_from_modules(self):
        p = HarnessProvider()
        modules = [
            {
                "id": "mod_1",
                "title": "Basics",
                "lessons": [
                    {"id": "les_1", "title": "Hello World"},
                    {"id": "les_2", "title": "Variables"},
                ]
            }
        ]
        cases = p._generate_from_modules(modules)
        assert len(cases) == 2  # 2 lessons from 1 module
        assert all(isinstance(c, HarnessCase) for c in cases)
    
    @pytest.mark.asyncio
    async def test_execute_with_cases(self, mock_runtime):
        p = HarnessProvider()
        cases = [
            HarnessCase(
                id="test_1",
                prompt="test",
                expected_tool="read_file",
                expected_params={},
            )
        ]
        out = await p.execute({"harness_cases": cases}, mock_runtime)
        assert out.ok is True
        report = out.data["test_report"]
        assert report["total"] == 1


# ── MemoryProvider ──────────────────────────────────────────────────────────────

class TestMemoryProvider:
    def test_phase(self):
        p = MemoryProvider()
        assert p.phase == TaskPhase.MEMORY
    
    def test_extract_from_harness(self):
        p = MemoryProvider()
        harness_data = {
            "data": {
                "test_report": {
                    "results": [
                        {"case_id": "c1", "verdict": "pass"},
                        {"case_id": "c2", "verdict": "fail"},
                    ]
                }
            }
        }
        exps = p._extract_from_harness(harness_data)
        assert len(exps) == 2
        assert exps[0]["type"] == "harness_pass"
        assert exps[1]["type"] == "harness_fail"
    
    def test_extract_from_harness_empty(self):
        p = MemoryProvider()
        assert p._extract_from_harness({}) == []
    
    @pytest.mark.asyncio
    async def test_execute_empty(self, mock_runtime):
        p = MemoryProvider()
        out = await p.execute({}, mock_runtime)
        assert out.ok is True
        assert out.data["memory"]["buffer_size"] >= 0


# ── ReviewProvider ─────────────────────────────────────────────────────────────

class TestReviewProvider:
    def test_phase(self):
        p = ReviewProvider()
        assert p.phase == TaskPhase.REVIEW
    
    def test_judge_pass(self):
        p = ReviewProvider()
        verdict, feedback = p._judge(
            harness_data={
                "data": {"test_report": {"pass_rate": 0.8}}
            },
            memory_data={
                "data": {"memory": {"hit_rate": 0.6}}
            },
            curriculum_data={},
        )
        assert verdict == "pass"
        assert any("✅" in f for f in feedback)
    
    def test_judge_fail(self):
        p = ReviewProvider()
        verdict, feedback = p._judge(
            harness_data={
                "data": {"test_report": {"pass_rate": 0.2}}
            },
            memory_data={},
            curriculum_data={},
        )
        assert verdict == "fail"
    
    @pytest.mark.asyncio
    async def test_execute_with_data(self, mock_runtime):
        p = ReviewProvider()
        mock_runtime._record.state_data["harness"] = {
            "data": {"test_report": {"pass_rate": 0.85}}
        }
        mock_runtime._record.state_data["memory"] = {
            "data": {"memory": {"hit_rate": 0.7}}
        }
        out = await p.execute({}, mock_runtime)
        assert out.ok is True
        assert out.data["verdict"] == "pass"


# ── ProviderRegistry ────────────────────────────────────────────────────────────

class TestProviderRegistry:
    def test_register_and_get(self):
        reg = ProviderRegistry()
        cp = CurriculumProvider()
        reg.register(cp)
        assert reg.get(TaskPhase.CURRICULUM) is cp
        assert reg.get(TaskPhase.HARNESS) is None
    
    def test_list(self):
        reg = ProviderRegistry()
        reg.register(CurriculumProvider())
        reg.register(HarnessProvider())
        reg.register(MemoryProvider())
        reg.register(ReviewProvider())
        providers = reg.list()
        # 按字母序 curriculum < harness < memory < review
        assert [p.phase.value for p in providers] == \
            ["curriculum", "harness", "memory", "review"]
    
    def test_list_by_phase(self):
        reg = ProviderRegistry()
        reg.register(CurriculumProvider())
        providers_by_phase = reg.list_by_phase()
        assert TaskPhase.CURRICULUM in providers_by_phase
        assert len(providers_by_phase) == 1


# ── CheckpointStore ─────────────────────────────────────────────────────────────

class TestCheckpointStore:
    def test_new_id_format(self):
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CheckpointStore(Path(tmpdir))
            run_id = store.new_id()
            assert run_id.startswith("run_")
            assert "_" in run_id
    
    def test_save_and_load(self):
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CheckpointStore(Path(tmpdir))
            record = CheckpointRecord(
                id="test_run_001",
                created_at="2026-04-22T00:00:00+00:00",
                profile="test",
                phase="curriculum",
                state=RunState.RUNNING,
                config={"topic": "test"},
                state_data={},
                metrics={},
            )
            store.save(record)
            
            loaded = store.load("test_run_001")
            assert loaded is not None
            assert loaded.id == "test_run_001"
            assert loaded.profile == "test"
            assert loaded.state == RunState.RUNNING
    
    def test_load_nonexistent(self):
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CheckpointStore(Path(tmpdir))
            assert store.load("nonexistent") is None
    
    def test_delete(self):
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CheckpointStore(Path(tmpdir))
            record = CheckpointRecord(
                id="test_del_001",
                created_at="2026-04-22T00:00:00+00:00",
                profile="test",
                phase="curriculum",
                state=RunState.COMPLETED,
                config={},
                state_data={},
                metrics={},
            )
            store.save(record)
            assert store.delete("test_del_001") is True
            assert store.load("test_del_001") is None
    
    def test_summary(self):
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CheckpointStore(Path(tmpdir))
            summary = store.summary()
            assert summary["total"] >= 0
            assert "by_state" in summary
            assert "storage_dir" in summary


# ── AdaptiveRuntime ─────────────────────────────────────────────────────────────

class TestAdaptiveRuntime:
    @pytest.mark.asyncio
    async def test_run_full_pipeline(self):
        cfg = PipelineConfig(
            profile="test",
            providers=[
                CurriculumProvider(),
                HarnessProvider(),
                MemoryProvider(),
                ReviewProvider(),
            ],
            auto_save=False,
        )
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            rt = AdaptiveRuntime(cfg, checkpoint_store=CheckpointStore(Path(tmpdir)))
            record = await rt.run({"topic": "Python", "difficulty": "beginner"})
            
            assert record.state == RunState.COMPLETED
            assert record.profile == "test"
            assert record.metrics["providers_run"] == 4
            assert record.metrics["providers_succeeded"] == 4
            assert "curriculum" in record.state_data
            assert "harness" in record.state_data
            assert "memory" in record.state_data
            assert "review" in record.state_data
    
    @pytest.mark.asyncio
    async def test_status(self):
        import tempfile
        from pathlib import Path
        store = CheckpointStore(Path(tempfile.mkdtemp()))
        cfg = PipelineConfig(profile="test", providers=[CurriculumProvider()], auto_save=False)
        rt = AdaptiveRuntime(cfg, checkpoint_store=store)
        # 运行前
        assert rt.status["state"] == "not_started"
    
    @pytest.mark.asyncio
    async def test_run_single_provider(self):
        cfg = PipelineConfig(profile="single", providers=[CurriculumProvider()], auto_save=False)
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            rt = AdaptiveRuntime(cfg, checkpoint_store=CheckpointStore(Path(tmpdir)))
            record = await rt.run({"topic": "Go", "difficulty": "advanced"})
            assert record.state == RunState.COMPLETED
            assert record.metrics["providers_run"] == 1


# ── Harness Types ───────────────────────────────────────────────────────────────

class TestHarnessTypes:
    def test_harness_case(self):
        case = HarnessCase(
            id="test_case",
            prompt="test prompt",
            expected_tool="read_file",
            expected_params={"path": "test.py"},
            tags=["unit"],
        )
        assert case.id == "test_case"
        assert case.expected_tool == "read_file"
    
    def test_harness_report(self):
        results = [
            HarnessResult("c1", VERDICT_PASS, "read_file", {}),
            HarnessResult("c2", VERDICT_FAIL, "write_file", {}),
        ]
        report = HarnessReport(total=2, passed=1, failed=1, results=results)
        assert report.total == 2
        assert report.passed == 1
