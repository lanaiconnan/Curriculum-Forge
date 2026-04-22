"""
External Proposal CLI

支持导入外部 `.proposal.json` 文件创建 Pipeline 运行。
MoonClaw 的 `proposal import` 命令实现。

参考：moonclaw/moonclaw-jobs/src/forge/proposal_cli.ts
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

from providers.base import TaskPhase
from runtimes.checkpoint_store import CheckpointStore, CheckpointRecord
from providers.base import TaskPhase, RunState


# ── Proposal Schema ────────────────────────────────────────────────────────────

PROPOSAL_SCHEMA = {
    "type": "object",
    "required": ["version", "type", "profile"],
    "properties": {
        "version":   {"type": "string"},
        "type":      {"type": "string", "enum": ["curriculum_proposal", "rerun_proposal"]},
        "profile":   {"type": "string"},
        "config":    {"type": "object"},
        "description": {"type": "string"},
        "metadata":  {"type": "object"},
    },
}


def validate_proposal(data: Dict[str, Any]) -> None:
    """验证提案 JSON Schema"""
    if data.get("version") != "1.0":
        raise ValueError(f"Unsupported proposal version: {data.get('version')}")
    if data.get("type") not in ("curriculum_proposal", "rerun_proposal"):
        raise ValueError(f"Invalid proposal type: {data.get('type')}")
    if not data.get("profile"):
        raise ValueError("profile is required")


# ── Proposal Import ────────────────────────────────────────────────────────────

def import_proposal(file_path: str) -> CheckpointRecord:
    """
    导入外部 proposal JSON 文件。
    
    Args:
        file_path: .proposal.json 文件路径
    
    Returns:
        创建的 CheckpointRecord
    
    Raises:
        FileNotFoundError: 文件不存在
        ValueError: JSON 格式错误或 schema 验证失败
    """
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Proposal file not found: {file_path}")
    
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e
    
    validate_proposal(data)
    
    store = CheckpointStore()
    run_id = store.new_id()
    
    if data["type"] == "curriculum_proposal":
        return _create_curriculum_proposal(store, run_id, data)
    elif data["type"] == "rerun_proposal":
        return _create_rerun_proposal(store, run_id, data)
    else:
        raise ValueError(f"Unknown proposal type: {data['type']}")


def _create_curriculum_proposal(
    store: CheckpointStore,
    run_id: str,
    data: Dict,
) -> CheckpointRecord:
    """创建课程提案"""
    from datetime import datetime, timezone
    
    config = data.get("config", {})
    
    # 如果 config 里有 topic，则从该 topic 开始
    # 否则使用默认配置
    initial_phase = TaskPhase.CURRICULUM.value
    
    record = CheckpointRecord(
        id=run_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        profile=data["profile"],
        phase=initial_phase,
        state=RunState.PENDING,
        config=config,
        state_data={},
        metrics={"proposal": True},
        description=data.get("description", ""),
    )
    
    store.save(record)
    return record


def _create_rerun_proposal(
    store: CheckpointStore,
    run_id: str,
    data: Dict,
) -> CheckpointRecord:
    """创建重新运行提案"""
    from datetime import datetime, timezone
    
    original_id = data.get("config", {}).get("resume_from")
    
    if original_id:
        original = store.load(original_id)
        if not original:
            raise ValueError(f"Original checkpoint not found: {original_id}")
    
    record = CheckpointRecord(
        id=run_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        profile=data["profile"],
        phase=TaskPhase.CURRICULUM.value,
        state=RunState.PENDING,
        config=data.get("config", {}),
        state_data={},
        metrics={"rerun": True, "original": original_id},
        description=f"Rerun of {original_id}",
    )
    
    store.save(record)
    return record


# ── CLI Entry Point ────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """
    proposal CLI 入口。
    
    Usage:
        python -m runtimes.proposal_cli import <file.proposal.json>
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Import external proposal JSON into Curriculum-Forge",
    )
    sub = parser.add_subparsers(dest="command")
    
    # import 命令
    imp = sub.add_parser("import", help="Import a .proposal.json file")
    imp.add_argument("file", help="Path to .proposal.json")
    
    # show 命令
    show = sub.add_parser("show", help="Show a proposal JSON template")
    
    args = parser.parse_args(argv)
    
    if args.command == "import":
        try:
            record = import_proposal(args.file)
            print(f"✅ Proposal imported: {record.id}")
            print(f"   Profile: {record.profile}")
            print(f"   Type: {record.description or 'curriculum_proposal'}")
            print(f"   Run with: forge run --resume {record.id}")
            return 0
        except (FileNotFoundError, ValueError) as e:
            print(f"❌ Error: {e}", file=sys.stderr)
            return 1
    
    elif args.command == "show":
        print(json.dumps({
            "version": "1.0",
            "type": "curriculum_proposal",
            "profile": "rl_controller",
            "description": "Train a Python coding agent",
            "config": {
                "topic": "Python Coding Agent",
                "difficulty": "intermediate",
                "goal": "Build an autonomous code reviewer",
            },
        }, indent=2, ensure_ascii=False))
        return 0
    
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
