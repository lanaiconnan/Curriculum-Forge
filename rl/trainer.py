"""RL 训练模块"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Callable
from collections import deque

try:
    from rl.evolution import EvolutionOptimizer, SelectionMethod
    EVOLUTION_AVAILABLE = True
except ImportError:
    EvolutionOptimizer = None
    SelectionMethod = None
    EVOLUTION_AVAILABLE = False


@dataclass
class RLExperience:
    state: str
    action: str
    reward: float
    next_state: str
    done: bool
    tool_calls: List[Dict]


@dataclass
class RLConfig:
    learning_rate: float = 3e-4
    gamma: float = 0.99
    epsilon: float = 0.2
    max_experiences: int = 10000


class RewardCalculator:
    """ToolRL 风格的奖励计算器 - 细粒度分解"""
    
    def __init__(self):
        # 格式奖励：0 或 1
        self.r_format_scale = 1.0
        
        # 正确性奖励：[-3, 3]
        self.r_correct_scale = 3.0
        
        # 子组件权重
        self.r_name_weight = 1.0      # 工具名称匹配
        self.r_param_weight = 1.0     # 参数名称匹配
        self.r_value_weight = 1.0     # 参数值匹配
    
    def calculate_format_reward(self, trajectory: Dict) -> float:
        """
        格式奖励：检查输出是否包含所有必需的特殊 token
        Rformat ∈ {0, 1}
        """
        required_fields = ['think', 'tool_call', 'response']
        has_all_fields = all(field in trajectory for field in required_fields)
        
        # 检查顺序
        if has_all_fields:
            think_idx = trajectory.get('think_idx', 0)
            tool_idx = trajectory.get('tool_call_idx', 1)
            resp_idx = trajectory.get('response_idx', 2)
            correct_order = think_idx < tool_idx < resp_idx
            return self.r_format_scale if correct_order else 0.0
        return 0.0
    
    def calculate_tool_name_match(self, predicted_tools: List[str], 
                                  ground_truth_tools: List[str]) -> float:
        """
        工具名称匹配：rname = |NG ∩ NP| / |NG ∪ NP|
        """
        if not ground_truth_tools:
            return 0.0
        
        predicted_set = set(predicted_tools)
        truth_set = set(ground_truth_tools)
        
        intersection = len(predicted_set & truth_set)
        union = len(predicted_set | truth_set)
        
        return intersection / union if union > 0 else 0.0
    
    def calculate_param_name_match(self, predicted_params: Dict, 
                                   ground_truth_params: Dict) -> float:
        """
        参数名称匹配：rparam = Σ |keys(PG) ∩ keys(PP)| / |keys(PG) ∪ keys(PP)|
        """
        if not ground_truth_params:
            return 0.0
        
        pred_keys = set(predicted_params.keys())
        truth_keys = set(ground_truth_params.keys())
        
        intersection = len(pred_keys & truth_keys)
        union = len(pred_keys | truth_keys)
        
        return intersection / union if union > 0 else 0.0
    
    def calculate_param_value_match(self, predicted_params: Dict, 
                                    ground_truth_params: Dict) -> float:
        """
        参数值匹配：rvalue = Σ Σ 1[PG[k] = PP[k]]
        """
        if not ground_truth_params:
            return 0.0
        
        matches = 0
        total = len(ground_truth_params)
        
        for key, truth_value in ground_truth_params.items():
            if key in predicted_params:
                if predicted_params[key] == truth_value:
                    matches += 1
        
        return matches / total if total > 0 else 0.0
    
    def calculate_correctness_reward(self, trajectory: Dict) -> float:
        """
        正确性奖励：Rcorrect ∈ [-3, 3]
        = rname + rparam + rvalue (每个 ∈ [0, 1])
        """
        predicted_tools = trajectory.get('predicted_tools', [])
        ground_truth_tools = trajectory.get('ground_truth_tools', [])
        predicted_params = trajectory.get('predicted_params', {})
        ground_truth_params = trajectory.get('ground_truth_params', {})
        
        r_name = self.calculate_tool_name_match(predicted_tools, ground_truth_tools)
        r_param = self.calculate_param_name_match(predicted_params, ground_truth_params)
        r_value = self.calculate_param_value_match(predicted_params, ground_truth_params)
        
        # 组合三个组件，缩放到 [-3, 3]
        r_correct = (r_name * self.r_name_weight + 
                     r_param * self.r_param_weight + 
                     r_value * self.r_value_weight) * self.r_correct_scale / 3.0
        
        return r_correct
    
    def calculate(self, trajectory: Dict) -> float:
        """
        总奖励 = 格式奖励 + 正确性奖励
        Rfinal = Rformat + Rcorrect ∈ [-3, 4]
        """
        r_format = self.calculate_format_reward(trajectory)
        r_correct = self.calculate_correctness_reward(trajectory)
        
        return r_format + r_correct


class RLTrainer:
    """GRPO 风格的 RL 训练器 - 组相对策略优化 + 进化算法"""
    
    def __init__(self, config: RLConfig = None, enable_evolution: bool = False):
        self.config = config or RLConfig()
        self.reward_calc = RewardCalculator()
        self.experiences: deque = deque(maxlen=self.config.max_experiences)
        
        # 进化优化器
        self.evolution_optimizer = None
        if enable_evolution and EVOLUTION_AVAILABLE:
            self.evolution_optimizer = EvolutionOptimizer(
                population_size=10,
                mutation_rate=0.1,
                crossover_rate=0.8,
                selection_method=SelectionMethod.TOURNAMENT,
            )
    
        self.eta = 1e-8  # 避免除以零的常数
    
    def add_experience(self, exp: RLExperience):
        self.experiences.append(exp)
    
    def compute_group_normalized_advantages(self, group_rewards: List[float]) -> List[float]:
        """
        GRPO 的组归一化优势计算
        Ai(si|Q) = (ri - μQ) / (σQ + η)
        
        其中：
        - μQ: 组内奖励的平均值
        - σQ: 组内奖励的标准差
        - η: 避免除以零的常数
        """
        if not group_rewards:
            return []
        
        # 计算平均值和标准差
        mean_reward = sum(group_rewards) / len(group_rewards)
        
        variance = sum((r - mean_reward) ** 2 for r in group_rewards) / len(group_rewards)
        std_reward = variance ** 0.5
        
        # 计算归一化优势
        advantages = []
        for reward in group_rewards:
            advantage = (reward - mean_reward) / (std_reward + self.eta)
            advantages.append(advantage)
        
        return advantages
    
    def compute_advantages(self, rewards: List[float]) -> List[float]:
        """
        计算优势函数（GAE）
        """
        advantages = []
        gae = 0.0
        for t in reversed(range(len(rewards))):
            next_val = rewards[t + 1] if t < len(rewards) - 1 else 0.0
            delta = rewards[t] + self.config.gamma * next_val - rewards[t]
            gae = delta + self.config.gamma * self.config.epsilon * gae
            advantages.insert(0, gae)
        return advantages
    
    def update(self):
        """更新策略（简化版）"""
        if len(self.experiences) < self.config.max_experiences // 10:
            return
    
    def train_step(self, results: List, use_grpo: bool = True) -> Dict[str, Any]:
        """
        训练步骤
        
        Args:
            results: 实验结果列表
            use_grpo: 是否使用 GRPO 组归一化
        
        Returns:
            训练统计信息
        """
        trajectories = []
        rewards = []
        
        for result in results:
            # 构建轨迹
            trajectory = {
                'predicted_tools': result.get('predicted_tools', []),
                'ground_truth_tools': result.get('ground_truth_tools', []),
                'predicted_params': result.get('predicted_params', {}),
                'ground_truth_params': result.get('ground_truth_params', {}),
                'think_idx': 0,
                'tool_call_idx': 1,
                'response_idx': 2,
            }
            
            # 计算奖励
            reward = self.reward_calc.calculate(trajectory)
            
            trajectories.append(trajectory)
            rewards.append(reward)
            
            # 添加经验
            self.add_experience(RLExperience(
                state="env_{}".format(result.get('id', 'unknown')),
                action=result.get('description', ''),
                reward=reward,
                next_state="done",
                done=True,
                tool_calls=result.get('predicted_tools', []),
            ))
        
        # 计算优势
        if use_grpo:
            advantages = self.compute_group_normalized_advantages(rewards)
        else:
            advantages = self.compute_advantages(rewards)
        
        self.update()
        
        return {
            "total_reward": sum(rewards),
            "avg_reward": sum(rewards) / len(rewards) if rewards else 0,
            "avg_advantage": sum(advantages) / len(advantages) if advantages else 0,
            "experiences": len(self.experiences),
            "method": "GRPO" if use_grpo else "GAE",
        }
