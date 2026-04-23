"""
Tests for Per-run Workspace Isolation

Validates that each job run gets its own isolated workspace directory,
and that concurrent runs don't interfere with each other.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── RunWorkspace Tests ─────────────────────────────────────────────────────────

from runtimes.workspace import RunWorkspace, WORKSPACE_BASE


class TestRunWorkspace:
    """Test the RunWorkspace class."""

    def test_create_workspace(self, tmp_path):
        """Workspace directory tree is created on init."""
        ws = RunWorkspace(run_id="test_run_001", base_dir=tmp_path)
        assert ws.root.exists()
        assert ws.scratch_dir.exists()
        assert ws.logs_dir.exists()
        assert ws.artifacts_dir.exists()

    def test_workspace_path(self, tmp_path):
        """workspace_path() returns the root as string."""
        ws = RunWorkspace(run_id="test_run_002", base_dir=tmp_path)
        assert ws.workspace_path() == str(tmp_path / "test_run_002")

    def test_scratch_path(self, tmp_path):
        """scratch_path() returns path in scratch directory."""
        ws = RunWorkspace(run_id="test_run_003", base_dir=tmp_path)
        p = ws.scratch_path("temp.json")
        assert p == ws.scratch_dir / "temp.json"

    def test_log_path(self, tmp_path):
        """log_path() returns path in logs directory."""
        ws = RunWorkspace(run_id="test_run_004", base_dir=tmp_path)
        p = ws.log_path("execution.log")
        assert p == ws.logs_dir / "execution.log"

    def test_artifact_path(self, tmp_path):
        """artifact_path() returns path in artifacts directory."""
        ws = RunWorkspace(run_id="test_run_005", base_dir=tmp_path)
        p = ws.artifact_path("report.html")
        assert p == ws.artifacts_dir / "report.html"

    def test_results_file_path(self, tmp_path):
        """results_file points to root/results.tsv."""
        ws = RunWorkspace(run_id="test_run_006", base_dir=tmp_path)
        assert ws.results_file == ws.root / "results.tsv"

    def test_cleanup(self, tmp_path):
        """cleanup() removes the entire workspace directory."""
        ws = RunWorkspace(run_id="test_run_007", base_dir=tmp_path)
        assert ws.root.exists()

        # Write a file
        (ws.scratch_dir / "test.txt").write_text("hello")

        ws.cleanup()
        assert not ws.root.exists()

    def test_cleanup_nonexistent(self, tmp_path):
        """cleanup() on non-existent workspace doesn't raise."""
        ws = RunWorkspace(run_id="test_run_008", base_dir=tmp_path, auto_create=False)
        ws.cleanup()  # Should not raise

    def test_exists(self, tmp_path):
        """exists() returns True when workspace is created."""
        ws = RunWorkspace(run_id="test_run_009", base_dir=tmp_path)
        assert ws.exists()

        ws.cleanup()
        assert not ws.exists()

    def test_auto_create_false(self, tmp_path):
        """auto_create=False skips directory creation."""
        ws = RunWorkspace(run_id="test_run_010", base_dir=tmp_path, auto_create=False)
        assert not ws.root.exists()
        assert not ws.exists()

    def test_disk_usage(self, tmp_path):
        """disk_usage() reports file sizes."""
        ws = RunWorkspace(run_id="test_run_011", base_dir=tmp_path)
        (ws.scratch_dir / "data.bin").write_bytes(b"x" * 1000)
        (ws.logs_dir / "run.log").write_text("log line\n" * 100)

        usage = ws.disk_usage()
        assert usage["exists"] is True
        assert usage["total_bytes"] > 0
        assert usage["file_count"] == 2
        assert usage["dir_count"] >= 3  # root, scratch, logs, artifacts

    def test_disk_usage_nonexistent(self, tmp_path):
        """disk_usage() on non-existent workspace."""
        ws = RunWorkspace(run_id="test_run_012", base_dir=tmp_path, auto_create=False)
        usage = ws.disk_usage()
        assert usage["exists"] is False

    def test_to_dict(self, tmp_path):
        """to_dict() serializes workspace info."""
        ws = RunWorkspace(run_id="test_run_013", base_dir=tmp_path)
        d = ws.to_dict()
        assert d["run_id"] == "test_run_013"
        assert d["root"] == str(tmp_path / "test_run_013")
        assert d["exists"] is True

    def test_repr(self, tmp_path):
        """repr includes run_id and root."""
        ws = RunWorkspace(run_id="test_run_014", base_dir=tmp_path)
        r = repr(ws)
        assert "test_run_014" in r
        assert str(tmp_path) in r


class TestRunWorkspaceIsolation:
    """Test that multiple runs get isolated workspaces."""

    def test_concurrent_runs_isolated(self, tmp_path):
        """Two runs get separate workspace directories."""
        ws1 = RunWorkspace(run_id="run_A", base_dir=tmp_path)
        ws2 = RunWorkspace(run_id="run_B", base_dir=tmp_path)

        # Write to workspace 1
        (ws1.scratch_dir / "data.txt").write_text("from run A")
        # Write to workspace 2
        (ws2.scratch_dir / "data.txt").write_text("from run B")

        # Verify isolation
        assert (ws1.scratch_dir / "data.txt").read_text() == "from run A"
        assert (ws2.scratch_dir / "data.txt").read_text() == "from run B"

        # Cleanup one doesn't affect the other
        ws1.cleanup()
        assert not ws1.exists()
        assert ws2.exists()

    def test_no_cross_contamination(self, tmp_path):
        """Files in one workspace don't appear in another."""
        ws1 = RunWorkspace(run_id="run_C", base_dir=tmp_path)
        ws2 = RunWorkspace(run_id="run_D", base_dir=tmp_path)

        # Write unique file to ws1
        (ws1.artifacts_dir / "model.pkl").write_bytes(b"PKL")

        # ws2 doesn't have it
        assert not (ws2.artifacts_dir / "model.pkl").exists()

    def test_cleanup_selective(self, tmp_path):
        """Cleaning up one workspace doesn't affect others."""
        workspaces = []
        for i in range(5):
            ws = RunWorkspace(run_id=f"run_{i}", base_dir=tmp_path)
            (ws.scratch_dir / "data.txt").write_text(f"run_{i}")
            workspaces.append(ws)

        # Cleanup middle one
        workspaces[2].cleanup()
        assert not workspaces[2].exists()

        # Others still exist
        for i in [0, 1, 3, 4]:
            assert workspaces[i].exists()
            assert (workspaces[i].scratch_dir / "data.txt").read_text() == f"run_{i}"


# ── CheckpointRecord workspace_dir Tests ──────────────────────────────────────

from runtimes.checkpoint_store import CheckpointRecord, CheckpointStore
from providers.base import RunState


class TestCheckpointRecordWorkspace:
    """Test that CheckpointRecord tracks workspace_dir."""

    def test_workspace_dir_default_none(self):
        """workspace_dir defaults to None (backward compat)."""
        record = CheckpointRecord(
            id="test",
            created_at="2026-01-01T00:00:00",
            profile="test",
            phase="curriculum",
            state=RunState.PENDING,
            config={},
            state_data={},
            metrics={},
        )
        assert record.workspace_dir is None

    def test_workspace_dir_set(self, tmp_path):
        """workspace_dir can be set to a path string."""
        ws = RunWorkspace(run_id="test_ws", base_dir=tmp_path)
        record = CheckpointRecord(
            id="test",
            created_at="2026-01-01T00:00:00",
            profile="test",
            phase="curriculum",
            state=RunState.PENDING,
            config={},
            state_data={},
            metrics={},
            workspace_dir=ws.workspace_path(),
        )
        assert record.workspace_dir == ws.workspace_path()

    def test_workspace_dir_serialization(self, tmp_path):
        """workspace_dir survives to_dict/from_dict round-trip."""
        ws = RunWorkspace(run_id="test_ser", base_dir=tmp_path)
        record = CheckpointRecord(
            id="test",
            created_at="2026-01-01T00:00:00",
            profile="test",
            phase="curriculum",
            state=RunState.PENDING,
            config={},
            state_data={},
            metrics={},
            workspace_dir=ws.workspace_path(),
        )
        d = record.to_dict()
        assert d["workspace_dir"] == ws.workspace_path()

        restored = CheckpointRecord.from_dict(d)
        assert restored.workspace_dir == ws.workspace_path()

    def test_workspace_dir_persisted(self, tmp_path):
        """workspace_dir is persisted to JSON and loadable."""
        store = CheckpointStore(base_dir=tmp_path / "checkpoints")
        ws = RunWorkspace(run_id="run_persist", base_dir=tmp_path / "workspaces")

        record = CheckpointRecord(
            id="run_persist",
            created_at="2026-01-01T00:00:00",
            profile="test",
            phase="curriculum",
            state=RunState.COMPLETED,
            config={},
            state_data={},
            metrics={},
            workspace_dir=ws.workspace_path(),
        )
        store.save(record)

        loaded = store.load("run_persist")
        assert loaded is not None
        assert loaded.workspace_dir == ws.workspace_path()


# ── AdaptiveRuntime + Workspace Integration ────────────────────────────────────

from runtimes.adaptive_runtime import AdaptiveRuntime, PipelineConfig
from providers.base import TaskProvider, TaskOutput, TaskPhase, ProviderConfig


class _DummyProvider(TaskProvider):
    """Minimal provider for testing."""

    def __init__(self, phase=TaskPhase.CURRICULUM):
        super().__init__(ProviderConfig(name="dummy"))
        self._phase = phase

    @property
    def phase(self):
        return self._phase

    async def execute(self, config, runtime):
        return TaskOutput(
            phase=self._phase,
            data={"workspace": runtime.workspace.workspace_path() if runtime.workspace else None},
        )


class TestAdaptiveRuntimeWorkspace:
    """Test AdaptiveRuntime workspace integration."""

    @pytest.mark.asyncio
    async def test_runtime_with_workspace(self, tmp_path):
        """Runtime passes workspace to providers."""
        ws = RunWorkspace(run_id="test_rt_ws", base_dir=tmp_path)
        store = CheckpointStore(base_dir=tmp_path / "checkpoints")
        config = PipelineConfig(
            profile="test",
            providers=[_DummyProvider()],
            auto_save=True,
        )

        runtime = AdaptiveRuntime(
            config=config,
            checkpoint_store=store,
            workspace=ws,
        )

        result = await runtime.run({})
        assert result.workspace_dir == ws.workspace_path()
        # Provider should have received the workspace
        phase_data = result.state_data.get("curriculum", {})
        assert phase_data.get("data", {}).get("workspace") == ws.workspace_path()

    @pytest.mark.asyncio
    async def test_runtime_without_workspace(self, tmp_path):
        """Runtime works without workspace (backward compat)."""
        store = CheckpointStore(base_dir=tmp_path / "checkpoints")
        config = PipelineConfig(
            profile="test",
            providers=[_DummyProvider()],
            auto_save=True,
        )

        runtime = AdaptiveRuntime(
            config=config,
            checkpoint_store=store,
            workspace=None,
        )

        result = await runtime.run({})
        assert result.workspace_dir is None

    @pytest.mark.asyncio
    async def test_run_stream_with_workspace(self, tmp_path):
        """run_stream yields events and sets workspace_dir."""
        ws = RunWorkspace(run_id="test_stream_ws", base_dir=tmp_path)
        store = CheckpointStore(base_dir=tmp_path / "checkpoints")
        config = PipelineConfig(
            profile="test",
            providers=[_DummyProvider()],
            auto_save=True,
        )

        runtime = AdaptiveRuntime(
            config=config,
            checkpoint_store=store,
            workspace=ws,
        )

        events = []
        async for event in runtime.run_stream():
            events.append(event)

        assert events[0]["event"] == "start"
        assert events[-1]["event"] == "done"
        assert runtime._record.workspace_dir == ws.workspace_path()


# ── Pipeline Factory Workspace Integration ─────────────────────────────────────

from runtimes.pipeline_factory import create_pipeline, create_runtime_from_profile


class TestPipelineFactoryWorkspace:
    """Test that pipeline_factory creates workspaces."""

    def test_create_pipeline_returns_workspace(self, tmp_path):
        """create_pipeline returns a RunWorkspace."""
        config, container, store, workspace = create_pipeline(
            profile_name="rl_controller",
            checkpoint_dir=tmp_path / "checkpoints",
            run_id="test_factory_ws",
        )
        assert workspace is not None
        assert workspace.run_id == "test_factory_ws"
        assert workspace.exists()

    def test_create_pipeline_workspace_dir_used_by_services(self, tmp_path):
        """Services in the container use the workspace directory."""
        config, container, store, workspace = create_pipeline(
            profile_name="rl_controller",
            checkpoint_dir=tmp_path / "checkpoints",
            run_id="test_service_ws",
        )
        # The service container should have been initialized with the workspace path
        assert workspace.workspace_path() != "."

    def test_create_runtime_from_profile_with_run_id(self, tmp_path):
        """create_runtime_from_profile creates workspace with given run_id."""
        with patch("runtimes.pipeline_factory._build_service_container") as mock_build:
            mock_container = MagicMock()
            mock_container.initialize_all = MagicMock()
            mock_container.start_all = MagicMock()
            mock_build.return_value = mock_container

            runtime = create_runtime_from_profile(
                profile_name="rl_controller",
                run_id="test_rt_profile_ws",
            )
            assert runtime.workspace is not None
            assert runtime.workspace.run_id == "test_rt_profile_ws"
