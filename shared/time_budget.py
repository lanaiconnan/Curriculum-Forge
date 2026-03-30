"""时间预算配置"""

from dataclasses import dataclass


@dataclass
class TimeBudget:
    """时间预算配置
    
    借鉴 autoresearch 的固定时间预算理念：
    所有实验使用相同时间预算，确保公平对比。
    """
    
    # 单次实验的最大时间（秒）
    experiment: int = 300  # 5 分钟
    
    # 单次迭代的最大时间（秒）
    iteration: int = 1800  # 30 分钟
    
    # 评估单个结果的时间（秒）
    evaluation: int = 60  # 1 分钟
    
    # 系统开销时间（秒）
    overhead: int = 60  # 1 分钟
    
    # 是否启用时间预算
    enabled: bool = True
    
    # 超时策略
    # - 'warn': 超时警告但继续
    # - 'skip': 跳过超时的实验
    # - 'terminate': 终止训练
    timeout_policy: str = 'warn'


class TimeBudgetManager:
    """时间预算管理器"""
    
    def __init__(self, config: TimeBudget = None):
        self.config = config or TimeBudget()
        self._start_time = None
        self._experiment_start = None
    
    def start_training(self):
        """开始训练计时"""
        import time
        self._start_time = time.time()
        print(f"⏱ Training started at {self._format_time()}")
        print(f"   Time budget: {self.config.iteration}s per iteration")
    
    def start_experiment(self):
        """开始实验计时"""
        import time
        self._experiment_start = time.time()
    
    def check_experiment_timeout(self) -> bool:
        """检查实验是否超时
        
        Returns:
            bool: 是否超时
        """
        if not self.config.enabled:
            return False
        
        import time
        elapsed = time.time() - self._experiment_start
        
        if elapsed > self.config.experiment:
            print(f"   ⏱ Experiment timeout ({elapsed:.1f}s > {self.config.experiment}s)")
            return True
        
        return False
    
    def get_experiment_elapsed(self) -> float:
        """获取当前实验已用时间"""
        import time
        if self._experiment_start is None:
            return 0.0
        return time.time() - self._experiment_start
    
    def check_iteration_timeout(self) -> bool:
        """检查迭代是否超时
        
        Returns:
            bool: 是否超时
        """
        if not self.config.enabled:
            return False
        
        import time
        elapsed = time.time() - self._start_time
        
        if elapsed > self.config.iteration:
            print(f"   ⏱ Iteration timeout ({elapsed:.1f}s > {self.config.iteration}s)")
            return True
        
        return False
    
    def get_iteration_elapsed(self) -> float:
        """获取当前迭代已用时间"""
        import time
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time
    
    def format_elapsed(self) -> str:
        """格式化已用时间"""
        elapsed = self.get_iteration_elapsed()
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        return f"{minutes:02d}:{seconds:02d}"
    
    def _format_time(self):
        """格式化当前时间"""
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")
    
    def reset(self):
        """重置计时器"""
        import time
        self._start_time = None
        self._experiment_start = None


# 全局时间预算实例
_default_budget = TimeBudget()


def get_time_budget() -> TimeBudget:
    """获取全局时间预算实例"""
    return _default_budget


def set_time_budget(config: TimeBudget):
    """设置全局时间预算"""
    global _default_budget
    _default_budget = config
