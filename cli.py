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
    elif args.command == 'llm':
        return show_llm_status()
    else:
        parser.print_help()
        return 0


if __name__ == '__main__':
    sys.exit(main())
