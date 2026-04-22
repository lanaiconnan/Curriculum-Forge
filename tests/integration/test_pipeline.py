"""
Integration Tests for MoonClaw Pipeline (AdaptiveRuntime + Providers)

测试 Provider 链的端到端执行，覆盖：
1. 完整 Pipeline 执行（所有 4 个 Provider）
2. Checkpoint 持久化（保存 + 加载）
3. 从 Checkpoint 恢复（跳过已完成阶段）
4. Provider 间 state_data 传递
5. PipelineConfig 不同 provider 组合
6. 失败与异常处理

运行方式：
    cd dual-agent-tool-rl && pytest tests/integration/test_pipeline.py -v
"""

import pytest
import asyncio
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from providers.base import TaskPhase, RunState, TaskOutput
from providers.curriculum_provider import CurriculumProvider
from providers.harness_provider import HarnessProvider
from providers.memory_provider import MemoryProvider
from providers.review_provider import ReviewProvider

from runtimes.checkpoint_store import CheckpointStore, CheckpointRecord
from runtimes.adaptive_runtime import AdaptiveRuntime, PipelineConfig


# ── Python 3.7 AsyncMock Compatibility ────────────────────────────────────────
# AsyncMock was added in Python 3.8. Provide a compatible alternative.


def async_mock(return_value):
    """
    Return an async function that yields/awaits the given return_value.
    Compatible with Python 3.7 (no AsyncMock).
    """
    async def _mock(*args, **kwargs):
        if isinstance(return_value, Exception):
            raise return_value
        return return_value

    return _mock


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_checkpoint_dir():
    """临时 Checkpoint 目录（每个测试独立）"""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def store(temp_checkpoint_dir):
    return CheckpointStore(base_dir=temp_checkpoint_dir)


@pytest.fixture
def all_providers():
    return [
        CurriculumProvider(),
        HarnessProvider(),
        MemoryProvider(),
        ReviewProvider(),
    ]


@pytest.fixture
def config_all(temp_checkpoint_dir, all_providers):
    """完整 Pipeline 配置"""
    return PipelineConfig(
        profile="rl_controller",
        providers=all_providers,
        checkpoint_dir=temp_checkpoint_dir,
        auto_save=True,
        interactive=False,
    )


@pytest.fixture
def runtime(config_all, store):
    return AdaptiveRuntime(config=config_all, checkpoint_store=store)


@pytest.fixture
def config_minimal(temp_checkpoint_dir):
    """仅 CurriculumProvider 的最小配置"""
    return PipelineConfig(
        profile="curriculum_only",
        providers=[CurriculumProvider()],
        checkpoint_dir=temp_checkpoint_dir,
        auto_save=True,
        interactive=False,
    )


@pytest.fixture
def runtime_minimal(config_minimal, store):
    return AdaptiveRuntime(config=config_minimal, checkpoint_store=store)


# ── Test 1: Full Pipeline End-to-End ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_pipeline_runs_all_providers(runtime):
    """
    验证完整 Pipeline（4个 Provider）按顺序执行，
    最终状态为 COMPLETED，所有 state_data 包含 4 个 phase。
    """
    record = await runtime.run({"topic": "Python", "difficulty": "intermediate"})

    assert record.state == RunState.COMPLETED, f"Expected COMPLETED, got {record.state}"
    assert record.profile == "rl_controller"

    # 所有 4 个 phase 都应该出现在 state_data
    phases_in_record = set(record.state_data.keys())
    expected_phases = {TaskPhase.CURRICULUM.value, TaskPhase.HARNESS.value,
                       TaskPhase.MEMORY.value, TaskPhase.REVIEW.value}
    assert expected_phases.issubset(phases_in_record), (
        f"Missing phases: {expected_phases - phases_in_record}"
    )

    # metrics 验证
    assert record.metrics["providers_run"] == 4
    assert record.metrics["providers_succeeded"] == 4
    assert record.metrics["curriculum_modules"] == 3  # beginner/intermediate 默认 3 个模块


# ── Test 2: Checkpoint Persistence ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_checkpoint_saved_to_disk(store, config_all):
    """
    验证 Pipeline 完成后，CheckpointRecord 被正确写入磁盘。
    """
    runtime = AdaptiveRuntime(config=config_all, checkpoint_store=store)
    record = await runtime.run({"topic": "Rust", "difficulty": "advanced"})

    # 重新从磁盘加载
    loaded = store.load(record.id)
    assert loaded is not None, f"Checkpoint file not found for run {record.id}"
    assert loaded.id == record.id
    assert loaded.state == RunState.COMPLETED
    assert loaded.profile == "rl_controller"
    assert TaskPhase.CURRICULUM.value in loaded.state_data


@pytest.mark.asyncio
async def test_checkpoint_record_roundtrip_serialization(temp_checkpoint_dir):
    """
    验证 CheckpointRecord.to_dict() / from_dict() 往返序列化正确。
    特别测试 RunState enum 的序列化/反序列化。
    """
    from providers.base import RunState
    from runtimes.checkpoint_store import CheckpointRecord

    record = CheckpointRecord(
        id="run_test_001",
        created_at="2026-04-22T10:00:00+00:00",
        profile="test",
        phase=TaskPhase.HARNESS.value,
        state=RunState.RUNNING,
        config={"topic": "Go"},
        state_data={"curriculum": {"phase": "curriculum"}},
        metrics={"providers_run": 1, "providers_succeeded": 1},
        finished_at=None,
    )

    # roundtrip
    d = record.to_dict()
    loaded = CheckpointRecord.from_dict(d)

    assert loaded.id == record.id
    assert loaded.state == RunState.RUNNING          # enum 反序列化
    assert loaded.state != "RUNNING"                 # 不是字符串
    assert loaded.profile == "test"
    assert loaded.state_data == record.state_data


# ── Test 3: Resume from Checkpoint ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_resume_skips_completed_phases(store, config_all, temp_checkpoint_dir):
    """
    验证 resume() 跳过已完成的 Provider，只执行剩余阶段。
    通过中途中断的 Checkpoint 模拟中断点。
    """
    # 创建已完成 curriculum 的 Checkpoint
    interrupted_record = CheckpointRecord(
        id="run_interrupted_001",
        created_at="2026-04-22T10:00:00+00:00",
        profile="rl_controller",
        phase=TaskPhase.CURRICULUM.value,
        state=RunState.RUNNING,
        config={"topic": "Python"},
        state_data={
            # 只有 curriculum 已完成
            TaskPhase.CURRICULUM.value: {
                "phase": TaskPhase.CURRICULUM.value,
                "data": {
                    "status": "ok",
                    "curriculum": {"topic": "Python", "modules": []},
                },
                "metadata": {},
            }
        },
        metrics={"providers_run": 1, "providers_succeeded": 1},
    )
    store.save(interrupted_record)

    # 从 Checkpoint 恢复
    runtime = AdaptiveRuntime(config=config_all, checkpoint_store=store)
    resumed = await runtime.resume("run_interrupted_001")

    assert resumed.state == RunState.COMPLETED

    # curriculum 已跳过，harness/memory/review 应已执行
    phases_run = set(resumed.state_data.keys())
    assert TaskPhase.HARNESS.value in phases_run
    assert TaskPhase.MEMORY.value in phases_run
    assert TaskPhase.REVIEW.value in phases_run

    # providers_run 应只统计 resume 后新增的（3个）
    assert resumed.metrics["providers_run"] == 4  # 完整运行


@pytest.mark.asyncio
async def test_resume_already_completed_returns_immediately(store, config_all):
    """
    验证 resume() 对已 COMPLETED 的 Checkpoint 直接返回，不报错。
    """
    completed = CheckpointRecord(
        id="run_done_001",
        created_at="2026-04-22T10:00:00+00:00",
        profile="rl_controller",
        phase=TaskPhase.REVIEW.value,
        state=RunState.COMPLETED,
        config={"topic": "Python"},
        state_data={ph.value: {} for ph in TaskPhase},
        metrics={"providers_run": 4, "providers_succeeded": 4},
        finished_at="2026-04-22T10:05:00+00:00",
    )
    store.save(completed)

    runtime = AdaptiveRuntime(config=config_all, checkpoint_store=store)
    result = await runtime.resume("run_done_001")

    assert result.state == RunState.COMPLETED
    assert result.id == "run_done_001"


@pytest.mark.asyncio
async def test_resume_nonexistent_raises(temp_checkpoint_dir):
    """
    验证 resume() 对不存在的 run_id 抛出 ValueError。
    """
    store = CheckpointStore(base_dir=temp_checkpoint_dir)
    runtime = AdaptiveRuntime(
        config=PipelineConfig(
            profile="test",
            providers=[CurriculumProvider()],
            checkpoint_dir=temp_checkpoint_dir,
            auto_save=True,
        ),
        checkpoint_store=store,
    )
    with pytest.raises(ValueError, match="Checkpoint not found"):
        await runtime.resume("nonexistent_run_id")


# ── Test 4: Provider Chain State Data Flow ────────────────────────────────────

@pytest.mark.asyncio
async def test_state_data_flows_between_providers(store, config_all):
    """
    验证 Provider 间 state_data 正确传递：
    HarnessProvider 应能读取 CurriculumProvider 生成的 curriculum modules。
    """
    runtime = AdaptiveRuntime(config=config_all, checkpoint_store=store)
    record = await runtime.run({"topic": "Python", "difficulty": "beginner"})

    # 检查 curriculum 阶段存在且有 modules
    curriculum_data = record.state_data[TaskPhase.CURRICULUM.value]
    assert curriculum_data["data"]["curriculum"]["topic"] == "Python"
    modules = curriculum_data["data"]["curriculum"]["modules"]
    assert len(modules) > 0

    # 检查 harness 阶段存在（基于 curriculum modules 生成）
    harness_data = record.state_data[TaskPhase.HARNESS.value]
    assert "test_report" in harness_data["data"]
    report = harness_data["data"]["test_report"]
    assert report["total"] > 0


@pytest.mark.asyncio
async def test_minimal_pipeline_curriculum_only(runtime_minimal, store):
    """
    验证只有 CurriculumProvider 的最小 Pipeline 能正常运行。
    """
    record = await runtime_minimal.run({"topic": "Haskell"})

    assert record.state == RunState.COMPLETED
    assert TaskPhase.CURRICULUM.value in record.state_data
    assert TaskPhase.HARNESS.value not in record.state_data
    assert record.metrics["providers_run"] == 1
    assert record.metrics["providers_succeeded"] == 1


# ── Test 5: CheckpointStore Operations ──────────────────────────────────────

@pytest.mark.asyncio
async def test_checkpoint_store_list_and_summary(store):
    """
    验证 CheckpointStore.list() 按时间倒序、summary() 统计正确。
    """
    for i in range(3):
        r = CheckpointRecord(
            id=f"run_list_{i:03d}",
            created_at=f"2026-04-22T{10+i:02d}:00:00+00:00",
            profile="test",
            phase=TaskPhase.REVIEW.value,
            state=RunState.COMPLETED,
            config={},
            state_data={},
            metrics={"providers_run": 1, "providers_succeeded": 1},
            finished_at=f"2026-04-22T{10+i:02d}:05:00+00:00",
        )
        store.save(r)
        time.sleep(0.01)  # 确保时间戳不同

    records = store.list()
    assert len(records) == 3
    # 最新（最高时间戳）应在最前
    assert records[0].id == "run_list_002"

    # 按 profile 过滤
    r = CheckpointRecord(
        id="run_list_other",
        created_at="2026-04-22T13:00:00+00:00",
        profile="other_profile",
        phase=TaskPhase.CURRICULUM.value,
        state=RunState.RUNNING,
        config={},
        state_data={},
        metrics={"providers_run": 0, "providers_succeeded": 0},
    )
    store.save(r)
    filtered = store.list(profile="test")
    assert all(rec.profile == "test" for rec in filtered)

    # summary
    summary = store.summary()
    assert summary["total"] == 4
    assert summary["by_profile"]["test"] == 3
    assert summary["by_state"]["completed"] == 3


# ── Test 6: Runtime Status & Metrics ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_runtime_status_property(runtime, store):
    """
    验证 AdaptiveRuntime.status 属性返回正确的运行时信息。
    """
    # 运行前
    assert runtime.status["state"] == "not_started"

    # 运行后
    record = await runtime.run({"topic": "Zig"})
    status = runtime.status

    assert status["run_id"] == record.id
    assert status["state"] == RunState.COMPLETED.value
    assert status["profile"] == "rl_controller"
    assert status["providers_run"] == 4
    assert status["providers_succeeded"] == 4


# ── Test 7: Failure & Exception Handling ─────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_raises_on_provider_failure(temp_checkpoint_dir):
    """
    验证当 Provider.execute() 抛出异常时，Pipeline 状态变为 FAILED，
    Checkpoint 被保存（用于事后分析）。
    """
    failing_provider = CurriculumProvider()
    failing_provider.execute = async_mock(
        RuntimeError("Simulated provider failure")
    )

    config = PipelineConfig(
        profile="failing",
        providers=[failing_provider, HarnessProvider()],
        checkpoint_dir=temp_checkpoint_dir,
        auto_save=True,
        interactive=False,
    )
    store = CheckpointStore(base_dir=temp_checkpoint_dir)
    runtime = AdaptiveRuntime(config=config, checkpoint_store=store)

    with pytest.raises(RuntimeError, match="Pipeline failed"):
        await runtime.run({"topic": "FailLang"})

    # Checkpoint 应保存失败状态
    records = store.list(profile="failing")
    assert len(records) >= 1
    failed_record = records[0]
    assert failed_record.state == RunState.FAILED
    assert "Simulated provider failure" in failed_record.metrics.get("error", "")


# ── Test 8: CheckpointStore Delete ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_checkpoint_delete(store):
    """
    验证 CheckpointStore.delete() 正确删除记录。
    """
    record = CheckpointRecord(
        id="run_delete_test",
        created_at="2026-04-22T10:00:00+00:00",
        profile="test",
        phase=TaskPhase.CURRICULUM.value,
        state=RunState.COMPLETED,
        config={},
        state_data={},
        metrics={"providers_run": 1, "providers_succeeded": 1},
    )
    store.save(record)
    assert store.load("run_delete_test") is not None

    deleted = store.delete("run_delete_test")
    assert deleted is True
    assert store.load("run_delete_test") is None

    # 重复删除应返回 False
    assert store.delete("run_delete_test") is False
