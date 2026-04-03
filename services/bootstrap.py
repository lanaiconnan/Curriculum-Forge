"""Session Bootstrap & State Management

Reference: Claude Code src/bootstrap/state.ts

Implements session lifecycle management:
- Session initialization and configuration
- State persistence (checkpoint/resume)
- Session history tracking
- Telemetry and metrics

For Curriculum-Forge:
- Session = one RL training run
- State = training progress, episode count, current stage
- Checkpoint = save training state for resume
- History = past training runs with results

Usage:
    bootstrap = SessionBootstrap(
        project_root="/path/to/project",
        session_id="training_001",
    )

    # Initialize session
    state = bootstrap.initialize()

    # Save checkpoint
    bootstrap.save_checkpoint(state)

    # Resume from checkpoint
    state = bootstrap.resume()

    # Get session history
    history = bootstrap.get_history()
"""

import os
import json
import time
import uuid
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


# ─── Session State ────────────────────────────────────────────────────────────

class SessionStatus(Enum):
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SessionMetrics:
    """Telemetry metrics for a session"""
    start_time: float = 0.0
    end_time: float = 0.0
    total_duration_ms: int = 0
    api_duration_ms: int = 0
    tool_duration_ms: int = 0
    turn_count: int = 0
    tool_call_count: int = 0
    error_count: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_duration_ms": self.total_duration_ms,
            "api_duration_ms": self.api_duration_ms,
            "tool_duration_ms": self.tool_duration_ms,
            "turn_count": self.turn_count,
            "tool_call_count": self.tool_call_count,
            "error_count": self.error_count,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SessionMetrics":
        return cls(**{k: v for k, v in d.items() if hasattr(cls, k)})


@dataclass
class TrainingProgress:
    """RL training specific state"""
    current_episode: int = 0
    total_episodes: int = 100
    current_stage: str = "beginner"  # beginner/intermediate/advanced
    stage_transition_count: int = 0
    total_reward: float = 0.0
    avg_reward: float = 0.0
    best_reward: float = 0.0
    keep_rate: float = 0.0
    experiments_completed: int = 0
    experiments_kept: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_episode": self.current_episode,
            "total_episodes": self.total_episodes,
            "current_stage": self.current_stage,
            "stage_transition_count": self.stage_transition_count,
            "total_reward": self.total_reward,
            "avg_reward": self.avg_reward,
            "best_reward": self.best_reward,
            "keep_rate": self.keep_rate,
            "experiments_completed": self.experiments_completed,
            "experiments_kept": self.experiments_kept,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TrainingProgress":
        return cls(**{k: v for k, v in d.items() if hasattr(cls, k)})


@dataclass
class SessionState:
    """
    Complete session state.

    Mirrors Claude Code's State type:
    - sessionId: unique identifier
    - projectRoot: stable project root
    - cwd: current working directory
    - metrics: telemetry
    - status: lifecycle status

    Extended for Curriculum-Forge:
    - training: RL training progress
    - config: session configuration
    """
    session_id: str
    project_root: str
    cwd: str
    status: SessionStatus = SessionStatus.INITIALIZING
    parent_session_id: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    metrics: SessionMetrics = field(default_factory=SessionMetrics)
    training: TrainingProgress = field(default_factory=TrainingProgress)
    config: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "project_root": self.project_root,
            "cwd": self.cwd,
            "status": self.status.value,
            "parent_session_id": self.parent_session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metrics": self.metrics.to_dict(),
            "training": self.training.to_dict(),
            "config": self.config,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SessionState":
        return cls(
            session_id=d["session_id"],
            project_root=d["project_root"],
            cwd=d["cwd"],
            status=SessionStatus(d.get("status", "initializing")),
            parent_session_id=d.get("parent_session_id"),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            metrics=SessionMetrics.from_dict(d.get("metrics", {})),
            training=TrainingProgress.from_dict(d.get("training", {})),
            config=d.get("config", {}),
            metadata=d.get("metadata", {}),
        )


# ─── Session Bootstrap ───────────────────────────────────────────────────────

class SessionBootstrap:
    """
    Session initialization and state management.

    Responsibilities:
    - Create new sessions with unique IDs
    - Persist session state to disk (checkpoints)
    - Resume from checkpoints
    - Track session history

    Storage layout:
        .claude/
        ├── sessions/
        │   ├── session_001.json      # Completed session
        │   ├── session_002.json
        │   └── current.json          # Active session checkpoint
        └── history.jsonl             # Session history log

    Usage:
        bootstrap = SessionBootstrap(project_root="/path/to/project")

        # Start new session
        state = bootstrap.initialize(config={"total_episodes": 100})

        # ... run training ...

        # Update state
        state.training.current_episode += 1
        bootstrap.update(state)

        # Save checkpoint
        bootstrap.save_checkpoint(state)

        # Complete session
        bootstrap.complete(state)

        # Resume later
        state = bootstrap.resume()
    """

    SESSIONS_DIR = "sessions"
    CURRENT_FILE = "current.json"
    HISTORY_FILE = "history.jsonl"

    def __init__(
        self,
        project_root: str,
        sessions_dir: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        self.project_root = os.path.abspath(project_root)

        # Sessions directory
        if sessions_dir:
            self.sessions_dir = os.path.abspath(sessions_dir)
        else:
            self.sessions_dir = os.path.join(
                self.project_root, ".claude", self.SESSIONS_DIR
            )

        os.makedirs(self.sessions_dir, exist_ok=True)

        # Session ID (generate if not provided)
        self._session_id = session_id or self._generate_session_id()

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def current_path(self) -> str:
        return os.path.join(self.sessions_dir, self.CURRENT_FILE)

    @property
    def history_path(self) -> str:
        return os.path.join(self.sessions_dir, self.HISTORY_FILE)

    # ─── Initialization ─────────────────────────────────────────────────────

    def initialize(
        self,
        config: Optional[Dict[str, Any]] = None,
        parent_session_id: Optional[str] = None,
        cwd: Optional[str] = None,
    ) -> SessionState:
        """
        Initialize a new session.

        Args:
            config: Session configuration (e.g., training params)
            parent_session_id: Parent session for lineage tracking
            cwd: Working directory (defaults to project_root)

        Returns:
            Initialized SessionState
        """
        now = time.strftime("%Y-%m-%d %H:%M:%S")

        state = SessionState(
            session_id=self._session_id,
            project_root=self.project_root,
            cwd=cwd or self.project_root,
            status=SessionStatus.INITIALIZING,
            parent_session_id=parent_session_id,
            created_at=now,
            updated_at=now,
            config=config or {},
        )

        # Initialize metrics
        state.metrics.start_time = time.time()

        # Initialize training progress from config
        if config:
            if "total_episodes" in config:
                state.training.total_episodes = config["total_episodes"]
            if "initial_stage" in config:
                state.training.current_stage = config["initial_stage"]

        # Save initial checkpoint
        self.save_checkpoint(state)

        logger.info(f"Session initialized: {self._session_id}")
        return state

    def resume(self) -> Optional[SessionState]:
        """
        Resume from the current checkpoint.

        Returns:
            SessionState if checkpoint exists, None otherwise
        """
        if not os.path.exists(self.current_path):
            logger.info("No checkpoint found to resume")
            return None

        try:
            with open(self.current_path, "r") as f:
                data = json.load(f)

            state = SessionState.from_dict(data)
            state.status = SessionStatus.RUNNING
            state.updated_at = time.strftime("%Y-%m-%d %H:%M:%S")

            logger.info(f"Resumed session: {state.session_id}")
            return state

        except Exception as e:
            logger.error(f"Failed to resume session: {e}")
            return None

    # ─── State Updates ──────────────────────────────────────────────────────

    def update(self, state: SessionState) -> None:
        """Update session state (in-memory only, no disk write)"""
        state.updated_at = time.strftime("%Y-%m-%d %H:%M:%S")

    def save_checkpoint(self, state: SessionState) -> str:
        """
        Save session checkpoint to disk.

        Writes to current.json (overwrites any existing checkpoint).

        Returns:
            Path to checkpoint file
        """
        state.updated_at = time.strftime("%Y-%m-%d %H:%M:%S")

        with open(self.current_path, "w") as f:
            json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)

        logger.debug(f"Checkpoint saved: {self.current_path}")
        return self.current_path

    def complete(self, state: SessionState) -> str:
        """
        Mark session as completed and archive it.

        Moves current.json to session_id.json and appends to history.
        Note: If state.status is already FAILED or CANCELLED, those take precedence.

        Returns:
            Path to archived session file
        """
        # Update final metrics
        state.metrics.end_time = time.time()
        state.metrics.total_duration_ms = int(
            (state.metrics.end_time - state.metrics.start_time) * 1000
        )
        # Only set COMPLETED if not already marked as FAILED/CANCELLED
        if state.status not in (SessionStatus.FAILED, SessionStatus.CANCELLED):
            state.status = SessionStatus.COMPLETED
        state.updated_at = time.strftime("%Y-%m-%d %H:%M:%S")

        # Archive session
        archive_path = os.path.join(self.sessions_dir, f"{state.session_id}.json")
        with open(archive_path, "w") as f:
            json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)

        # Append to history
        self._append_history(state)

        # Remove current checkpoint
        if os.path.exists(self.current_path):
            os.remove(self.current_path)

        logger.info(f"Session completed: {state.session_id}")
        return archive_path

    def fail(self, state: SessionState, error: str) -> str:
        """Mark session as failed"""
        state.status = SessionStatus.FAILED
        state.metadata["error"] = error
        return self.complete(state)

    def cancel(self, state: SessionState) -> str:
        """Mark session as cancelled"""
        state.status = SessionStatus.CANCELLED
        return self.complete(state)

    # ─── History ────────────────────────────────────────────────────────────

    def _append_history(self, state: SessionState) -> None:
        """Append session to history log"""
        record = {
            "session_id": state.session_id,
            "status": state.status.value,
            "created_at": state.created_at,
            "duration_ms": state.metrics.total_duration_ms,
            "turn_count": state.metrics.turn_count,
            "total_reward": state.training.total_reward,
            "avg_reward": state.training.avg_reward,
            "experiments_completed": state.training.experiments_completed,
        }

        with open(self.history_path, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get session history (most recent first)"""
        if not os.path.exists(self.history_path):
            return []

        records = []
        with open(self.history_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

        return list(reversed(records[-limit:]))

    def list_sessions(
        self,
        status: Optional[SessionStatus] = None,
        limit: int = 50,
    ) -> List[SessionState]:
        """List archived sessions"""
        sessions = []

        for fname in os.listdir(self.sessions_dir):
            if not fname.endswith(".json") or fname == self.CURRENT_FILE:
                continue

            fpath = os.path.join(self.sessions_dir, fname)
            try:
                with open(fpath, "r") as f:
                    data = json.load(f)
                state = SessionState.from_dict(data)

                if status and state.status != status:
                    continue

                sessions.append(state)
            except Exception:
                pass

        # Sort by created_at descending
        sessions.sort(key=lambda s: s.created_at, reverse=True)
        return sessions[:limit]

    def get_session(self, session_id: str) -> Optional[SessionState]:
        """Get a specific session by ID"""
        fpath = os.path.join(self.sessions_dir, f"{session_id}.json")
        if not os.path.exists(fpath):
            return None

        try:
            with open(fpath, "r") as f:
                data = json.load(f)
            return SessionState.from_dict(data)
        except Exception:
            return None

    # ─── Cleanup ────────────────────────────────────────────────────────────

    def cleanup_old_sessions(self, max_age_days: int = 30) -> int:
        """
        Remove sessions older than max_age_days.

        Returns:
            Number of sessions removed
        """
        removed = 0
        cutoff = time.time() - max_age_days * 86400

        for fname in os.listdir(self.sessions_dir):
            if not fname.endswith(".json") or fname == self.CURRENT_FILE:
                continue

            fpath = os.path.join(self.sessions_dir, fname)
            mtime = os.path.getmtime(fpath)

            if mtime < cutoff:
                os.remove(fpath)
                removed += 1

        logger.info(f"Cleaned up {removed} old sessions")
        return removed

    # ─── Helpers ────────────────────────────────────────────────────────────

    def _generate_session_id(self) -> str:
        """Generate a unique session ID"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        unique = uuid.uuid4().hex[:8]
        return f"session_{timestamp}_{unique}"

    # ─── Stats ──────────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """Get bootstrap statistics"""
        sessions = self.list_sessions()
        history = self.get_history(limit=100)

        total_duration = sum(
            s.metrics.total_duration_ms for s in sessions
        )
        total_reward = sum(
            s.training.total_reward for s in sessions
        )

        return {
            "project_root": self.project_root,
            "sessions_dir": self.sessions_dir,
            "current_session": self._session_id,
            "has_checkpoint": os.path.exists(self.current_path),
            "total_sessions": len(sessions),
            "total_history_entries": len(history),
            "total_duration_ms": total_duration,
            "total_reward": total_reward,
            "by_status": {
                status.value: sum(
                    1 for s in sessions if s.status == status
                )
                for status in SessionStatus
            },
        }


# ─── Session Manager (High-Level API) ────────────────────────────────────────

class SessionManager:
    """
    High-level session management API.

    Combines SessionBootstrap with automatic checkpointing:
    - Auto-save checkpoints every N updates
    - Context manager for automatic cleanup
    - Event hooks for state transitions

    Usage:
        with SessionManager(project_root) as mgr:
            state = mgr.start(config={"total_episodes": 100})

            for episode in range(100):
                # ... run episode ...
                state.training.current_episode = episode + 1
                mgr.update(state)  # Auto-checkpoint every 10 updates
    """

    def __init__(
        self,
        project_root: str,
        auto_checkpoint_interval: int = 10,
        on_checkpoint: Optional[Callable[[SessionState], None]] = None,
        on_complete: Optional[Callable[[SessionState], None]] = None,
    ):
        self.bootstrap = SessionBootstrap(project_root)
        self.auto_checkpoint_interval = auto_checkpoint_interval
        self._update_count = 0
        self._state: Optional[SessionState] = None
        self._on_checkpoint = on_checkpoint
        self._on_complete = on_complete

    def start(
        self,
        config: Optional[Dict[str, Any]] = None,
        resume: bool = True,
    ) -> SessionState:
        """
        Start a new session or resume existing.

        Args:
            config: Session configuration
            resume: If True, try to resume from checkpoint first

        Returns:
            SessionState
        """
        if resume:
            state = self.bootstrap.resume()
            if state:
                self._state = state
                return state

        self._state = self.bootstrap.initialize(config=config)
        return self._state

    def update(self, state: SessionState) -> None:
        """Update state with auto-checkpointing"""
        self._update_count += 1
        self.bootstrap.update(state)

        if self._update_count % self.auto_checkpoint_interval == 0:
            self.bootstrap.save_checkpoint(state)
            if self._on_checkpoint:
                self._on_checkpoint(state)

    def checkpoint(self) -> None:
        """Force checkpoint"""
        if self._state:
            self.bootstrap.save_checkpoint(self._state)
            if self._on_checkpoint:
                self._on_checkpoint(self._state)

    def complete(self) -> str:
        """Complete session"""
        if not self._state:
            raise RuntimeError("No active session")

        result = self.bootstrap.complete(self._state)
        if self._on_complete:
            self._on_complete(self._state)
        return result

    def __enter__(self) -> "SessionManager":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._state:
            if exc_type:
                self.bootstrap.fail(self._state, str(exc_val))
            else:
                self.checkpoint()
