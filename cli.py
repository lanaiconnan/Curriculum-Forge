#!/usr/bin/env python3
"""Curriculum-Forge CLI - 命令行工具

提供查看 program.md、日志和系统状态的接口。
"""

import argparse
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.program_loader import get_program_validator
from shared.time_budget import TimeBudget
from shared.scratchpad import ScratchpadManager
from shared.local_llm import LocalLLMManager, auto_detect_local_llm
from shared.doc_gardening import DocGardeningAgent
from shared.architecture_engine import ArchitectureRuleEngine

# ── MoonClaw Pipeline ──────────────────────────────────────────────────────────
# MoonClaw AdaptiveRuntime + Checkpoint persistence for Curriculum-Forge.
# Phase 1+3: Provider abstraction + Checkpoint persistence.
from pathlib import Path as _Path
from runtimes.checkpoint_store import CheckpointStore
from runtimes.adaptive_runtime import AdaptiveRuntime, PipelineConfig
from providers.curriculum_provider import CurriculumProvider
from providers.harness_provider import HarnessProvider
from providers.memory_provider import MemoryProvider
from providers.review_provider import ReviewProvider


def show_program(agent_type: str):
    """显示指定 Agent 的工作手册"""
    validator = get_program_validator()
    
    try:
        validator.print_summary(agent_type)
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        return 1
    
    return 0


def check_permission(agent_type: str, action: str):
    """检查动作是否允许"""
    validator = get_program_validator()
    
    allowed, reason = validator.validate_action(agent_type, action)
    
    if allowed:
        print(f"✅ {agent_type} can perform: {action}")
        return 0
    else:
        print(f"❌ {agent_type} cannot perform: {action}")
        if reason:
            print(f"   Reason: {reason}")
        return 1


def show_status():
    """显示系统状态"""
    print("\n" + "=" * 60)
    print("Curriculum-Forge System Status")
    print("=" * 60)
    
    # 显示 Agent A
    print("\n[Agent A]")
    show_program("agent_a")
    
    # 显示 Agent B
    print("\n[Agent B]")
    show_program("agent_b")
    
    # 显示 Shared
    print("\n[Shared]")
    show_program("shared")
    
    # 显示时间预算
    print("\n[Time Budget]")
    budget = TimeBudget()
    print(f"   • Experiment: {budget.experiment}s ({budget.experiment / 60:.1f} minutes)")
    print(f"   • Iteration: {budget.iteration}s ({budget.iteration / 60:.1f} minutes)")
    print(f"   • Evaluation: {budget.evaluation}s")
    print(f"   • Overhead: {budget.overhead}s")
    print(f"   • Enabled: {budget.enabled}")
    print(f"   • Timeout policy: {budget.timeout_policy}")
    
    return 0


def show_time_budget():
    """显示时间预算配置"""
    budget = TimeBudget()
    
    print("\n" + "=" * 60)
    print("Time Budget Configuration")
    print("=" * 60)
    
    print(f"\n📊 Time Budget Settings:")
    print(f"   • Experiment: {budget.experiment}s ({budget.experiment / 60:.1f} minutes)")
    print(f"   • Iteration: {budget.iteration}s ({budget.iteration / 60:.1f} minutes)")
    print(f"   • Evaluation: {budget.evaluation}s ({budget.evaluation / 60:.1f} minutes)")
    print(f"   • Overhead: {budget.overhead}s ({budget.overhead / 60:.1f} minutes)")
    
    print(f"\n⚙️ Configuration:")
    print(f"   • Enabled: {budget.enabled}")
    print(f"   • Timeout policy: {budget.timeout_policy}")
    
    print(f"\n💡 Usage:")
    print(f"   # Set custom time budget")
    print(f"   python3 main.py --mode dual --exp-time 600 --iter-time 3600")
    
    return 0


def show_metrics(agent_type: str):
    """显示指标阈值"""
    validator = get_program_validator()
    
    try:
        info = validator.get_info(agent_type)
        
        print(f"\n📊 Metrics for {agent_type}:")
        for metric, threshold in info.metrics.thresholds.items():
            if 'keep_rate' in metric:
                print(f"   • {metric}: >= {threshold:.1%}")
            else:
                print(f"   • {metric}: >= {threshold:.2f}")
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        return 1
    
    return 0


def show_scratchpad_list():
    """列出所有 Scratchpad 日志"""
    manager = ScratchpadManager(base_dir='.scratchpad')
    sessions = manager.list_sessions()
    
    print("\n" + "=" * 60)
    print("Scratchpad Sessions")
    print("=" * 60)
    
    if not sessions:
        print("\n⚠️ No scratchpad sessions found")
        print("   Run training with Scratchpad enabled to create sessions")
        return 0
    
    print(f"\n📝 Found {len(sessions)} sessions:\n")
    
    for i, session in enumerate(sessions, 1):
        # 加载并显示摘要
        try:
            scratchpad = manager.load(session)
            scratchpad.print_summary()
            print()
        except Exception as e:
            print(f"   {i}. {session} - Error: {e}")
    
    return 0


def show_scratchpad_session(filename: str = None):
    """显示指定 Scratchpad 会话"""
    manager = ScratchpadManager(base_dir='.scratchpad')
    
    # 如果没有指定文件名，显示最新的
    if filename is None:
        sessions = manager.list_sessions()
        if not sessions:
            print("❌ No scratchpad sessions found")
            return 1
        filename = sessions[0]
    
    try:
        scratchpad = manager.load(filename)
        
        print("\n" + "=" * 60)
        print(f"Scratchpad Session: {scratchpad.session_id}")
        print("=" * 60)
        
        # 显示摘要
        scratchpad.print_summary()
        
        # 显示思考
        scratchpad.print_thinkings()
        
        # 显示工具调用
        scratchpad.print_tool_calls()
        
        return 0
    except FileNotFoundError:
        print(f"❌ Scratchpad session not found: {filename}")
        return 1
    except Exception as e:
        print(f"❌ Error loading scratchpad: {e}")
        return 1


def show_scratchpad_filtered(filename: str, entry_type: str):
    """显示指定类型的日志"""
    manager = ScratchpadManager(base_dir='.scratchpad')
    
    # 如果没有指定文件名，使用最新的
    if filename is None:
        sessions = manager.list_sessions()
        if not sessions:
            print("❌ No scratchpad sessions found")
            return 1
        filename = sessions[0]
    
    try:
        scratchpad = manager.load(filename)
        
        print("\n" + "=" * 60)
        print(f"Scratchpad: {scratchpad.session_id} [{entry_type}]")
        print("=" * 60)
        
        entries = scratchpad.get_entries(entry_type)
        
        if not entries:
            print(f"\n⚠️ No {entry_type} entries found")
            return 0
        
        print(f"\n📝 Found {len(entries)} {entry_type} entries:\n")
        
        for i, entry in enumerate(entries, 1):
            print(f"   {i}. [{entry.timestamp}]")
            for key, value in entry.data.items():
                if value is not None:
                    if isinstance(value, dict):
                        print(f"      {key}: {value}")
                    elif isinstance(value, list):
                        print(f"      {key}: {value}")
                    else:
                        print(f"      {key}: {value}")
            print()
        
        return 0
    except FileNotFoundError:
        print(f"❌ Scratchpad session not found: {filename}")
        return 1
    except Exception as e:
        print(f"❌ Error loading scratchpad: {e}")
        return 1


def show_verification_stats():
    """显示验证统计"""
    print("\n" + "=" * 60)
    print("Verification Statistics")
    print("=" * 60)
    
    try:
        from rl.self_verifier import ConfidenceTracker
        from rl.enhanced_reward_calculator import EnhancedRewardCalculator
        
        print("\n📊 Verification Modules:")
        print("   • SelfVerifier: Available")
        print("   • ConfidenceTracker: Available")
        print("   • EnhancedRewardCalculator: Available")
        
        print("\n💡 Usage in code:")
        print("""
from rl.self_verifier import SelfVerifier, ConfidenceTracker
from rl.enhanced_reward_calculator import EnhancedRewardCalculator

# 创建实例
verifier = SelfVerifier()
tracker = ConfidenceTracker(window_size=10)
calculator = EnhancedRewardCalculator()

# 使用
reward = calculator.calculate(trajectory)
tracker.add(reward.verification.confidence)

# 获取统计
print(tracker.get_summary())
        """)
        
        return 0
    except ImportError as e:
        print(f"\n⚠️ Verification modules not available: {e}")
        return 1


def show_llm_status():
    """显示本地 LLM 状态"""
    print("\n" + "=" * 60)
    print("Local LLM Status")
    print("=" * 60)
    
    manager = LocalLLMManager()
    
    # 自动检测
    print("\n🔍 Auto-detecting local LLM...")
    success, msg = manager.auto_detect()
    
    if success:
        print(f"\n✅ {msg}")
        manager.print_status()
    else:
        print(f"\n⚠️ {msg}")
        
        print("\n💡 Setup instructions:")
        print("\n   Ollama:")
        print("   1. Install: brew install ollama")
        print("   2. Start: ollama serve")
        print("   3. Pull model: ollama pull llama3.2")
        
        print("\n   LM Studio:")
        print("   1. Download from https://lmstudio.ai")
        print("   2. Start LM Studio")
        print("   3. Load a model")
        
        print("\n🔒 Offline mode:")
        print("   Add --offline flag to run with simulated responses")
    
    return 0


def show_doc_garden():
    """显示文档整理状态"""
    print("\n" + "=" * 60)
    print("🌱 DocGardening Status")
    print("=" * 60)
    
    try:
        agent = DocGardeningAgent(workspace='.')
        report = agent.scan()
        agent.print_report(report)
        return 0
    except ImportError as e:
        print(f"\n⚠️ DocGardening module not available: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1


def validate_architecture():
    """验证架构规则"""
    print("\n" + "=" * 60)
    print("🏛️ Architecture Validation")
    print("=" * 60)
    
    try:
        engine = ArchitectureRuleEngine(workspace='.')
        report = engine.validate_all(['.py'])
        engine.print_report(report)
        
        if engine.should_block(report):
            print("\n🚨 架构违规！建议修复后再继续。")
            return 1
        else:
            print("\n✅ 架构检查通过！")
            return 0
    except ImportError as e:
        print(f"\n⚠️ Architecture module not available: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1


def show_confidence():
    """显示置信度追踪"""
    manager = ScratchpadManager(base_dir='.scratchpad')
    sessions = manager.list_sessions()
    
    print("\n" + "=" * 60)
    print("Confidence Tracking")
    print("=" * 60)
    
    if not sessions:
        print("\n⚠️ No scratchpad sessions found")
        return 0
    
    # 尝试加载最新的会话
    try:
        scratchpad = manager.load(sessions[0])
        
        # 查找奖励记录
        reward_entries = scratchpad.get_entries('reward')
        
        if not reward_entries:
            print("\n⚠️ No reward entries found")
            return 0
        
        print(f"\n📊 Found {len(reward_entries)} reward entries")
        
        # 提取置信度
        confidences = []
        for entry in reward_entries:
            verification = entry.data.get('verification', {})
            if verification:
                confidence = verification.get('confidence')
                if confidence is not None:
                    confidences.append(confidence)
        
        if confidences:
            avg_confidence = sum(confidences) / len(confidences)
            print(f"\n📈 Confidence Statistics:")
            print(f"   • Records: {len(confidences)}")
            print(f"   • Average: {avg_confidence:.1%}")
            print(f"   • Min: {min(confidences):.1%}")
            print(f"   • Max: {max(confidences):.1%}")
            
            # 简单趋势分析
            if len(confidences) >= 3:
                recent = confidences[-3:]
                trend = "increasing" if recent[-1] > recent[0] else "decreasing" if recent[-1] < recent[0] else "stable"
                print(f"   • Trend: {trend}")
        else:
            print("\n⚠️ No confidence data found")
        
        return 0
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1


# ── MoonClaw Forge Handlers ───────────────────────────────────────────────────

# Provider name → class mapping
_PROVIDER_REGISTRY = {
    "CurriculumProvider": CurriculumProvider,
    "HarnessProvider": HarnessProvider,
    "MemoryProvider": MemoryProvider,
    "ReviewProvider": ReviewProvider,
}

# Default checkpoint directory
_CHECKPOINT_DIR = _Path.home() / ".curriculum-forge" / "checkpoints"


def _load_profile(profile_name):
    """Load a profile JSON from profiles/ directory."""
    profile_path = _Path(__file__).parent / "profiles" / f"{profile_name}.json"
    if not profile_path.exists():
        print(f"❌ Profile not found: {profile_name}")
        print(f"   Available: rl_controller, pure_harness, progressive_disclosure")
        return None
    import json
    with open(profile_path, "r") as f:
        return json.load(f)


def _build_pipeline_config(profile, args):
    """Build PipelineConfig from profile JSON + CLI overrides."""
    providers = []
    for name in profile.get("providers", []):
        cls = _PROVIDER_REGISTRY.get(name)
        if cls is None:
            print(f"⚠️ Unknown provider: {name}, skipping")
            continue
        providers.append(cls())

    defaults = profile.get("defaults", {})
    runtime_cfg = profile.get("runtime", {})

    interactive = args.interactive or runtime_cfg.get("interactive", False)
    auto_save = not args.no_save

    return PipelineConfig(
        profile=profile["name"],
        providers=providers,
        checkpoint_dir=_CHECKPOINT_DIR,
        auto_save=auto_save,
        interactive=interactive,
    ), defaults


def forge_run(args):
    """Run a MoonClaw Pipeline from a profile."""
    import asyncio

    profile = _load_profile(args.profile)
    if profile is None:
        return 1

    config, defaults = _build_pipeline_config(profile, args)

    # Build run config from defaults + CLI overrides
    run_config = dict(defaults)
    if args.topic:
        run_config["topic"] = args.topic
    if args.difficulty:
        run_config["difficulty"] = args.difficulty

    # Ensure required keys
    if "topic" not in run_config:
        run_config["topic"] = "Python"
    if "difficulty" not in run_config:
        run_config["difficulty"] = "intermediate"

    store = CheckpointStore(base_dir=_CHECKPOINT_DIR)
    rt = AdaptiveRuntime(config=config, checkpoint_store=store)

    if args.resume:
        print(f"🔄 Resuming Checkpoint: {args.resume}")
        try:
            record = asyncio.get_event_loop().run_until_complete(
                rt.resume(args.resume)
            )
        except ValueError as e:
            print(f"❌ {e}")
            return 1
    else:
        print(f"🚀 Running Pipeline: {args.profile}")
        print(f"   Topic: {run_config.get('topic')}")
        print(f"   Difficulty: {run_config.get('difficulty')}")
        print(f"   Providers: {', '.join(p.__class__.__name__ for p in config.providers)}")
        print()
        try:
            record = asyncio.get_event_loop().run_until_complete(
                rt.run(run_config)
            )
        except RuntimeError as e:
            print(f"\n❌ Pipeline failed: {e}")
            return 1

    # Print results
    print(f"\n{'=' * 60}")
    print(f"  Run ID:     {record.id}")
    print(f"  Profile:    {record.profile}")
    print(f"  State:      {record.state.value}")
    print(f"  Providers:  {record.metrics.get('providers_run', '?')} run / "
                f"{record.metrics.get('providers_succeeded', '?')} succeeded")

    if record.state.value == "completed":
        # Show phase summary
        for phase_name, phase_data in record.state_data.items():
            status = phase_data.get("data", {}).get("status", "?")
            print(f"  • {phase_name}: {status}")
    elif record.state.value == "failed":
        error = record.metrics.get("error", "unknown")
        print(f"  Error: {error}")

    print(f"{'=' * 60}")
    return 0


def forge_list(args):
    """List Checkpoint records."""
    store = CheckpointStore(base_dir=_CHECKPOINT_DIR)
    records = store.list(profile=args.profile)

    if not records:
        print("No checkpoints found.")
        return 0

    # Show latest N
    shown = records[:args.limit]
    print(f"\n📋 Checkpoint Records (showing {len(shown)} of {len(records)}):\n")
    print(f"  {'Run ID':<30} {'Profile':<22} {'State':<12} {'Created'}")
    print(f"  {'-' * 30} {'-' * 22} {'-' * 12} {'-' * 20}")
    for r in shown:
        state_str = r.state.value if hasattr(r.state, "value") else str(r.state)
        created = r.created_at[:19] if r.created_at else "?"
        print(f"  {r.id:<30} {r.profile:<22} {state_str:<12} {created}")
    print()
    return 0


def forge_status(args):
    """Show Checkpoint summary statistics."""
    store = CheckpointStore(base_dir=_CHECKPOINT_DIR)
    summary = store.summary()

    if summary["total"] == 0:
        print("No checkpoints found.")
        return 0

    print(f"\n📊 Checkpoint Summary:")
    print(f"   Total runs: {summary['total']}")
    print(f"\n   By Profile:")
    for profile, count in summary.get("by_profile", {}).items():
        print(f"     • {profile}: {count}")
    print(f"\n   By State:")
    for state, count in summary.get("by_state", {}).items():
        print(f"     • {state}: {count}")
    print()
    return 0


def forge_log(args):
    """Show details of a specific Checkpoint run."""
    store = CheckpointStore(base_dir=_CHECKPOINT_DIR)
    record = store.load(args.run_id)

    if record is None:
        print(f"❌ Run not found: {args.run_id}")
        return 1

    import json
    state_str = record.state.value if hasattr(record.state, "value") else str(record.state)

    print(f"\n{'=' * 60}")
    print(f"  Run ID:     {record.id}")
    print(f"  Profile:    {record.profile}")
    print(f"  State:      {state_str}")
    print(f"  Created:    {record.created_at}")
    print(f"  Finished:   {record.finished_at or 'N/A'}")
    print(f"  Config:     {json.dumps(record.config, indent=2)}")
    print(f"\n  Metrics:")
    for k, v in record.metrics.items():
        print(f"    • {k}: {v}")
    print(f"\n  State Data (phases):")
    for phase, data in record.state_data.items():
        phase_status = data.get("data", {}).get("status", "?") if isinstance(data, dict) else "?"
        print(f"    • {phase}: {phase_status}")
    print(f"{'=' * 60}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Curriculum-Forge CLI - View program.md, logs and system status",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show Agent A's program
  python3 cli.py show agent_a
  
  # Show Agent B's program
  python3 cli.py show agent_b
  
  # Check if Agent A can modify a file
  python3 cli.py check agent_a "modify:agent_b/learner.py"
  
  # Show system status
  python3 cli.py status
  
  # Show time budget configuration
  python3 cli.py time-budget
  
  # List all scratchpad sessions
  python3 cli.py log list
  
  # Show latest scratchpad session
  python3 cli.py log show
  
  # Show scratchpad session by filename
  python3 cli.py log show 2026-03-29_120000.jsonl
  
  # Show only thinking entries
  python3 cli.py log thinking
  
  # Show only tool calls
  python3 cli.py log tools
  
  # Show verification statistics
  python3 cli.py verification
  
  # Show confidence tracking
  python3 cli.py confidence
  
  # Show local LLM status
  python3 cli.py llm
  
  # Show doc gardening status
  python3 cli.py garden
  
  # Validate architecture rules
  python3 cli.py arch
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # show 命令
    show_parser = subparsers.add_parser('show', help='Show program.md for an agent')
    show_parser.add_argument('agent', choices=['agent_a', 'agent_b', 'shared'],
                            help='Agent type')
    
    # check 命令
    check_parser = subparsers.add_parser('check', help='Check if an action is allowed')
    check_parser.add_argument('agent', choices=['agent_a', 'agent_b', 'shared'],
                             help='Agent type')
    check_parser.add_argument('action', help='Action to check (e.g., "modify:agent_b/learner.py")')
    
    # status 命令
    subparsers.add_parser('status', help='Show system status')
    
    # time-budget 命令
    subparsers.add_parser('time-budget', help='Show time budget configuration')
    
    # metrics 命令
    metrics_parser = subparsers.add_parser('metrics', help='Show metrics thresholds')
    metrics_parser.add_argument('agent', choices=['agent_a', 'agent_b', 'shared'],
                               help='Agent type')
    
    # verification 命令
    subparsers.add_parser('verification', help='Show verification statistics')
    
    # confidence 命令
    subparsers.add_parser('confidence', help='Show confidence tracking')
    
    # llm 命令
    subparsers.add_parser('llm', help='Show local LLM status')
    
    # garden 命令
    subparsers.add_parser('garden', help='Show doc gardening status')
    
    # arch 命令
    subparsers.add_parser('arch', help='Validate architecture rules')
    
    # log 命令
    log_parser = subparsers.add_parser('log', help='Scratchpad log commands')
    log_subparsers = log_parser.add_subparsers(dest='log_command', help='Log subcommand')
    
    # log list
    log_list_parser = log_subparsers.add_parser('list', help='List all scratchpad sessions')
    
    # log show
    log_show_parser = log_subparsers.add_parser('show', help='Show scratchpad session')
    log_show_parser.add_argument('filename', nargs='?', help='Session filename (optional, defaults to latest)')
    
    # log thinking
    log_thinking_parser = log_subparsers.add_parser('thinking', help='Show thinking entries')
    log_thinking_parser.add_argument('filename', nargs='?', help='Session filename (optional)')
    
    # log tools
    log_tools_parser = log_subparsers.add_parser('tools', help='Show tool call entries')
    log_tools_parser.add_argument('filename', nargs='?', help='Session filename (optional)')

    # ── forge ────────────────────────────────────────────────────────────────────
    # MoonClaw Pipeline commands: run, list, status, log
    forge_parser = subparsers.add_parser('forge', help='MoonClaw Pipeline commands')
    forge_subparsers = forge_parser.add_subparsers(
        dest='forge_command', help='Forge subcommand'
    )

    # forge run
    forge_run_parser = forge_subparsers.add_parser(
        'run',
        help='Run a MoonClaw Pipeline from a profile'
    )
    forge_run_parser.add_argument(
        '--profile', '-p',
        default='rl_controller',
        choices=['rl_controller', 'pure_harness', 'progressive_disclosure'],
        help='Profile to use (default: rl_controller)'
    )
    forge_run_parser.add_argument(
        '--topic', '-t',
        help='Override topic (overrides profile default)'
    )
    forge_run_parser.add_argument(
        '--difficulty', '-d',
        choices=['beginner', 'intermediate', 'advanced', 'expert'],
        help='Override difficulty'
    )
    forge_run_parser.add_argument(
        '--resume', '-r',
        metavar='RUN_ID',
        help='Resume from an existing Checkpoint (run_id)'
    )
    forge_run_parser.add_argument(
        '--interactive', '-i',
        action='store_true',
        help='Enable interactive mode (pause at WaitingForInput)'
    )
    forge_run_parser.add_argument(
        '--no-save',
        action='store_true',
        help='Disable Checkpoint auto-save'
    )

    # forge list
    forge_list_parser = forge_subparsers.add_parser(
        'list', help='List Checkpoint records'
    )
    forge_list_parser.add_argument(
        '--profile', '-p',
        help='Filter by profile'
    )
    forge_list_parser.add_argument(
        '--limit', '-n',
        type=int, default=10,
        help='Max records to show (default: 10)'
    )

    # forge status
    forge_status_parser = forge_subparsers.add_parser(
        'status', help='Show Checkpoint summary statistics'
    )

    # forge log
    forge_log_parser = forge_subparsers.add_parser(
        'log', help='Show details of a specific Checkpoint run'
    )
    forge_log_parser.add_argument('run_id', help='Run ID (e.g. run_20260422_103000)')

    args = parser.parse_args()
    
    if args.command == 'show':
        return show_program(args.agent)
    elif args.command == 'check':
        return check_permission(args.agent, args.action)
    elif args.command == 'status':
        return show_status()
    elif args.command == 'time-budget':
        return show_time_budget()
    elif args.command == 'metrics':
        return show_metrics(args.agent)
    elif args.command == 'llm':
        return show_llm_status()
    elif args.command == 'garden':
        return show_doc_garden()
    elif args.command == 'arch':
        return validate_architecture()
    elif args.command == 'log':
        if args.log_command == 'list':
            return show_scratchpad_list()
        elif args.log_command == 'show':
            return show_scratchpad_session(args.filename)
        elif args.log_command == 'thinking':
            return show_scratchpad_filtered(args.filename, 'thinking')
        elif args.log_command == 'tools':
            return show_scratchpad_filtered(args.filename, 'tool_call')
        else:
            log_parser.print_help()
            return 0
    elif args.command == 'verification':
        return show_verification_stats()
    elif args.command == 'confidence':
        return show_confidence()
    elif args.command == 'forge':
        if args.forge_command == 'run':
            return forge_run(args)
        elif args.forge_command == 'list':
            return forge_list(args)
        elif args.forge_command == 'status':
            return forge_status(args)
        elif args.forge_command == 'log':
            return forge_log(args)
        else:
            forge_parser.print_help()
            return 0
    else:
        parser.print_help()
        return 0


if __name__ == '__main__':
    sys.exit(main())
