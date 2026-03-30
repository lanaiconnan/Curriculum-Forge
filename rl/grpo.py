"""GRPO - Group Relative Policy Optimization

来自 DeepSeek 的 GRPO 算法：
- Group Relative Policy Optimization
- 无需 Critic 模型
- 组内相对奖励
- 高效稳定
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import math
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 可选依赖
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    class np:
        @staticmethod
        def mean(arr):
            return sum(arr) / len(arr) if arr else 0.0
        @staticmethod
        def std(arr):
            if not arr: return 0.0
            m = sum(arr) / len(arr)
            return (sum((x-m)**2 for x in arr) / len(arr)) ** 0.5
        @staticmethod
        def exp(x):
            import math
            return math.exp(x)
        @staticmethod
        def log(x):
            import math
            return math.log(x)
        @staticmethod
        def max(arr):
            return max(arr) if arr else 0.0
        @staticmethod
        def clip(a, lo, hi):
            return max(lo, min(hi, a))
        @staticmethod
        def random():
            import random
            return random.random()
        @staticmethod
        def choice(n, p=None):
            import random
            if p:
                return random.choices(range(n), weights=p, k=1)[0]
            return random.randint(0, n-1)
        @staticmethod
        def zeros(n):
            return [0.0] * n
        @staticmethod
        def array(lst):
            return list(lst)

try:
    from rl.gae import GAE, GAEConfig
except ImportError:
    GAE = None
    GAEConfig = None


@dataclass
class GRPOConfig:
    """GRPO 配置"""
    group_size: int = 4           # 每组样本数
    clip_ratio: float = 0.2      # PPO 裁剪比率
    entropy_coef: float = 0.01   # 熵正则化系数
    learning_rate: float = 3e-4  # 学习率
    gamma: float = 0.99          # 折扣因子
    lam: float = 0.95            # GAE lambda
    normalize_advantage: bool = True  # 是否归一化优势
    use_kl_penalty: bool = True   # 是否使用 KL 惩罚
    kl_coef: float = 0.1          # KL 惩罚系数


@dataclass
class PolicyOutput:
    """策略输出"""
    action: Dict[str, Any]        # 选择的动作
    log_prob: float               # 对数概率
    value: float = 0.0            # 价值估计
    entropy: float = 0.0          # 熵


class PolicyNetwork:
    """
    策略网络
    
    π(a|s) - 策略概率分布
    """
    
    def __init__(
        self,
        action_dim: int = 10,
        state_dim: int = 128,
        hidden_dim: int = 256,
    ):
        """
        初始化策略网络
        
        Args:
            action_dim: 动作维度
            state_dim: 状态维度
            hidden_dim: 隐藏层维度
        """
        self.action_dim = action_dim
        self.state_dim = state_dim
        
        # 简化的策略网络（线性模型）
        import random
        self.weights = [[random.random() * 0.01 for _ in range(action_dim)] for _ in range(state_dim)]
        self.bias = [0.0] * action_dim
    
    def forward(self, state_features: list) -> list:
        """前向传播"""
        logits = []
        for j in range(self.action_dim):
            logit = sum(state_features[i] * self.weights[i][j] for i in range(self.state_dim)) + self.bias[j]
            logits.append(logit)
        return logits
    
    def get_action_probs(self, state: Dict[str, Any]) -> list:
        """
        获取动作概率分布
        """
        features = self._extract_features(state)
        logits = self.forward(features)
        
        # Softmax
        max_logit = max(logits)
        exp_logits = [math.exp(l - max_logit) for l in logits]
        total = sum(exp_logits)
        probs = [e / total for e in exp_logits]
        return probs
    
    def sample_action(self, state: Dict[str, Any], temperature: float = 1.0) -> PolicyOutput:
        """采样动作"""
        probs = self.get_action_probs(state)
        
        if temperature != 1.0:
            logits = [math.log(p + 1e-10) / temperature for p in probs]
            max_l = max(logits)
            exp_l = [math.exp(l - max_l) for l in logits]
            total = sum(exp_l)
            probs = [e / total for e in exp_l]
        
        import random
        r = random.random()
        cumulative = 0.0
        action_idx = 0
        for i, p in enumerate(probs):
            cumulative += p
            if r < cumulative:
                action_idx = i
                break
        
        entropy = -sum(p * math.log(p + 1e-10) for p in probs)
        
        return PolicyOutput(
            action={'index': action_idx, 'probs': probs},
            log_prob=float(math.log(probs[action_idx] + 1e-10)),
            entropy=float(entropy),
        )
    
    def evaluate_action(self, state: Dict[str, Any], action: Dict[str, Any]) -> Tuple[float, float]:
        """评估动作"""
        probs = self.get_action_probs(state)
        action_idx = action.get('index', 0)
        log_prob = math.log(probs[action_idx] + 1e-10)
        entropy = -sum(p * math.log(p + 1e-10) for p in probs)
        return float(log_prob), float(entropy)
    
    def _extract_features(self, state: Dict[str, Any]) -> list:
        """提取特征"""
        state_str = str(state)
        return [hash(state_str + str(i)) % 1000 / 1000.0 for i in range(self.state_dim)]
    
    def update(self, grads: list, lr: float = None):
        """更新参数"""
        lr = lr or 3e-4
        self.weights += lr * grads


class GRPO:
    """
    Group Relative Policy Optimization
    
    来自 DeepSeek 的算法：
    - 将样本分组
    - 计算组内相对奖励
    - 使用相对奖励进行策略更新
    
    优点：
    - 无需 Critic 模型（节省内存）
    - 组内对比减少方差
    - 稳定高效
    """
    
    def __init__(self, config: GRPOConfig = None):
        """
        初始化 GRPO
        
        Args:
            config: GRPO 配置
        """
        self.config = config or GRPOConfig()
        
        # 策略网络
        self.policy = PolicyNetwork()
        
        # 参考策略（用于 KL 惩罚）
        self.ref_policy = None
        
        # 统计
        self.stats = {
            'updates': 0,
            'mean_reward': 0.0,
            'mean_advantage': 0.0,
            'mean_entropy': 0.0,
            'policy_loss': 0.0,
        }
    
    def compute_group_advantages(
        self,
        rewards: List[float],
        group_size: int = None,
    ) -> List[float]:
        """
        计算组相对优势
        
        将奖励分组，计算每个样本相对于组内平均的优势
        
        Args:
            rewards: 奖励列表
            group_size: 每组大小
        
        Returns:
            List[float]: 组相对优势
        """
        group_size = group_size or self.config.group_size
        
        advantages = []
        
        for i in range(0, len(rewards), group_size):
            group_rewards = rewards[i:i + group_size]
            
            if len(group_rewards) == 0:
                continue
            
            # 组内平均奖励
            group_mean = np.mean(group_rewards)
            group_std = np.std(group_rewards)
            
            # 组相对优势
            for r in group_rewards:
                if group_std > 1e-8:
                    adv = (r - group_mean) / group_std
                else:
                    adv = r - group_mean
                
                advantages.append(adv)
        
        return advantages
    
    def compute_policy_loss(
        self,
        states: List[Dict[str, Any]],
        actions: List[Dict[str, Any]],
        advantages: List[float],
        old_log_probs: List[float],
    ) -> float:
        """
        计算策略损失
        
        L = -E[min(r(θ) * A, clip(r(θ), 1-ε, 1+ε) * A)]
        
        Args:
            states: 状态列表
            actions: 动作列表
            advantages: 优势列表
            old_log_probs: 旧策略对数概率
        
        Returns:
            float: 策略损失
        """
        losses = []
        entropies = []
        
        for state, action, adv, old_log_prob in zip(
            states, actions, advantages, old_log_probs
        ):
            # 当前策略评估
            new_log_prob, entropy = self.policy.evaluate_action(state, action)
            
            # 概率比率
            ratio = np.exp(new_log_prob - old_log_prob)
            
            # PPO 裁剪
            clip_ratio = self.config.clip_ratio
            clipped_ratio = np.clip(ratio, 1 - clip_ratio, 1 + clip_ratio)
            
            # 策略损失
            loss = -min(ratio * adv, clipped_ratio * adv)
            
            losses.append(loss)
            entropies.append(entropy)
        
        # 平均损失
        policy_loss = np.mean(losses) if losses else 0.0
        mean_entropy = np.mean(entropies) if entropies else 0.0
        
        # 熵正则化
        total_loss = policy_loss - self.config.entropy_coef * mean_entropy
        
        # 更新统计
        self.stats['policy_loss'] = float(policy_loss)
        self.stats['mean_entropy'] = float(mean_entropy)
        
        return float(total_loss)
    
    def update(
        self,
        states: List[Dict[str, Any]],
        actions: List[Dict[str, Any]],
        rewards: List[float],
        old_log_probs: List[float] = None,
    ) -> Dict[str, Any]:
        """
        执行 GRPO 更新
        
        Args:
            states: 状态列表
            actions: 动作列表
            rewards: 奖励列表
            old_log_probs: 旧策略对数概率（可选）
        
        Returns:
            Dict[str, Any]: 更新统计
        """
        if old_log_probs is None:
            # 使用当前策略计算
            old_log_probs = []
            for state, action in zip(states, actions):
                log_prob, _ = self.policy.evaluate_action(state, action)
                old_log_probs.append(log_prob)
        
        # 计算组相对优势
        advantages = self.compute_group_advantages(rewards)
        
        # 归一化
        if self.config.normalize_advantage and advantages:
            mean = np.mean(advantages)
            std = np.std(advantages)
            if std > 1e-8:
                advantages = [(a - mean) / std for a in advantages]
        
        # 计算损失
        loss = self.compute_policy_loss(
            states, actions, advantages, old_log_probs
        )
        
        # 简单梯度更新（实际应使用优化器）
        # 这里省略反向传播细节
        
        # 更新统计
        self.stats['updates'] += 1
        self.stats['mean_reward'] = float(np.mean(rewards)) if rewards else 0.0
        self.stats['mean_advantage'] = float(np.mean(advantages)) if advantages else 0.0
        
        return {
            'loss': loss,
            'mean_reward': self.stats['mean_reward'],
            'mean_advantage': self.stats['mean_advantage'],
            'mean_entropy': self.stats['mean_entropy'],
            'updates': self.stats['updates'],
        }
    
    def sample_actions(
        self,
        states: List[Dict[str, Any]],
        temperature: float = 1.0,
    ) -> List[PolicyOutput]:
        """
        批量采样动作
        
        Args:
            states: 状态列表
            temperature: 温度参数
        
        Returns:
            List[PolicyOutput]: 策略输出列表
        """
        outputs = []
        for state in states:
            output = self.policy.sample_action(state, temperature)
            outputs.append(output)
        return outputs
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            'config': {
                'group_size': self.config.group_size,
                'clip_ratio': self.config.clip_ratio,
                'entropy_coef': self.config.entropy_coef,
            },
        }
    
    def save_reference_policy(self):
        """保存参考策略（用于 KL 惩罚）"""
        import copy
        self.ref_policy = copy.deepcopy(self.policy)
    
    def compute_kl_divergence(
        self,
        states: List[Dict[str, Any]],
    ) -> float:
        """
        计算 KL 散度
        
        KL(π || π_ref)
        """
        if self.ref_policy is None:
            return 0.0
        
        kl_values = []
        
        for state in states:
            probs = self.policy.get_action_probs(state)
            ref_probs = self.ref_policy.get_action_probs(state)
            
            # KL 散度
            kl = np.sum(probs * (np.log(probs + 1e-10) - np.log(ref_probs + 1e-10)))
            kl_values.append(kl)
        
        return float(np.mean(kl_values)) if kl_values else 0.0


def compute_grpo_loss(
    rewards: List[float],
    log_probs: List[float],
    group_size: int = 4,
    clip_ratio: float = 0.2,
) -> float:
    """
    便捷函数：计算 GRPO 损失
    
    Args:
        rewards: 奖励列表
        log_probs: 对数概率列表
        group_size: 每组大小
        clip_ratio: 裁剪比率
    
    Returns:
        float: GRPO 损失
    """
    grpo = GRPO(GRPOConfig(group_size=group_size, clip_ratio=clip_ratio))
    
    # 简单实现
    advantages = grpo.compute_group_advantages(rewards)
    
    losses = []
    for i, (r, lp) in enumerate(zip(rewards, log_probs)):
        adv = advantages[i] if i < len(advantages) else 0.0
        loss = -adv * lp  # 简化版本
        losses.append(loss)
    
    return float(np.mean(losses)) if losses else 0.0
