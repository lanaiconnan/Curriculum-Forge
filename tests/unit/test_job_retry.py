"""
Test job retry and error recovery for Curriculum-Forge Gateway.
"""
import pytest
from unittest.mock import patch

from runtimes.checkpoint_store import CheckpointRecord, RunState

# Minimal valid created_at value shared by all test records
_FIXED_TIME = "2026-04-24T00:00:00+00:00"


class TestCheckpointRecordRetryFields:
    """Test CheckpointRecord retry fields are present and sane."""

    def test_retry_fields_exist_with_defaults(self):
        """New record should have retry_count=0 and max_retries=3 by default."""
        record = CheckpointRecord(
            id="run_test_001",
            created_at=_FIXED_TIME,
            profile="rl_controller",
            phase="generate",
            state=RunState.PENDING,
            config={},
            state_data={},
            metrics={},
        )
        assert record.retry_count == 0
        assert record.max_retries == 3

    def test_retry_fields_settable(self):
        """Retry fields should be settable at construction."""
        record = CheckpointRecord(
            id="run_test_002",
            created_at=_FIXED_TIME,
            profile="pure_harness",
            phase="verify",
            state=RunState.RUNNING,
            config={},
            state_data={},
            metrics={},
            retry_count=2,
            max_retries=5,
        )
        assert record.retry_count == 2
        assert record.max_retries == 5

    def test_retry_fields_survive_to_dict_roundtrip(self):
        """retry_count / max_retries should survive to_dict → from_dict."""
        record = CheckpointRecord(
            id="run_test_003",
            created_at=_FIXED_TIME,
            profile="progressive_disclosure",
            phase="generate",
            state=RunState.FAILED,
            config={},
            state_data={},
            metrics={},
            retry_count=1,
            max_retries=3,
        )
        d = record.to_dict()
        restored = CheckpointRecord.from_dict(d)
        assert restored.retry_count == 1
        assert restored.max_retries == 3
        assert restored.state == RunState.FAILED


class TestRetryDecisionLogic:
    """Test retry decision logic (record.retry_count < record.max_retries)."""

    def _make(self, retry_count: int, max_retries: int) -> CheckpointRecord:
        return CheckpointRecord(
            id=f"run_retry_{retry_count}_{max_retries}",
            created_at=_FIXED_TIME,
            profile="rl_controller",
            phase="generate",
            state=RunState.RUNNING,
            config={},
            state_data={},
            metrics={},
            retry_count=retry_count,
            max_retries=max_retries,
        )

    def test_within_limit_retry(self):
        """retry_count < max_retries → should retry."""
        record = self._make(retry_count=1, max_retries=3)
        assert record.retry_count < record.max_retries

    def test_at_limit_no_retry(self):
        """retry_count == max_retries → no more retries."""
        record = self._make(retry_count=3, max_retries=3)
        assert not (record.retry_count < record.max_retries)

    def test_max_retries_zero_disabled(self):
        """max_retries=0 disables retries entirely."""
        record = self._make(retry_count=0, max_retries=0)
        assert not (record.retry_count < record.max_retries)

    def test_retry_count_increments_correctly(self):
        """Simulate multiple failure cycles."""
        record = self._make(retry_count=0, max_retries=2)

        # Cycle 1: fail → retry
        record.retry_count += 1
        assert record.retry_count == 1
        assert record.retry_count < record.max_retries  # → retry

        # Cycle 2: fail → permanent fail
        record.retry_count += 1
        assert record.retry_count == 2
        assert not (record.retry_count < record.max_retries)  # → stop
