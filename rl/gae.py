"""GAE - Generalized Advantage Estimation

来自 RL 经典算法：
- Generalized Advantage Estimation (Schulman et al., 2016)
- 结合 Value Function 的 Advantage 估计
- 平衡偏差-方差权衡
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
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
    # 简单实现
    class np:
        @staticmethod
        def mean(arr):
            return sum(arr) / len(arr) if arr else 0.0
        
        @staticmethod
        def std(arr):
            if not arr:
                return 0.0
            m = sum(arr) / len(arr)
            return (sum((x - m) ** 2 for x in arr) / len(arr)) ** 0.5
        
        @staticmethod
        def max(arr):
            return max(arr) if arr else 0.0
        
        @staticmethod
        def min(arr):
            return min(arr) if arr else 0.0
        
        @staticmethod
        def dot(a, b):
            return sum(x * y for x, y in zip(a, b))
        
        @staticmethod
        def random():
            import random
            return random.random()


@dataclass
class GAEConfig:
    """GAE 配置"""
    gamma: float = 0.99           # 折扣因子
    lam: float = 0.95            # GAE lambda 参数
    normalize: bool = True        # 是否归一化 advantage


class ValueFunction:
    """
    价值函数
    
    使用简单的神经网络或线性模型估计状态价值 V(s)
    """
    
    def __init__(
        self,
        state_dim: int = 128,
        hidden_dim: int = 256,
        learning_rate: float = 3e-4,
    ):
        """
        初始化价值函数
        
        Args:
            state_dim: 状态维度
            hidden_dim: 隐藏层维度
            learning_rate: 学习率
        """
        self.state_dim = state_dim
        self.hidden_dim = hidden_dim
        self.lr = learning_rate
        
        # 简化的价值函数（线性模型 + 特征哈希）
        # 实际实现可使用 PyTorch/TensorFlow
        import random
        self.weights = [random.random() * 0.01 for _ in range(state_dim)]
        self.baseline = 0.0
    
    def predict(self, state: Dict[str, Any]) -> float:
        """预测状态价值"""
        features = self._extract_features(state)
        value = sum(a * b for a, b in zip(features, self.weights)) + self.baseline
        return float(value)
    
    def _extract_features(self, state: Dict[str, Any]) -> list:
        """提取特征向量"""
        state_str = str(state)
        return [hash(state_str + str(i)) % 1000 / 1000.0 for i in range(self.state_dim)]
    
    def update(self, states: List[Dict], returns: List[float]) -> float:
        """更新价值函数"""
        if not states or not returns:
            return 0.0
        predictions = [self.predict(s) for s in states]
        errors = [r - p for r, p in zip(returns, predictions)]
        self.baseline += self.lr * sum(errors) / len(states)
        return float(sum(e ** 2 for e in errors) / len(states))


class GAE:
    """
    Generalized Advantage Estimation
    
    优势函数估计器：
    A_t = Σ_{l=1}^{T-t} (γλ)^l δ_{t+l}
    
    其中 δ_t = r_t + γV(s_{t+1}) - V(s_t)
    
    优点：
    - 可调节的偏差-方差权衡（通过 λ）
    - 低方差策略梯度估计
    - 与任何 RL 算法兼容
    """
    
    def __init__(self, config: GAEConfig = None):
        """
        初始化 GAE
        
        Args:
            config: GAE 配置
        """
        self.config = config or GAEConfig()
        
        # 价值函数
        self.value_function = ValueFunction()
        
        # 统计
        self.stats = {
            'advantages_computed': 0,
            'mean_advantage': 0.0,
            'max_advantage': 0.0,
            'min_advantage': 0.0,
        }
    
    def compute_advantages(
        self,
        rewards: List[float],
        states: List[Dict[str, Any]],
        dones: List[bool] = None,
        values: List[float] = None,
    ) -> Tuple[List[float], List[float]]:
        """
        计算 Advantage 和 Returns
        
        Args:
            rewards: 奖励列表 [r_0, r_1, ..., r_{T-1}]
            states: 状态列表 [s_0, s_1, ..., s_T]
            dones: 终止标志列表 [d_0, d_1, ..., d_{T-1}]
            values: 预计算的价值列表（可选）
        
        Returns:
            Tuple[List[float], List[float]]: (advantages, returns)
        """
        T = len(rewards)
        
        if dones is None:
            dones = [False] * T
        
        if values is None:
            # 使用价值函数估计
            values = [self.value_function.predict(s) for s in states]
        
        # 添加最后一个状态的价值
        if len(values) == T:
            # bootstrap from last state
            values.append(self.value_function.predict(states[-1]) if T > 0 else 0.0)
        
        # 计算 TD errors δ_t = r_t + γV(s_{t+1}) - V(s_t)
        td_errors = []
        for t in range(T):
            gamma = self.config.gamma
            next_value = values[t + 1] if t + 1 < len(values) else 0.0
            
            # 如果终止，next_value = 0
            if t < len(dones) and dones[t]:
                next_value = 0.0
            
            delta = rewards[t] + gamma * next_value - values[t]
            td_errors.append(delta)
        
        # GAE: A_t = Σ_{l=0}^{T-t-1} (γλ)^l δ_{t+l}
        advantages = [0.0] * T
        advantage = 0.0
        
        for t in reversed(range(T)):
            gamma_lambda = self.config.gamma * self.config.lam
            
            if t < len(dones) and dones[t]:
                advantage = td_errors[t]
            else:
                advantage = td_errors[t] + gamma_lambda * advantage
            
            advantages[t] = advantage
        
        # 计算 Returns: G_t = A_t + V(s_t)
        returns = [advantages[t] + values[t] for t in range(T)]
        
        # 更新统计
        self.stats['advantages_computed'] += T
        if advantages:
            self.stats['mean_advantage'] = float(np.mean(advantages))
            self.stats['max_advantage'] = float(np.max(advantages))
            self.stats['min_advantage'] = float(np.min(advantages))
        
        # 归一化
        if self.config.normalize and advantages:
            mean = np.mean(advantages)
            std = np.std(advantages)
            if std > 1e-8:
                advantages = [(a - mean) / std for a in advantages]
        
        return advantages, returns
    
    def compute_returns(
        self,
        rewards: List[float],
        dones: List[bool] = None,
        gamma: float = None,
    ) -> List[float]:
        """
        计算折扣回报（不估计 Advantage）
        
        Args:
            rewards: 奖励列表
            dones: 终止标志列表
            gamma: 折扣因子
        
        Returns:
            List[float]: 回报列表
        """
        gamma = gamma or self.config.gamma
        
        if dones is None:
            dones = [False] * len(rewards)
        
        returns = []
        G = 0.0
        
        for t in reversed(range(len(rewards))):
            G = rewards[t] + gamma * G * (1 - dones[t])
            returns.insert(0, G)
        
        return returns
    
    def update_value_function(
        self,
        states: List[Dict[str, Any]],
        returns: List[float],
    ) -> float:
        """
        更新价值函数
        
        Args:
            states: 状态列表
            returns: 回报列表
        
        Returns:
            float: 损失
        """
        return self.value_function.update(states, returns)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            'value_function_params': self.value_function.weights.shape[0],
        }


def compute_gae(
    rewards: List[float],
    values: List[float],
    dones: List[bool],
    gamma: float = 0.99,
    lam: float = 0.95,
) -> Tuple[List[float], List[float]]:
    """
    便捷函数：计算 GAE
    
    Args:
        rewards: 奖励
        values: 状态价值
        dones: 终止标志
        gamma: 折扣因子
        lam: GAE lambda
    
    Returns:
        Tuple[List[float], List[float]]: (advantages, returns)
    """
    gae = GAE(GAEConfig(gamma=gamma, lam=lam, normalize=False))
    return gae.compute_advantages(rewards, values=[], states=[], dones=dones)


class GAEWithBaseline(GAE):
    """
    带基线的 GAE
    
    使用 reward-to-go 作为基线
    """
    
    def compute_advantages(
        self,
        rewards: List[float],
        states: List[Dict[str, Any]],
        dones: List[bool] = None,
        values: List[float] = None,
    ) -> Tuple[List[float], List[float]]:
        """
        计算 Advantage（使用 reward-to-go 作为基线）
        """
        # 首先计算 reward-to-go
        reward_to_go = self.compute_returns(rewards, dones)
        
        # 使用 reward-to-go 作为基线
        advantages = []
        for t in range(len(rewards)):
            baseline = reward_to_go[t]
            adv = reward_to_go[t] - baseline
            advantages.append(adv)
        
        returns = reward_to_go
        
        # 归一化
        if self.config.normalize and advantages:
            mean = np.mean(advantages)
            std = np.std(advantages)
            if std > 1e-8:
                advantages = [(a - mean) / std for a in advantages]
        
        return advantages, returns
