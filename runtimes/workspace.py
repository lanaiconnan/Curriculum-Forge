"""
Run Workspace — Per-run file system isolation

Each job execution gets its own workspace directory under
~/.curriculum-forge/workspaces/{run_id}/, preventing concurrent
runs from interfering with each other.

Structure:
    workspaces/{run_id}/
    ├── results.tsv      # Experiment results
    ├── scratch/         # Temporary scratch files
    ├── logs/            # Per-run log files
    └── artifacts/       # Output artifacts (reports, models, etc.)
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default base directory for all run workspaces
WORKSPACE_BASE = Path.home() / ".curriculum-forge" / "workspaces"


class RunWorkspace:
    """
    Per-run workspace isolation.

    Provides a dedicated directory tree for each job execution,
    ensuring that concurrent runs do not share or overwrite
    each other's files.

    Usage:
        workspace = RunWorkspace("run_20260423_120000")
        # Pass to services:
        env_config = EnvironmentServiceConfig(workspace=workspace.workspace_path())
        # Access sub-directories:
        workspace.scratch_dir / "temp.json"
        # Cleanup when done:
        workspace.cleanup()
    """

    def __init__(
        self,
        run_id: str,
        base_dir: Optional[Path] = None,
        auto_create: bool = True,
    ):
        self.run_id = run_id
        self._base_dir = (base_dir or WORKSPACE_BASE).resolve()
        self.root = self._base_dir / run_id

        # Sub-directories
        self.scratch_dir = self.root / "scratch"
        self.logs_dir = self.root / "logs"
        self.artifacts_dir = self.root / "artifacts"

        # Convenience: results file
        self.results_file = self.root / "results.tsv"

        if auto_create:
            self.create()

    # ── Directory Management ─────────────────────────────────────────────────

    def create(self) -> None:
        """Create the workspace directory tree."""
        self.root.mkdir(parents=True, exist_ok=True)
        self.scratch_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        self.artifacts_dir.mkdir(exist_ok=True)
        logger.debug(f"RunWorkspace created: {self.root}")

    def cleanup(self) -> None:
        """Remove the entire workspace directory."""
        if self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)
            logger.info(f"RunWorkspace cleaned up: {self.root}")

    def exists(self) -> bool:
        """Check if workspace directory exists."""
        return self.root.exists()

    # ── Path Accessors ───────────────────────────────────────────────────────

    def workspace_path(self) -> str:
        """
        Return root path as string.

        This is the interface for services that accept workspace: str.
        """
        return str(self.root)

    def scratch_path(self, filename: str) -> Path:
        """Get a path in the scratch directory."""
        return self.scratch_dir / filename

    def log_path(self, filename: str) -> Path:
        """Get a path in the logs directory."""
        return self.logs_dir / filename

    def artifact_path(self, filename: str) -> Path:
        """Get a path in the artifacts directory."""
        return self.artifacts_dir / filename

    # ── Disk Usage ───────────────────────────────────────────────────────────

    def disk_usage(self) -> dict:
        """Return disk usage statistics for this workspace."""
        if not self.root.exists():
            return {"exists": False}

        total_size = sum(
            f.stat().st_size for f in self.root.rglob("*") if f.is_file()
        )
        file_count = sum(1 for f in self.root.rglob("*") if f.is_file())
        dir_count = sum(1 for f in self.root.rglob("*") if f.is_dir())

        return {
            "exists": True,
            "root": str(self.root),
            "total_bytes": total_size,
            "file_count": file_count,
            "dir_count": dir_count,
        }

    # ── Serialization ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize workspace info to dict (for CheckpointRecord)."""
        return {
            "run_id": self.run_id,
            "root": str(self.root),
            "exists": self.exists(),
        }

    def __repr__(self) -> str:
        return f"RunWorkspace(run_id={self.run_id!r}, root={self.root!s})"
