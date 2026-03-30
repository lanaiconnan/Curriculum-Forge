"""Agent A - 环境生成器（集成 Scratchpad 日志）"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import os
import sys

# 添加项目路径以导入 Scratchpad
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from shared.scratchpad import Scratchpad
    SCRATCHPAD_AVAILABLE = True
except ImportError:
    SCRATCHPAD_AVAILABLE = False
    Scratchpad = None

try:
    from agent_a.analyst import AnalystAgent, AnalysisReport
    ANALYST_AVAILABLE = True
except ImportError:
    AnalystAgent = None
    AnalysisReport = None
    ANALYST_AVAILABLE = False

try:
    from shared.human_feedback import HumanFeedbackManager
    HUMAN_FEEDBACK_AVAILABLE = True
except ImportError:
    HumanFeedbackManager = None
    HUMAN_FEEDBACK_AVAILABLE = False


@dataclass
class TrainingEnvironment:
    id: str
    name: str
    description: str
    tasks: List[Dict]
    difficulty: float
    available_tools: List[str]
    tool_constraints: Dict
    reward_config: Dict


@dataclass
class AgentBProgress:
    total_experiments: int = 0
    keep_rate: float = 0.0
    best_score: float = 0.0
    weak_areas: List[str] = field(default_factory=list)


class AgentA:
    """
    环境生成器 - 根据 ToolRL 的课程学习策略
    
    Agent A 负责：
    1. 分析 Agent B 的实验进度
    2. 判断当前学习阶段
    3. 生成合适的训练环境
    4. 配置动态奖励尺度
    """
    
    def __init__(self, workspace: str = ".", scratchpad: Scratchpad = None, enable_analyst: bool = True, enable_human_feedback: bool = True):
        """
        初始化 Agent A
        
        Args:
            workspace: 工作区路径
            scratchpad: Scratchpad 日志实例（可选）
            enable_analyst: 是否启用 Analyst Agent
            enable_human_feedback: 是否启用人类反馈
        """
        self.workspace = workspace
        
        # 初始化 Scratchpad 日志
        if scratchpad is not None:
            self.scratchpad = scratchpad
        elif SCRATCHPAD_AVAILABLE:
            self.scratchpad = Scratchpad(base_dir=os.path.join(workspace, '.scratchpad'))
        else:
            self.scratchpad = None
        
        # 初始化 Analyst Agent
        self.analyst = None
        self.last_analysis: AnalysisReport = None
        if enable_analyst and ANALYST_AVAILABLE:
            self.analyst = AnalystAgent(scratchpad=self.scratchpad)
        
        # 初始化人类反馈管理器
        self.human_feedback = None
        if enable_human_feedback and HUMAN_FEEDBACK_AVAILABLE:
            self.human_feedback = HumanFeedbackManager(workspace=workspace, scratchpad=self.scratchpad)
        
        # ToolRL 的动态奖励尺度配置
        self.reward_scales = {
            'beginner': 1.0,      # 新手期：高奖励尺度
            'intermediate': 0.7,  # 成长期：中等奖励尺度
            'advanced': 0.5,      # 成熟期：低奖励尺度（细粒度）
        }
        
        # 学习阶段阈值
        self.learning_stage_thresholds = (0.3, 0.6)
    
    def _log_thinking(self, thought: str, confidence: float = None):
        """记录思考日志"""
        if self.scratchpad:
            self.scratchpad.log_thinking(
                thought=thought,
                confidence=confidence,
                context='Agent A - 环境生成'
            )
    
    def _log_tool_call(self, tool: str, args: Dict):
        """记录工具调用日志"""
        if self.scratchpad:
            self.scratchpad.log_tool_call(tool, args)
    
    def analyze_progress(self, results_tsv: str) -> AgentBProgress:
        """
        分析 Agent B 的实验进度
        
        Args:
            results_tsv: 结果文件路径
        
        Returns:
            AgentBProgress: 实验进度
        """
        # 记录思考
        self._log_thinking(f'分析实验进度：{results_tsv}', confidence=0.9)
        
        progress = AgentBProgress()
        if not os.path.exists(results_tsv):
            self._log_thinking('结果文件不存在，返回默认进度', confidence=1.0)
            return progress
        
        with open(results_tsv) as f:
            lines = f.readlines()[1:]  # 跳过表头
        
        keeps = 0
        for line in lines:
            parts = line.strip().split("\t")
            if len(parts) < 5:
                continue
            progress.total_experiments += 1
            if parts[4] == "keep":
                keeps += 1
            try:
                score = float(parts[2])
                if score > progress.best_score:
                    progress.best_score = score
            except:
                pass
        
        if progress.total_experiments > 0:
            progress.keep_rate = keeps / progress.total_experiments
        
        # 记录分析结果
        self._log_thinking(
            f'分析完成：{progress.total_experiments} 个实验，'
            f'保留率 {progress.keep_rate:.1%}，'
            f'最佳分数 {progress.best_score:.2f}',
            confidence=0.95
        )
        
        # 使用 Analyst Agent 进行深度分析
        if self.analyst and progress.total_experiments >= 5:
            results = self._load_results_for_analyst(results_tsv)
            if results:
                analysis_report = self.analyst.analyze(results)
                self.last_analysis = analysis_report
                
                # 根据分析结果更新 progress
                if analysis_report.trend_analysis.get('reward'):
                    trend = analysis_report.trend_analysis['reward']
                    self._log_thinking(
                        f'Analyst 分析：奖励趋势 {trend.direction.value}，斜率 {trend.slope:.4f}',
                        confidence=trend.confidence
                    )
                
                # 提取弱点领域
                for pattern in analysis_report.patterns:
                    if 'failure' in pattern.name.lower():
                        progress.weak_areas.append(pattern.description)
        
        return progress
    
    def _load_results_for_analyst(self, results_tsv: str) -> List[Dict[str, Any]]:
        """加载结果用于 Analyst 分析"""
        results = []
        try:
            with open(results_tsv) as f:
                lines = f.readlines()[1:]  # 跳过表头
            
            for line in lines:
                parts = line.strip().split("\t")
                if len(parts) < 5:
                    continue
                
                result = {
                    'id': parts[0],
                    'commit': parts[0],
                    'reward': float(parts[2]) if parts[2] else 0,
                    'memory': float(parts[3]) if len(parts) > 3 else 0,
                    'status': parts[4],
                    'description': parts[1] if len(parts) > 1 else '',
                    'tools_used': [],  # 需要从描述中解析
                    'failure_reason': 'unknown',
                }
                
                # 简单解析工具
                desc = result['description'].lower()
                if 'git' in desc:
                    result['tools_used'].append('git')
                if 'moon' in desc:
                    result['tools_used'].append('moon')
                
                results.append(result)
        except Exception as e:
            self._log_thinking(f'加载结果失败: {e}', confidence=0.5)
        
        return results
    
    def get_learning_stage(self, progress: AgentBProgress) -> str:
        """
        根据 keep_rate 判断学习阶段
        对应 ToolRL 的课程学习策略
        
        Args:
            progress: 实验进度
        
        Returns:
            str: 学习阶段 (beginner/intermediate/advanced)
        """
        # 记录思考
        self._log_thinking(
            f'判断学习阶段：keep_rate={progress.keep_rate:.1%}',
            confidence=0.8
        )
        
        if progress.total_experiments < 10 or progress.keep_rate < self.learning_stage_thresholds[0]:
            stage = 'beginner'
        elif progress.keep_rate < self.learning_stage_thresholds[1]:
            stage = 'intermediate'
        else:
            stage = 'advanced'
        
        self._log_thinking(
            f'判断结果：{stage} 阶段',
            confidence=0.9
        )
        
        return stage
    
    def get_dynamic_reward_scale(self, stage: str) -> float:
        """
        获取动态奖励尺度
        
        Args:
            stage: 学习阶段
        
        Returns:
            float: 奖励尺度
        """
        scale = self.reward_scales.get(stage, 0.7)
        
        self._log_thinking(
            f'获取奖励尺度：{stage} -> {scale}',
            confidence=1.0
        )
        
        return scale
    
    def generate_environment(self, progress: AgentBProgress) -> TrainingEnvironment:
        """
        生成训练环境
        根据 Agent B 的进度动态调整难度和奖励尺度
        """
        # 记录工具调用
        self._log_tool_call('generate_environment', {
            'total_experiments': progress.total_experiments,
            'keep_rate': progress.keep_rate,
        })
        
        # 确定学习阶段
        stage = self.get_learning_stage(progress)
        
        # 根据阶段设置难度
        if stage == 'beginner':
            difficulty = 0.3
            task_complexity = 'simple'
        elif stage == 'intermediate':
            difficulty = 0.5
            task_complexity = 'medium'
        else:  # advanced
            difficulty = 0.7
            task_complexity = 'complex'
        
        # 根据阶段生成任务
        if task_complexity == 'simple':
            tasks = [
                {
                    "id": "t1",
                    "type": "optimize",
                    "description": "Improve performance",
                    "target": "score > baseline",
                    "tools_required": ["moon"],
                },
                {
                    "id": "t2",
                    "type": "refactor",
                    "description": "Clean code",
                    "target": "maintain score",
                    "tools_required": ["git"],
                },
            ]
        elif task_complexity == 'medium':
            tasks = [
                {
                    "id": "t1",
                    "type": "optimize",
                    "description": "Improve performance with constraints",
                    "target": "score > baseline + 5%",
                    "tools_required": ["moon", "git"],
                },
                {
                    "id": "t2",
                    "type": "refactor",
                    "description": "Refactor with tests",
                    "target": "maintain score + pass tests",
                    "tools_required": ["git", "moon"],
                },
                {
                    "id": "t3",
                    "type": "benchmark",
                    "description": "Run comprehensive benchmark",
                    "target": "identify bottlenecks",
                    "tools_required": ["moon"],
                },
            ]
        else:  # complex
            tasks = [
                {
                    "id": "t1",
                    "type": "optimize",
                    "description": "Multi-objective optimization",
                    "target": "score > baseline + 10%, latency < threshold",
                    "tools_required": ["moon", "git"],
                },
                {
                    "id": "t2",
                    "type": "refactor",
                    "description": "Architectural refactoring",
                    "target": "improve maintainability + performance",
                    "tools_required": ["git", "moon"],
                },
                {
                    "id": "t3",
                    "type": "benchmark",
                    "description": "Advanced profiling",
                    "target": "identify and fix performance issues",
                    "tools_required": ["moon"],
                },
                {
                    "id": "t4",
                    "type": "experiment",
                    "description": "Design and run experiment",
                    "target": "validate hypothesis",
                    "tools_required": ["git", "moon"],
                },
            ]
        
        # 获取动态奖励尺度
        reward_scale = self.get_dynamic_reward_scale(stage)
        
        # 构建奖励配置（ToolRL 风格）
        reward_config = {
            'r_format_scale': reward_scale,
            'r_correct_scale': reward_scale * 3.0,
            'r_name_weight': 1.0,
            'r_param_weight': 1.0,
            'r_value_weight': 1.0,
            'stage': stage,
        }
        
        # 构建环境
        env = TrainingEnvironment(
            id=f"env-{progress.total_experiments // 10 + 1}",
            name=f"Environment #{progress.total_experiments // 10 + 1} ({stage})",
            description=f"Stage: {stage}, Difficulty: {difficulty}",
            tasks=tasks,
            difficulty=difficulty,
            available_tools=["git", "moon"],
            tool_constraints={
                "max_tool_calls": 10 if stage == 'beginner' else (15 if stage == 'intermediate' else 20),
                "timeout": 300,
            },
            reward_config=reward_config,
        )
        
        # 应用人类反馈约束
        if self.human_feedback:
            env_dict = {
                'difficulty': env.difficulty,
                'stage': stage,
                'tasks_count': len(env.tasks),
            }
            
            # 验证环境
            valid, failures = self.human_feedback.validate_environment(env_dict)
            if not valid:
                self._log_thinking(
                    f'环境验证失败: {failures}',
                    confidence=0.7
                )
            
            # 应用约束
            env_dict = self.human_feedback.apply_constraints_to_environment(env_dict)
            
            # 更新环境配置
            if 'difficulty' in env_dict:
                env.difficulty = env_dict['difficulty']
        
        self._log_tool_call('environment_generated', {
            'env_id': env.id,
            'stage': stage,
            'difficulty': difficulty,
            'tasks_count': len(tasks),
        })
        
        return env
