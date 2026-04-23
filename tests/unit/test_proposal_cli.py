"""
Unit Tests for proposal_cli

测试 runtimes/proposal_cli.py：
- validate_proposal()
- import_proposal()
- main() CLI entry point
"""

import json, os, sys, tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from providers.base import RunState, TaskPhase
from runtimes.proposal_cli import validate_proposal, import_proposal, main as proposal_main


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as td:
        yield td


@pytest.fixture
def valid_proposal():
    return {
        "version": "1.0",
        "type": "curriculum_proposal",
        "profile": "rl_controller",
        "description": "Train a coding agent",
        "config": {"topic": "Python", "difficulty": "intermediate"},
    }


@pytest.fixture
def valid_rerun():
    return {
        "version": "1.0",
        "type": "rerun_proposal",
        "profile": "rl_controller",
        "config": {"resume_from": "run_20260101_120000"},
    }


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


# ── validate_proposal() ────────────────────────────────────────────────────────

class TestValidateProposal:
    def test_valid_ok(self, valid_proposal):
        validate_proposal(valid_proposal)  # no raise

    def test_bad_version(self, valid_proposal):
        valid_proposal["version"] = "99.0"
        with pytest.raises(ValueError, match="Unsupported proposal version"):
            validate_proposal(valid_proposal)

    def test_bad_type(self, valid_proposal):
        valid_proposal["type"] = "unknown"
        with pytest.raises(ValueError, match="Invalid proposal type"):
            validate_proposal(valid_proposal)

    def test_missing_profile(self, valid_proposal):
        del valid_proposal["profile"]
        with pytest.raises(ValueError, match="profile is required"):
            validate_proposal(valid_proposal)


# ── import_proposal() ──────────────────────────────────────────────────────────

class TestImportProposal:
    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            import_proposal("/no/such/file.proposal.json")

    def test_bad_json(self, tmp_dir):
        path = os.path.join(tmp_dir, "bad.json")
        with open(path, "w") as f:
            f.write("{ broken")
        with pytest.raises(ValueError, match="Invalid JSON"):
            import_proposal(path)

    def test_bad_version_schema(self, tmp_dir, valid_proposal):
        valid_proposal["version"] = "0.9"
        path = os.path.join(tmp_dir, "p.json")
        write_json(path, valid_proposal)
        with pytest.raises(ValueError, match="Unsupported proposal version"):
            import_proposal(path)

    def test_curriculum_proposal_ok(self, tmp_dir, valid_proposal):
        path = os.path.join(tmp_dir, "curriculum.json")
        write_json(path, valid_proposal)
        record = import_proposal(path)
        assert record is not None
        assert record.profile == "rl_controller"
        assert record.phase == TaskPhase.CURRICULUM.value
        assert record.state == RunState.PENDING
        assert record.config["topic"] == "Python"
        assert record.description == "Train a coding agent"
        assert record.id.startswith("run_")

    def test_curriculum_proposal_serializable(self, tmp_dir, valid_proposal):
        path = os.path.join(tmp_dir, "curriculum.json")
        write_json(path, valid_proposal)
        record = import_proposal(path)
        d = record.to_dict()
        assert d["state"] == "pending"
        assert d["phase"] == "curriculum"
        assert d["profile"] == "rl_controller"

    def test_rerun_proposal_missing_original(self, tmp_dir, valid_rerun):
        """When resume_from checkpoint does not exist, ValueError is raised."""
        path = os.path.join(tmp_dir, "rerun.json")
        write_json(path, valid_rerun)
        with pytest.raises(ValueError, match="Original checkpoint not found"):
            import_proposal(path)


# ── main() CLI ─────────────────────────────────────────────────────────────────

class TestProposalMain:
    def test_show(self):
        assert proposal_main(["show"]) == 0

    def test_import_success(self, tmp_dir, valid_proposal, capsys):
        path = os.path.join(tmp_dir, "curriculum.json")
        write_json(path, valid_proposal)
        assert proposal_main(["import", path]) == 0
        out = capsys.readouterr().out
        assert "Proposal imported" in out
        assert "rl_controller" in out

    def test_import_not_found(self, capsys):
        assert proposal_main(["import", "/no/such/file.json"]) == 1
        assert "Error" in capsys.readouterr().err

    def test_import_bad_json(self, tmp_dir, capsys):
        path = os.path.join(tmp_dir, "bad.json")
        with open(path, "w") as f:
            f.write("{ broken")
        assert proposal_main(["import", path]) == 1
        assert "Error" in capsys.readouterr().err

    def test_import_bad_version(self, tmp_dir, valid_proposal, capsys):
        valid_proposal["version"] = "0.8"
        path = os.path.join(tmp_dir, "badver.json")
        write_json(path, valid_proposal)
        assert proposal_main(["import", path]) == 1
        assert "Error" in capsys.readouterr().err

    def test_no_args_shows_help(self, capsys):
        assert proposal_main([]) == 0

    def test_unknown_subcommand(self, capsys):
        with pytest.raises(SystemExit) as exc:
            proposal_main(["unknown"])
        assert exc.value.code == 2
