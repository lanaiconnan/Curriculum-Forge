"""Unit tests for services/bootstrap.py — Session Bootstrap & State Management

Run: pytest tests/unit/test_bootstrap.py -v
"""

import pytest
import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.bootstrap import (
    SessionStatus,
    SessionMetrics,
    TrainingProgress,
    SessionState,
    SessionBootstrap,
    SessionManager,
)


# ─── SessionMetrics ───────────────────────────────────────────────────────────

class TestSessionMetrics:
    def test_to_dict_and_from_dict(self):
        m = SessionMetrics(
            start_time=1000.0,
            end_time=2000.0,
            total_duration_ms=1000000,
            turn_count=50,
            tool_call_count=100,
            total_tokens=50000,
            total_cost_usd=0.05,
        )
        d = m.to_dict()
        m2 = SessionMetrics.from_dict(d)
        assert m2.start_time == m.start_time
        assert m2.turn_count == m.turn_count
        assert m2.total_cost_usd == m.total_cost_usd

    def test_default_values(self):
        m = SessionMetrics()
        assert m.turn_count == 0
        assert m.total_cost_usd == 0.0


# ─── TrainingProgress ─────────────────────────────────────────────────────────

class TestTrainingProgress:
    def test_to_dict_and_from_dict(self):
        p = TrainingProgress(
            current_episode=50,
            total_episodes=100,
            current_stage="intermediate",
            total_reward=25.5,
            avg_reward=0.51,
            best_reward=0.8,
            experiments_completed=50,
        )
        d = p.to_dict()
        p2 = TrainingProgress.from_dict(d)
        assert p2.current_episode == 50
        assert p2.current_stage == "intermediate"
        assert p2.best_reward == 0.8

    def test_default_values(self):
        p = TrainingProgress()
        assert p.current_episode == 0
        assert p.current_stage == "beginner"


# ─── SessionState ─────────────────────────────────────────────────────────────

class TestSessionState:
    def test_to_dict_and_from_dict(self):
        s = SessionState(
            session_id="test_001",
            project_root="/project",
            cwd="/project",
            status=SessionStatus.RUNNING,
            created_at="2026-04-03 10:00",
            config={"total_episodes": 100},
        )
        d = s.to_dict()
        s2 = SessionState.from_dict(d)
        assert s2.session_id == "test_001"
        assert s2.status == SessionStatus.RUNNING
        assert s2.config["total_episodes"] == 100

    def test_nested_objects(self):
        s = SessionState(
            session_id="test",
            project_root="/p",
            cwd="/p",
            metrics=SessionMetrics(turn_count=10),
            training=TrainingProgress(current_episode=5),
        )
        d = s.to_dict()
        s2 = SessionState.from_dict(d)
        assert s2.metrics.turn_count == 10
        assert s2.training.current_episode == 5


# ─── SessionBootstrap ─────────────────────────────────────────────────────────

class TestSessionBootstrap:
    def test_initialize(self, tmp_path):
        bootstrap = SessionBootstrap(
            project_root=str(tmp_path),
            session_id="test_session_001",
        )
        
        state = bootstrap.initialize(config={"total_episodes": 50})
        
        assert state.session_id == "test_session_001"
        assert state.status == SessionStatus.INITIALIZING
        assert state.training.total_episodes == 50
        assert os.path.exists(bootstrap.current_path)

    def test_save_and_resume_checkpoint(self, tmp_path):
        bootstrap = SessionBootstrap(
            project_root=str(tmp_path),
            session_id="resume_test",
        )
        
        # Initialize and save
        state = bootstrap.initialize(config={"total_episodes": 100})
        state.training.current_episode = 25
        state.status = SessionStatus.RUNNING
        bootstrap.save_checkpoint(state)
        
        # Create new bootstrap instance and resume
        bootstrap2 = SessionBootstrap(
            project_root=str(tmp_path),
            session_id="resume_test",
        )
        resumed = bootstrap2.resume()
        
        assert resumed is not None
        assert resumed.training.current_episode == 25
        assert resumed.status == SessionStatus.RUNNING

    def test_resume_no_checkpoint(self, tmp_path):
        bootstrap = SessionBootstrap(project_root=str(tmp_path))
        result = bootstrap.resume()
        assert result is None

    def test_complete(self, tmp_path):
        bootstrap = SessionBootstrap(
            project_root=str(tmp_path),
            session_id="complete_test",
        )
        
        state = bootstrap.initialize()
        state.metrics.turn_count = 10
        state.training.total_reward = 5.0
        
        archive_path = bootstrap.complete(state)
        
        assert os.path.exists(archive_path)
        assert not os.path.exists(bootstrap.current_path)
        assert "complete_test.json" in archive_path

    def test_complete_updates_metrics(self, tmp_path):
        bootstrap = SessionBootstrap(
            project_root=str(tmp_path),
            session_id="metrics_test",
        )
        
        state = bootstrap.initialize()
        time.sleep(0.1)  # Small delay
        archive_path = bootstrap.complete(state)
        
        with open(archive_path) as f:
            data = json.load(f)
        
        assert data["metrics"]["total_duration_ms"] > 0

    def test_history(self, tmp_path):
        bootstrap = SessionBootstrap(
            project_root=str(tmp_path),
            session_id="history_test",
        )
        
        state = bootstrap.initialize()
        state.training.total_reward = 10.0
        bootstrap.complete(state)
        
        history = bootstrap.get_history()
        assert len(history) == 1
        assert history[0]["session_id"] == "history_test"
        assert history[0]["total_reward"] == 10.0

    def test_multiple_sessions(self, tmp_path):
        bootstrap1 = SessionBootstrap(
            project_root=str(tmp_path),
            session_id="session_1",
        )
        state1 = bootstrap1.initialize()
        bootstrap1.complete(state1)
        
        bootstrap2 = SessionBootstrap(
            project_root=str(tmp_path),
            session_id="session_2",
        )
        state2 = bootstrap2.initialize()
        bootstrap2.complete(state2)
        
        sessions = bootstrap1.list_sessions()
        assert len(sessions) == 2
        ids = {s.session_id for s in sessions}
        assert "session_1" in ids
        assert "session_2" in ids

    def test_get_session(self, tmp_path):
        bootstrap = SessionBootstrap(
            project_root=str(tmp_path),
            session_id="get_test",
        )
        state = bootstrap.initialize()
        state.training.current_episode = 42
        bootstrap.complete(state)
        
        retrieved = bootstrap.get_session("get_test")
        assert retrieved is not None
        assert retrieved.training.current_episode == 42

    def test_get_session_not_found(self, tmp_path):
        bootstrap = SessionBootstrap(project_root=str(tmp_path))
        result = bootstrap.get_session("nonexistent")
        assert result is None

    def test_fail(self, tmp_path):
        bootstrap = SessionBootstrap(
            project_root=str(tmp_path),
            session_id="fail_test",
        )
        state = bootstrap.initialize()
        bootstrap.fail(state, "Something went wrong")
        
        retrieved = bootstrap.get_session("fail_test")
        assert retrieved.status == SessionStatus.FAILED
        assert "Something went wrong" in retrieved.metadata.get("error", "")

    def test_cancel(self, tmp_path):
        bootstrap = SessionBootstrap(
            project_root=str(tmp_path),
            session_id="cancel_test",
        )
        state = bootstrap.initialize()
        bootstrap.cancel(state)
        
        retrieved = bootstrap.get_session("cancel_test")
        assert retrieved.status == SessionStatus.CANCELLED

    def test_cleanup_old_sessions(self, tmp_path):
        bootstrap = SessionBootstrap(
            project_root=str(tmp_path),
            session_id="old_test",
        )
        state = bootstrap.initialize()
        bootstrap.complete(state)
        
        # Manually set old mtime
        archive_path = os.path.join(bootstrap.sessions_dir, "old_test.json")
        old_time = time.time() - 31 * 86400  # 31 days ago
        os.utime(archive_path, (old_time, old_time))
        
        removed = bootstrap.cleanup_old_sessions(max_age_days=30)
        assert removed == 1

    def test_stats(self, tmp_path):
        bootstrap = SessionBootstrap(
            project_root=str(tmp_path),
            session_id="stats_test",
        )
        state = bootstrap.initialize()
        state.training.total_reward = 5.0
        bootstrap.complete(state)
        
        stats = bootstrap.stats()
        assert stats["total_sessions"] == 1
        assert stats["by_status"]["completed"] == 1

    def test_parent_session_lineage(self, tmp_path):
        bootstrap = SessionBootstrap(
            project_root=str(tmp_path),
            session_id="child_session",
        )
        
        state = bootstrap.initialize(
            config={},
            parent_session_id="parent_session",
        )
        
        assert state.parent_session_id == "parent_session"


# ─── SessionManager ───────────────────────────────────────────────────────────

class TestSessionManager:
    def test_start_new(self, tmp_path):
        mgr = SessionManager(str(tmp_path))
        state = mgr.start(config={"total_episodes": 50}, resume=False)
        
        assert state.training.total_episodes == 50
        assert mgr._state is not None

    def test_start_resume(self, tmp_path):
        # First session
        mgr1 = SessionManager(str(tmp_path))
        state1 = mgr1.start(config={"total_episodes": 100}, resume=False)
        state1.training.current_episode = 25
        mgr1.update(state1)
        mgr1.checkpoint()
        
        # Resume
        mgr2 = SessionManager(str(tmp_path))
        state2 = mgr2.start(resume=True)
        
        assert state2.training.current_episode == 25

    def test_auto_checkpoint(self, tmp_path):
        checkpoint_count = [0]
        
        def on_checkpoint(state):
            checkpoint_count[0] += 1
        
        mgr = SessionManager(
            str(tmp_path),
            auto_checkpoint_interval=3,
            on_checkpoint=on_checkpoint,
        )
        
        state = mgr.start(resume=False)
        
        for i in range(10):
            state.training.current_episode = i
            mgr.update(state)
        
        # Should checkpoint at 3, 6, 9
        assert checkpoint_count[0] == 3

    def test_context_manager_success(self, tmp_path):
        complete_count = [0]
        
        def on_complete(state):
            complete_count[0] += 1
        
        with SessionManager(str(tmp_path), on_complete=on_complete) as mgr:
            state = mgr.start(resume=False)
            state.training.current_episode = 10
            mgr.update(state)
        
        # Should checkpoint on exit
        assert complete_count[0] == 0  # Not called, just checkpoint

    def test_context_manager_exception(self, tmp_path):
        try:
            with SessionManager(str(tmp_path)) as mgr:
                state = mgr.start(resume=False)
                state.training.current_episode = 5
                mgr.update(state)
                # Simulate exception
                raise RuntimeError("Test error")
        except RuntimeError:
            pass
        
        # Session should be marked as failed
        bootstrap = SessionBootstrap(str(tmp_path))
        retrieved = bootstrap.get_session(mgr._state.session_id)
        assert retrieved.status == SessionStatus.FAILED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
