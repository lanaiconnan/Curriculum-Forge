"""Dual-Agent ToolRL - 主入口（ToolRL 完整训练循环）"""

import argparse
import os
import sys
from datetime import datetime
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_a.generator import AgentA, TrainingEnvironment
from agent_b.learner import AgentB
from rl.trainer import RLTrainer, RLConfig
from shared.results import ResultsLog, ExperimentRecord
from shared.time_budget import TimeBudget, TimeBudgetManager, get_time_budget, set_time_budget
from shared.scratchpad import Scratchpad, ScratchpadManager
from rl.self_verifier import SelfVerifier, ConfidenceTracker, VerificationContext
from rl.enhanced_reward_calculator import EnhancedRewardCalculator
from shared.local_llm import LocalLLMManager, LLMConfig, Provider, auto_detect_local_llm
from shared.doc_gardening import DocGardeningAgent
from shared.architecture_engine import ArchitectureRuleEngine
from tools import create_registry
from tools.memory import MemoryManager


def setup_workspace(ws: str):
    """初始化工作区"""
    os.makedirs(ws, exist_ok=True)
    os.chdir(ws)
    if not os.path.exists(".git"):
        os.system("git init > /dev/null 2>&1")
    return ResultsLog("results.tsv")


def format_trajectory(result: Dict[str, Any]) -> Dict[str, Any]:
    """将实验结果转换为 ToolRL 轨迹格式"""
    return {
        'id': result.get('id', 'unknown'),
        'description': result.get('description', ''),
        'predicted_tools': result.get('tools_used', []),
        'ground_truth_tools': result.get('tools_expected', []),
        'predicted_params': result.get('params_used', {}),
        'ground_truth_params': result.get('params_expected', {}),
        'think': result.get('reasoning', ''),
        'tool_call': result.get('tool_calls', ''),
        'response': result.get('response', ''),
        'think_idx': 0,
        'tool_call_idx': 1,
        'response_idx': 2,
    }


def run_dual_agent_with_toolrl(ws: str, iterations: int = 10, use_grpo: bool = True, 
                                 time_budget: TimeBudget = None, enable_scratchpad: bool = True,
                                 enable_verification: bool = True,
                                 llm_manager: LocalLLMManager = None):
    """
    完整的 ToolRL 训练循环
    
    流程：
    1. Agent A 分析进度并生成环境
    2. Agent B 运行实验
    3. RL 训练器计算 ToolRL 风格的奖励
    4. 验证机制计算置信度
    5. 更新模型（GRPO）
    6. 进入下一轮
    
    Args:
        ws: 工作区路径
        iterations: 迭代次数
        use_grpo: 是否使用 GRPO（否则使用 GAE）
        time_budget: 时间预算配置
        enable_scratchpad: 是否启用 Scratchpad 日志
        enable_verification: 是否启用验证机制
    """
    print("=" * 70)
    print("Dual-Agent ToolRL Mode (with ToolRL Training Loop)")
    print("=" * 70)
    
    # 初始化 Scratchpad 日志
    scratchpad_manager = None
    if enable_scratchpad:
        scratchpad_manager = ScratchpadManager(base_dir=os.path.join(ws, '.scratchpad'))
        scratchpad = scratchpad_manager.create()
        print(f"\n📝 Scratchpad Enabled: {scratchpad.session.session_id}")
    
    # 初始化时间预算
    budget_manager = TimeBudgetManager(time_budget or TimeBudget())
    budget_manager.start_training()
    
    # 初始化本地 LLM
    if llm_manager is None:
        llm_manager = LocalLLMManager()
        success, msg = llm_manager.auto_detect()
        if success:
            print(f"\n🌐 Local LLM detected: {msg}")
        else:
            print(f"\n⚠️ {msg}")
            print("   Falling back to offline mode...")
            llm_manager.enable_offline_mode()
    else:
        success, msg = llm_manager.check_health()
        print(f"\n🌐 Using configured LLM: {llm_manager.config.provider.value}")
    
    # 初始化验证机制
    verifier = None
    confidence_tracker = None
    reward_calculator = None
    
    if enable_verification:
        try:
            verifier = SelfVerifier()
            confidence_tracker = ConfidenceTracker(window_size=10)
            reward_calculator = EnhancedRewardCalculator()
            print(f"\n✅ Verification Enabled")
            print(f"   • SelfVerifier: Active")
            print(f"   • ConfidenceTracker: Active")
            print(f"   • EnhancedRewardCalculator: Active")
        except ImportError as e:
            print(f"\n⚠️ Verification modules not available: {e}")
            enable_verification = False
    
    # 初始化 Harness Engineering 模块
    doc_gardener = None
    arch_engine = None
    
    try:
        doc_gardener = DocGardeningAgent(workspace=ws)
        arch_engine = ArchitectureRuleEngine(workspace=ws)
        print(f"\n🔧 Harness Engineering:")
        print(f"   • DocGardeningAgent: Active")
        print(f"   • ArchitectureRuleEngine: Active")
    except ImportError as e:
        print(f"\n⚠️ Harness modules not available: {e}")
    
    # 初始化
    setup_workspace(ws)
    agent_a = AgentA(ws, scratchpad=scratchpad if enable_scratchpad else None)
    tools = create_registry(ws, ["git", "moon"])
    agent_b = AgentB(ws, tools, scratchpad=scratchpad if enable_scratchpad else None)
    trainer = RLTrainer(RLConfig())
    results_log = ResultsLog("results.tsv")
    
    # 记录启动
    if scratchpad:
        scratchpad.log_thinking(
            f'开始训练循环: {iterations} 次迭代',
            confidence=1.0
        )
        if enable_verification:
            scratchpad.log_thinking(
                '验证机制已启用',
                confidence=1.0
            )
    
    # 统计信息
    total_experiments = 0
    total_kept = 0
    stage_transitions = []
    timeout_count = 0
    
    for epoch in range(iterations):
        # 检查迭代超时
        if budget_manager.check_iteration_timeout():
            print(f"\n⏱ Iteration timeout! Stopping training.")
            break
        
        print(f"\n{'='*70}")
        print(f"Epoch {epoch+1}/{iterations} [{budget_manager.format_elapsed()}]")
        print(f"{'='*70}")
        
        # ========== Agent A: 分析进度并生成环境 ==========
        progress = agent_a.analyze_progress("results.tsv")
        stage = agent_a.get_learning_stage(progress)
        reward_scale = agent_a.get_dynamic_reward_scale(stage)
        
        print(f"\n[Agent A] Progress Analysis")
        print(f"  • Total experiments: {progress.total_experiments}")
        print(f"  • Keep rate: {progress.keep_rate:.1%}")
        print(f"  • Best score: {progress.best_score:.2f}")
        print(f"  • Learning stage: {stage}")
        print(f"  • Reward scale: {reward_scale:.1f}")
        
        # 记录阶段转换
        if stage_transitions and stage_transitions[-1] != stage:
            print(f"  ⚡ Stage transition: {stage_transitions[-1]} → {stage}")
        stage_transitions.append(stage)
        
        # 生成环境
        env = agent_a.generate_environment(progress)
        print(f"\n[Agent A] Environment Generated")
        print(f"  • Name: {env.name}")
        print(f"  • Difficulty: {env.difficulty:.1f}")
        print(f"  • Tasks: {len(env.tasks)}")
        print(f"  • Tool constraints: {env.tool_constraints}")
        
        # ========== Agent B: 运行实验 ==========
        print(f"\n[Agent B] Running Experiments")
        print(f"  • Max iterations: 5")
        print(f"  • Time budget: {budget_manager.config.experiment}s per experiment")
        
        # 开始计时
        budget_manager.start_experiment()
        results = agent_b.autoresearch_loop(env, max_iterations=5)
        
        # 检查实验超时
        elapsed = budget_manager.get_experiment_elapsed()
        print(f"  • Experiment time: {elapsed:.1f}s")
        if elapsed > budget_manager.config.experiment:
            timeout_count += 1
            print(f"  ⚠️ Experiment exceeded time budget!")
        
        # ========== RL 训练: 计算 ToolRL 奖励 ==========
        print(f"\n[RL Trainer] Computing Rewards (ToolRL)")
        
        # 转换为轨迹格式
        trajectories = []
        for r in results:
            # 处理 ExperimentResult dataclass
            if hasattr(r, 'to_dict'):
                r_dict = r.to_dict()
            elif isinstance(r, dict):
                r_dict = r
            else:
                r_dict = {
                    'id': getattr(r, 'commit', 'unknown'),
                    'description': getattr(r.idea, 'description', '') if hasattr(r, 'idea') else '',
                    'tools_used': [],
                    'tools_expected': [],
                    'params_used': {},
                    'params_expected': {},
                    'reasoning': '',
                    'tool_calls': '',
                    'response': '',
                }
            
            trajectory = format_trajectory(r_dict)
            trajectories.append(trajectory)
        
        # 计算奖励（使用增强版）
        if enable_verification and reward_calculator:
            rewards = [reward_calculator.calculate(traj) for traj in trajectories]
            # 记录验证结果
            for i, reward in enumerate(rewards):
                if hasattr(reward, 'verification'):
                    # EnhancedReward 对象
                    confidence = reward.verification.confidence
                    exact_match = reward.verification.exact_match
                    actual_reward = reward.total
                else:
                    # 简单浮点数
                    confidence = 0.5
                    exact_match = False
                    actual_reward = reward
                
                # 追踪置信度
                if confidence_tracker:
                    confidence_tracker.add(confidence)
                
                # 记录到 Scratchpad
                if scratchpad:
                    scratchpad.log_reward(
                        total=actual_reward,
                        breakdown={'rformat': reward.rformat if hasattr(reward, 'rformat') else 0,
                                  'rname': reward.rname if hasattr(reward, 'rname') else 0,
                                  'rparam': reward.rparam if hasattr(reward, 'rparam') else 0,
                                  'rvalue': reward.rvalue if hasattr(reward, 'rvalue') else 0},
                        verification={
                            'confidence': confidence,
                            'exact_match': exact_match
                        }
                    )
        else:
            rewards = [trainer.reward_calc.calculate(traj) for traj in trajectories]
        
        # 训练步骤（GRPO）
        train_results = []
        for i, r in enumerate(results):
            if hasattr(r, 'to_dict'):
                train_results.append(r.to_dict())
            elif isinstance(r, dict):
                train_results.append({
                    'id': r.get('id', f'exp{i}'),
                    'description': r.get('description', ''),
                    'predicted_tools': r.get('tools_used', []),
                    'ground_truth_tools': r.get('tools_expected', []),
                    'predicted_params': r.get('params_used', {}),
                    'ground_truth_params': r.get('params_expected', {}),
                })
            else:
                train_results.append({
                    'id': getattr(r, 'commit', f'exp{i}'),
                    'description': getattr(r.idea, 'description', '') if hasattr(r, 'idea') else '',
                    'predicted_tools': [],
                    'ground_truth_tools': [],
                    'predicted_params': {},
                    'ground_truth_params': {},
                })
        
        stats = trainer.train_step(train_results, use_grpo=use_grpo)
        
        print(f"  • Method: {stats['method']}")
        print(f"  • Total reward: {stats['total_reward']:.2f}")
        print(f"  • Avg reward: {stats['avg_reward']:.2f}")
        print(f"  • Avg advantage: {stats['avg_advantage']:.2f}")
        print(f"  • Experiences: {stats['experiences']}")
        
        # ========== 记录结果 ==========
        print(f"\n[Results] Recording Experiments")
        
        kept = 0
        for i, r in enumerate(results):
            if hasattr(r, 'status'):
                status = r.status
            elif isinstance(r, dict):
                status = r.get('status', 'unknown')
            else:
                status = 'unknown'
            if status == 'keep':
                kept += 1
            
            commit = getattr(r, 'commit', f'exp{i}') if hasattr(r, 'commit') else f'exp{i}'
            desc = getattr(r.idea, 'description', '') if hasattr(r, 'idea') else ''
            if isinstance(r, dict):
                commit = r.get('commit', f'exp{i}')
                desc = r.get('description', '')
            
            record = ExperimentRecord(
                commit=commit,
                timestamp=datetime.now().isoformat(),
                bpb_score=float(rewards[i].total if hasattr(rewards[i], 'total') else rewards[i]) if i < len(rewards) else 0.0,
                memory_mb=getattr(r, 'metrics', {}).get('memory', 0) if hasattr(r, 'metrics') else 0,
                status=status,
                description=desc,
            )
            results_log.append(record)
        
        total_experiments += len(results)
        total_kept += kept
        
        print(f"  • Experiments: {len(results)}")
        print(f"  • Kept: {kept}/{len(results)} ({kept/len(results)*100:.0f}%)")
        print(f"  • Cumulative: {total_kept}/{total_experiments} ({total_kept/total_experiments*100:.0f}%)")
    
    # ========== 最终统计 ==========
    print(f"\n{'='*70}")
    print("Final Statistics")
    print(f"{'='*70}")
    
    final_stats = results_log.get_stats()
    print(f"  • Total experiments: {final_stats['total']}")
    print(f"  • Keep rate: {final_stats['keep_rate']:.1%}")
    print(f"  • Stage transitions: {len(set(stage_transitions))}")
    print(f"  • Final stage: {stage_transitions[-1] if stage_transitions else 'unknown'}")
    print(f"  • Training method: {stats['method']}")
    print(f"  • Total experiences: {stats['experiences']}")
    
    # 验证机制统计
    if enable_verification and confidence_tracker:
        summary = confidence_tracker.get_summary()
        print(f"\n[Verification Statistics]")
        print(f"  • Average confidence: {summary.get('average', 0):.1%}")
        print(f"  • Confidence trend: {summary.get('trend')}")
        print(f"  • Stability: {summary.get('stability', 0):.1%}")
        
        if summary.get('should_alert'):
            print(f"  ⚠️ Alert: {summary.get('alert_reason')}")
        else:
            print(f"  ✅ No alerts")
        
        # 保存验证统计到 Scratchpad
        if scratchpad:
            scratchpad.log_result(
                status='completed',
                message='Training completed',
                metrics={
                    'confidence_average': summary.get('average', 0),
                    'confidence_trend': summary.get('trend'),
                    'stability': summary.get('stability', 0),
                }
            )
    
    # 保存 Scratchpad 日志
    if scratchpad_manager:
        filepath = scratchpad_manager.save_current()
        print(f"\n📝 Scratchpad saved: {filepath}")
    
    # ========== Harness Engineering 收尾 ==========
    
    # DocGardening：扫描文档状态
    if doc_gardener:
        print(f"\n{'='*70}")
        print("[DocGardening] Scanning docs...")
        garden_report = doc_gardener.scan()
        
        if garden_report.stale_docs > 0 or garden_report.outdated_docs > 0:
            print(f"  ⚠️ {garden_report.stale_docs} stale, {garden_report.outdated_docs} outdated docs")
            stale = doc_gardener.get_stale_docs()
            for doc in stale[:3]:
                print(f"     - {doc.name} ({doc.age_days} days old)")
        else:
            print(f"  ✅ All {garden_report.current_docs} docs are current")
    
    # ArchitectureRuleEngine：验证架构
    if arch_engine:
        print(f"\n[Architecture] Validating rules...")
        arch_report = arch_engine.validate_all(['.py'])
        
        if arch_report.total_violations > 0:
            print(f"  ⚠️ {arch_report.total_violations} violations found")
            print(f"     Critical: {arch_report.critical_violations}")
            print(f"     Major: {arch_report.major_violations}")
        else:
            print(f"  ✅ Architecture check passed ({arch_report.total_files} files)")
    
    return final_stats


def run_single_with_toolrl(ws: str, iterations: int = 5):
    """
    单 Agent 模式（用于测试）
    """
    print("=" * 70)
    print("Single Agent Mode (with ToolRL Rewards)")
    print("=" * 70)
    
    setup_workspace(ws)
    tools = create_registry(ws, ["git", "moon"])
    agent_b = AgentB(ws, tools)
    trainer = RLTrainer(RLConfig())
    
    # 创建简单的测试环境
    env = TrainingEnvironment(
        id="single",
        name="Single Agent Test",
        description="Test environment for single agent",
        tasks=[
            {
                "id": "t1",
                "type": "optimize",
                "description": "Test task",
                "target": "score > 100",
                "tools_required": ["git", "moon"],
            }
        ],
        difficulty=0.5,
        available_tools=["git", "moon"],
        tool_constraints={"max_tool_calls": 10, "timeout": 300},
        reward_config={
            'r_format_scale': 1.0,
            'r_correct_scale': 3.0,
            'stage': 'beginner',
        },
    )
    
    print(f"\n[Environment] {env.name}")
    print(f"  • Difficulty: {env.difficulty}")
    print(f"  • Tasks: {len(env.tasks)}")
    
    # 运行实验
    print(f"\n[Agent B] Running experiments...")
    results = agent_b.autoresearch_loop(env, max_iterations=iterations)
    
    # 计算奖励
    print(f"\n[RL Trainer] Computing Rewards")
    train_results = []
    for i, r in enumerate(results):
        if hasattr(r, 'to_dict'):
            train_results.append(r.to_dict())
        elif isinstance(r, dict):
            train_results.append({
                'id': r.get('id', f'exp{i}'),
                'description': r.get('description', ''),
                'predicted_tools': r.get('tools_used', []),
                'ground_truth_tools': r.get('tools_expected', []),
                'predicted_params': r.get('params_used', {}),
                'ground_truth_params': r.get('params_expected', {}),
            })
        else:
            # ExperimentResult dataclass
            train_results.append({
                'id': getattr(r, 'commit', f'exp{i}'),
                'description': getattr(r.idea, 'description', '') if hasattr(r, 'idea') else '',
                'predicted_tools': [],
                'ground_truth_tools': [],
                'predicted_params': {},
                'ground_truth_params': {},
            })
    
    stats = trainer.train_step(train_results, use_grpo=False)
    
    kept = sum(1 for r in results if getattr(r, 'status', '') == 'keep')
    print(f"\n[Results]")
    print(f"  • Total: {len(results)}")
    print(f"  • Kept: {kept}/{len(results)}")
    print(f"  • Avg reward: {stats['avg_reward']:.2f}")
    
    return stats


def run_dual_agent(ws: str, iterations: int = 10):
    """向后兼容的旧接口"""
    return run_dual_agent_with_toolrl(ws, iterations, use_grpo=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Dual-Agent ToolRL with ToolRL Training Loop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Gateway mode (HTTP API + Web UI on port 8765)
  python main.py --gateway
  python main.py --gateway --port 8080

  # Single Agent mode (test)
  python main.py --mode single --iterations 5

  # Dual Agent mode (full training)
  python main.py --mode dual --iterations 10

  # Use GAE instead of GRPO
  python main.py --mode dual --iterations 10 --no-grpo

  # Custom time budget (5min experiment, 30min iteration)
  python main.py --mode dual --iterations 10 --exp-time 300 --iter-time 1800

  # Disable time budget
  python main.py --mode dual --iterations 10 --no-time-budget
        """
    )

    # Gateway mode
    parser.add_argument("--gateway", action="store_true",
                        help="Start Gateway HTTP service (API + Web UI)")
    parser.add_argument("--port", type=int, default=8765,
                        help="Gateway port (default: 8765)")
    parser.add_argument("--host", default="0.0.0.0",
                        help="Gateway host (default: 0.0.0.0)")
    parser.add_argument("--reload", action="store_true",
                        help="Enable auto-reload for Gateway (dev mode)")

    # Training mode
    parser.add_argument("--mode", choices=["single", "dual"], default="dual",
                        help="Run mode")
    parser.add_argument("--workspace", default="workspace",
                        help="Workspace path")
    parser.add_argument("--iterations", type=int, default=10,
                        help="Number of iterations")
    parser.add_argument("--no-grpo", action="store_true",
                        help="Use GAE instead of GRPO")

    # Time budget
    parser.add_argument("--exp-time", type=int, default=300,
                        help="Max time per experiment in seconds (default: 300)")
    parser.add_argument("--iter-time", type=int, default=1800,
                        help="Max time per iteration in seconds (default: 1800)")
    parser.add_argument("--no-time-budget", action="store_true",
                        help="Disable time budget")

    # Scratchpad
    parser.add_argument("--no-scratchpad", action="store_true",
                        help="Disable Scratchpad logging")

    # Verification
    parser.add_argument("--no-verification", action="store_true",
                        help="Disable verification mechanism")

    # Offline mode
    parser.add_argument("--offline", action="store_true",
                        help="Offline mode (use mock LLM responses)")

    args = parser.parse_args()

    # ── Gateway Mode ────────────────────────────────────────────────────────────
    if args.gateway:
        import uvicorn
        from runtimes.gateway import create_app
        print(f"\n⚡ Starting Curriculum-Forge Gateway")
        print(f"   Host: {args.host}")
        print(f"   Port: {args.port}")
        print(f"   UI:   http://{args.host}:{args.port}")
        print(f"   API:  http://{args.host}:{args.port}/docs")
        app = create_app()
        uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)
        sys.exit(0)

    # ── Training Mode ───────────────────────────────────────────────────────────
    time_budget = None
    if not args.no_time_budget:
        time_budget = TimeBudget(
            experiment=args.exp_time,
            iteration=args.iter_time,
            enabled=True
        )
        print(f"\n⏱ Time Budget Enabled:")
        print(f"   • Experiment: {args.exp_time}s")
        print(f"   • Iteration: {args.iter_time}s")

    llm_manager = None
    if args.offline:
        llm_manager = LocalLLMManager()
        llm_manager.enable_offline_mode()
        print(f"\n🔒 Offline mode enabled")

    if args.mode == "single":
        run_single_with_toolrl(args.workspace, args.iterations)
    else:
        run_dual_agent_with_toolrl(
            args.workspace,
            args.iterations,
            use_grpo=not args.no_grpo,
            time_budget=time_budget,
            enable_scratchpad=not args.no_scratchpad,
            enable_verification=not args.no_verification,
            llm_manager=llm_manager,
        )
