"""Experience Buffer - 经验回放缓冲

来自 RL 最佳实践：
- 存储训练经验
- 优先级经验回放
- 批量采样
- 经验去重
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from collections import deque
import random
import heapq
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class Experience:
    """单条经验"""
    state: Dict[str, Any]          # 状态（任务描述、上下文）
    action: Dict[str, Any]         # 动作（工具选择、参数）
    reward: float                  # 奖励
    next_state: Dict[str, Any]     # 下一状态
    done: bool                     # 是否终止
    info: Dict[str, Any] = field(default_factory=dict)  # 额外信息
    timestamp: str = None
    priority: float = 1.0          # 优先级（用于优先级回放）
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'state': self.state,
            'action': self.action,
            'reward': self.reward,
            'next_state': self.next_state,
            'done': self.done,
            'info': self.info,
            'timestamp': self.timestamp,
            'priority': self.priority,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Experience':
        return cls(
            state=data['state'],
            action=data['action'],
            reward=data['reward'],
            next_state=data.get('next_state', {}),
            done=data.get('done', False),
            info=data.get('info', {}),
            timestamp=data.get('timestamp'),
            priority=data.get('priority', 1.0),
        )


class ExperienceBuffer:
    """
    经验回放缓冲
    
    功能：
    1. 存储训练经验
    2. 优先级经验回放（PER）
    3. 批量采样
    4. 经验去重
    5. 容量管理
    """
    
    def __init__(
        self,
        capacity: int = 10000,
        use_priority: bool = True,
        dedup_threshold: float = 0.95,
    ):
        """
        初始化经验缓冲
        
        Args:
            capacity: 最大容量
            use_priority: 是否使用优先级回放
            dedup_threshold: 去重相似度阈值
        """
        self.capacity = capacity
        self.use_priority = use_priority
        self.dedup_threshold = dedup_threshold
        
        # 存储
        self.buffer: deque = deque(maxlen=capacity)
        
        # 优先级堆（如果启用）
        self.priority_heap: List[Tuple[float, int, Experience]] = []
        
        # 统计
        self.stats = {
            'total_added': 0,
            'total_sampled': 0,
            'duplicates_rejected': 0,
        }
    
    def add(
        self,
        experience: Experience,
        check_duplicate: bool = True
    ) -> bool:
        """
        添加经验
        
        Args:
            experience: 经验对象
            check_duplicate: 是否检查重复
        
        Returns:
            bool: 是否成功添加
        """
        # 检查重复
        if check_duplicate and self._is_duplicate(experience):
            self.stats['duplicates_rejected'] += 1
            return False
        
        # 添加到缓冲
        self.buffer.append(experience)
        
        # 添加到优先级堆
        if self.use_priority:
            idx = len(self.buffer) - 1
            heapq.heappush(
                self.priority_heap,
                (-experience.priority, idx, experience)
            )
        
        self.stats['total_added'] += 1
        return True
    
    def add_batch(self, experiences: List[Experience]) -> int:
        """批量添加经验"""
        added = 0
        for exp in experiences:
            if self.add(exp):
                added += 1
        return added
    
    def sample(
        self,
        batch_size: int,
        use_priority: bool = None
    ) -> List[Experience]:
        """
        采样经验
        
        Args:
            batch_size: 批量大小
            use_priority: 是否使用优先级采样（覆盖默认）
        
        Returns:
            List[Experience]: 采样的经验列表
        """
        use_priority = use_priority if use_priority is not None else self.use_priority
        
        if len(self.buffer) == 0:
            return []
        
        batch_size = min(batch_size, len(self.buffer))
        
        if use_priority and self.priority_heap:
            # 优先级采样
            samples = []
            temp_heap = []
            
            for _ in range(batch_size):
                if not self.priority_heap:
                    break
                
                priority, idx, exp = heapq.heappop(self.priority_heap)
                samples.append(exp)
                temp_heap.append((priority, idx, exp))
            
            # 放回堆中
            for item in temp_heap:
                heapq.heappush(self.priority_heap, item)
            
            result = samples
        else:
            # 均匀随机采样
            result = random.sample(list(self.buffer), batch_size)
        
        self.stats['total_sampled'] += len(result)
        return result
    
    def get_recent(self, n: int = 10) -> List[Experience]:
        """获取最近的 n 条经验"""
        return list(self.buffer)[-n:]
    
    def get_by_reward(self, top_k: int = 10) -> List[Experience]:
        """获取奖励最高的经验"""
        sorted_exp = sorted(self.buffer, key=lambda x: x.reward, reverse=True)
        return sorted_exp[:top_k]
    
    def clear(self):
        """清空缓冲"""
        self.buffer.clear()
        self.priority_heap.clear()
    
    def _is_duplicate(self, experience: Experience) -> bool:
        """检查是否重复"""
        for existing in self.buffer:
            similarity = self._compute_similarity(experience, existing)
            if similarity >= self.dedup_threshold:
                return True
        return False
    
    def _compute_similarity(self, exp1: Experience, exp2: Experience) -> float:
        """计算经验相似度"""
        # 简单的状态相似度
        state1 = exp1.state.get('description', '')
        state2 = exp2.state.get('description', '')
        
        if state1 == state2:
            return 1.0
        
        # Jaccard 相似度
        words1 = set(state1.lower().split())
        words2 = set(state2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0.0
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            'buffer_size': len(self.buffer),
            'capacity': self.capacity,
            'fill_ratio': len(self.buffer) / self.capacity,
        }
    
    def save(self, filepath: str):
        """保存到文件"""
        import json
        
        data = {
            'experiences': [exp.to_dict() for exp in self.buffer],
            'stats': self.stats,
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def load(self, filepath: str):
        """从文件加载"""
        import json
        
        if not os.path.exists(filepath):
            return
        
        with open(filepath) as f:
            data = json.load(f)
        
        self.buffer.clear()
        self.priority_heap.clear()
        
        for exp_data in data.get('experiences', []):
            exp = Experience.from_dict(exp_data)
            self.buffer.append(exp)
            
            if self.use_priority:
                idx = len(self.buffer) - 1
                heapq.heappush(
                    self.priority_heap,
                    (-exp.priority, idx, exp)
                )
        
        self.stats.update(data.get('stats', {}))


class PrioritizedExperienceBuffer(ExperienceBuffer):
    """
    优先级经验回放缓冲
    
    基于 TD-error 的优先级
    """
    
    def __init__(
        self,
        capacity: int = 10000,
        alpha: float = 0.6,     # 优先级指数
        beta: float = 0.4,      # 重要性采样指数
        beta_increment: float = 0.001,
    ):
        super().__init__(capacity, use_priority=True)
        
        self.alpha = alpha
        self.beta = beta
        self.beta_increment = beta_increment
        self.max_priority = 1.0
    
    def add(self, experience: Experience, check_duplicate: bool = True) -> bool:
        """添加经验（自动设置优先级）"""
        experience.priority = self.max_priority
        return super().add(experience, check_duplicate)
    
    def sample_with_weights(
        self,
        batch_size: int
    ) -> Tuple[List[Experience], List[float]]:
        """
        采样并返回重要性采样权重
        
        Returns:
            Tuple[List[Experience], List[float]]: (经验列表, 权重列表)
        """
        samples = self.sample(batch_size, use_priority=True)
        
        if not samples:
            return [], []
        
        # 计算重要性采样权重
        weights = []
        for exp in samples:
            # p_i = priority^alpha
            prob = (exp.priority ** self.alpha) / self._get_total_priority()
            # w_i = (N * p_i)^(-beta)
            weight = (len(self.buffer) * prob) ** (-self.beta)
            weights.append(weight)
        
        # 归一化权重
        max_weight = max(weights) if weights else 1.0
        weights = [w / max_weight for w in weights]
        
        # 增加 beta
        self.beta = min(1.0, self.beta + self.beta_increment)
        
        return samples, weights
    
    def update_priorities(self, indices: List[int], td_errors: List[float]):
        """更新优先级（基于 TD-error）"""
        for idx, td_error in zip(indices, td_errors):
            if 0 <= idx < len(self.buffer):
                priority = (abs(td_error) + 1e-6) ** self.alpha
                self.buffer[idx].priority = priority
                self.max_priority = max(self.max_priority, priority)
    
    def _get_total_priority(self) -> float:
        """获取总优先级"""
        return sum(exp.priority ** self.alpha for exp in self.buffer)
