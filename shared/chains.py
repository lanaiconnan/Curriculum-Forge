"""Chains - 可组合的处理链

来自 Flowise / LangChain 的灵感：
- Chain 是可组合的处理单元
- 支持顺序执行、条件分支、并行执行
- 可用于 RL 训练流程、数据处理管道

核心 Chain 类型：
1. SequentialChain - 顺序执行
2. ConversationChain - 对话处理
3. RetrievalChain - 检索增强
4. TransformChain - 数据转换
5. ConditionalChain - 条件分支
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable, Union
from datetime import datetime
from abc import ABC, abstractmethod
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ChainStatus:
    """Chain 执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ChainResult:
    """Chain 执行结果"""
    chain_name: str
    status: str
    input_data: Dict[str, Any]
    output_data: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'chain_name': self.chain_name,
            'status': self.status,
            'input_data': self.input_data,
            'output_data': self.output_data,
            'error': self.error,
            'duration_ms': self.duration_ms,
            'metadata': self.metadata,
        }


class BaseChain(ABC):
    """
    Chain 基类
    
    所有 Chain 都需要实现 execute 方法
    """
    
    def __init__(self, name: str = None, description: str = ""):
        self.name = name or self.__class__.__name__
        self.description = description
        self.status = ChainStatus.PENDING
        self.last_result: Optional[ChainResult] = None
    
    @abstractmethod
    def execute(self, input_data: Dict[str, Any]) -> ChainResult:
        """
        执行 Chain
        
        Args:
            input_data: 输入数据
        
        Returns:
            ChainResult: 执行结果
        """
        pass
    
    def run(self, input_data: Dict[str, Any]) -> ChainResult:
        """
        运行 Chain（带状态管理）
        """
        self.status = ChainStatus.RUNNING
        start_time = datetime.now()
        
        try:
            result = self.execute(input_data)
            self.status = result.status
        except Exception as e:
            result = ChainResult(
                chain_name=self.name,
                status=ChainStatus.FAILED,
                input_data=input_data,
                error=str(e),
            )
            self.status = ChainStatus.FAILED
        
        # 计算耗时
        duration = (datetime.now() - start_time).total_seconds() * 1000
        result.duration_ms = duration
        self.last_result = result
        
        return result
    
    def get_info(self) -> Dict[str, Any]:
        """获取 Chain 信息"""
        return {
            'name': self.name,
            'description': self.description,
            'status': self.status,
            'type': self.__class__.__name__,
        }


class SequentialChain(BaseChain):
    """
    顺序执行链
    
    按顺序执行多个 Chain，前一个的输出作为后一个的输入
    
    示例：
        chain = SequentialChain([
            LoadDataChain(),
            ProcessChain(),
            SaveChain(),
        ])
        result = chain.run({'data_path': '/path/to/data'})
    """
    
    def __init__(
        self,
        chains: List[BaseChain] = None,
        name: str = None,
    ):
        super().__init__(name=name or "SequentialChain")
        self.chains = chains or []
    
    def add_chain(self, chain: BaseChain):
        """添加 Chain"""
        self.chains.append(chain)
    
    def execute(self, input_data: Dict[str, Any]) -> ChainResult:
        """顺序执行所有 Chain"""
        current_data = input_data.copy()
        results = []
        
        for chain in self.chains:
            result = chain.run(current_data)
            results.append(result)
            
            if result.status == ChainStatus.FAILED:
                return ChainResult(
                    chain_name=self.name,
                    status=ChainStatus.FAILED,
                    input_data=input_data,
                    output_data=current_data,
                    error=f"Chain {chain.name} failed: {result.error}",
                    metadata={'chain_results': [r.to_dict() for r in results]},
                )
            
            # 更新数据，传递给下一个 Chain
            current_data.update(result.output_data)
        
        return ChainResult(
            chain_name=self.name,
            status=ChainStatus.COMPLETED,
            input_data=input_data,
            output_data=current_data,
            metadata={'chain_results': [r.to_dict() for r in results]},
        )


class TransformChain(BaseChain):
    """
    转换链
    
    使用自定义函数转换数据
    """
    
    def __init__(
        self,
        transform_fn: Callable[[Dict], Dict],
        name: str = None,
        description: str = "",
    ):
        super().__init__(name=name or "TransformChain", description=description)
        self.transform_fn = transform_fn
    
    def execute(self, input_data: Dict[str, Any]) -> ChainResult:
        """执行转换"""
        try:
            output_data = self.transform_fn(input_data)
            return ChainResult(
                chain_name=self.name,
                status=ChainStatus.COMPLETED,
                input_data=input_data,
                output_data=output_data,
            )
        except Exception as e:
            return ChainResult(
                chain_name=self.name,
                status=ChainStatus.FAILED,
                input_data=input_data,
                error=str(e),
            )


class ConditionalChain(BaseChain):
    """
    条件分支链
    
    根据条件选择不同的分支执行
    
    示例：
        chain = ConditionalChain(
            condition_fn=lambda data: data.get('score', 0) > 0.5,
            true_chain=SuccessChain(),
            false_chain=RetryChain(),
        )
    """
    
    def __init__(
        self,
        condition_fn: Callable[[Dict], bool],
        true_chain: BaseChain,
        false_chain: BaseChain = None,
        name: str = None,
    ):
        super().__init__(name=name or "ConditionalChain")
        self.condition_fn = condition_fn
        self.true_chain = true_chain
        self.false_chain = false_chain
    
    def execute(self, input_data: Dict[str, Any]) -> ChainResult:
        """执行条件分支"""
        try:
            condition_result = self.condition_fn(input_data)
        except Exception as e:
            return ChainResult(
                chain_name=self.name,
                status=ChainStatus.FAILED,
                input_data=input_data,
                error=f"Condition evaluation failed: {e}",
            )
        
        if condition_result:
            result = self.true_chain.run(input_data)
        elif self.false_chain:
            result = self.false_chain.run(input_data)
        else:
            # 没有 false_chain，跳过
            result = ChainResult(
                chain_name=self.name,
                status=ChainStatus.SKIPPED,
                input_data=input_data,
                output_data=input_data,
            )
        
        return ChainResult(
            chain_name=self.name,
            status=result.status,
            input_data=input_data,
            output_data=result.output_data,
            error=result.error,
            metadata={'condition_result': condition_result, 'branch_taken': 'true' if condition_result else 'false'},
        )


class ConversationChain(BaseChain):
    """
    对话处理链
    
    处理对话消息，支持上下文
    """
    
    def __init__(
        self,
        name: str = None,
        max_history: int = 10,
    ):
        super().__init__(name=name or "ConversationChain")
        self.max_history = max_history
        self.history: List[Dict[str, Any]] = []
    
    def execute(self, input_data: Dict[str, Any]) -> ChainResult:
        """处理对话消息"""
        message = input_data.get('message', '')
        role = input_data.get('role', 'user')
        
        # 添加到历史
        self.history.append({
            'role': role,
            'message': message,
            'timestamp': datetime.now().isoformat(),
        })
        
        # 保持历史大小
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
        
        # 生成响应（简化版，实际可接入 LLM）
        response = self._generate_response(message)
        
        return ChainResult(
            chain_name=self.name,
            status=ChainStatus.COMPLETED,
            input_data=input_data,
            output_data={
                'response': response,
                'history_length': len(self.history),
            },
        )
    
    def _generate_response(self, message: str) -> str:
        """生成响应（子类可覆盖）"""
        return f"Processed: {message[:100]}"
    
    def get_history(self) -> List[Dict[str, Any]]:
        """获取对话历史"""
        return self.history
    
    def clear_history(self):
        """清空历史"""
        self.history.clear()


class RetrievalChain(BaseChain):
    """
    检索增强链
    
    从知识库检索相关信息
    """
    
    def __init__(
        self,
        retriever: Callable[[str], List[Dict]] = None,
        name: str = None,
        top_k: int = 5,
    ):
        super().__init__(name=name or "RetrievalChain")
        self.retriever = retriever or self._default_retriever
        self.top_k = top_k
    
    def execute(self, input_data: Dict[str, Any]) -> ChainResult:
        """执行检索"""
        query = input_data.get('query', '')
        
        try:
            results = self.retriever(query)[:self.top_k]
            
            return ChainResult(
                chain_name=self.name,
                status=ChainStatus.COMPLETED,
                input_data=input_data,
                output_data={
                    'query': query,
                    'results': results,
                    'count': len(results),
                },
            )
        except Exception as e:
            return ChainResult(
                chain_name=self.name,
                status=ChainStatus.FAILED,
                input_data=input_data,
                error=str(e),
            )
    
    def _default_retriever(self, query: str) -> List[Dict]:
        """默认检索器（返回空结果）"""
        return [{'content': f"No results for: {query}", 'score': 0.0}]


class ParallelChain(BaseChain):
    """
    并行执行链
    
    同时执行多个 Chain，合并结果
    """
    
    def __init__(
        self,
        chains: List[BaseChain] = None,
        name: str = None,
        merge_fn: Callable[[List[Dict]], Dict] = None,
    ):
        super().__init__(name=name or "ParallelChain")
        self.chains = chains or []
        self.merge_fn = merge_fn or self._default_merge
    
    def add_chain(self, chain: BaseChain):
        """添加 Chain"""
        self.chains.append(chain)
    
    def execute(self, input_data: Dict[str, Any]) -> ChainResult:
        """并行执行所有 Chain"""
        results = []
        
        for chain in self.chains:
            result = chain.run(input_data)
            results.append(result)
        
        # 合并结果
        merged_output = self.merge_fn([r.output_data for r in results])
        
        # 检查是否有失败
        failed = [r for r in results if r.status == ChainStatus.FAILED]
        status = ChainStatus.FAILED if failed else ChainStatus.COMPLETED
        
        return ChainResult(
            chain_name=self.name,
            status=status,
            input_data=input_data,
            output_data=merged_output,
            metadata={'chain_results': [r.to_dict() for r in results]},
        )
    
    def _default_merge(self, outputs: List[Dict]) -> Dict:
        """默认合并策略"""
        merged = {}
        for output in outputs:
            merged.update(output)
        return merged


class LoopChain(BaseChain):
    """
    循环执行链
    
    重复执行直到满足条件
    """
    
    def __init__(
        self,
        chain: BaseChain,
        condition_fn: Callable[[Dict], bool],
        max_iterations: int = 10,
        name: str = None,
    ):
        super().__init__(name=name or "LoopChain")
        self.chain = chain
        self.condition_fn = condition_fn
        self.max_iterations = max_iterations
    
    def execute(self, input_data: Dict[str, Any]) -> ChainResult:
        """循环执行"""
        current_data = input_data.copy()
        iterations = 0
        results = []
        
        while iterations < self.max_iterations:
            result = self.chain.run(current_data)
            results.append(result)
            
            if result.status == ChainStatus.FAILED:
                break
            
            current_data.update(result.output_data)
            iterations += 1
            
            # 检查终止条件
            if self.condition_fn(current_data):
                break
        
        return ChainResult(
            chain_name=self.name,
            status=ChainStatus.COMPLETED if iterations < self.max_iterations else ChainStatus.FAILED,
            input_data=input_data,
            output_data=current_data,
            metadata={'iterations': iterations, 'chain_results': [r.to_dict() for r in results]},
        )


# ==================== RL 训练专用 Chain ====================

class TrainingChain(SequentialChain):
    """
    RL 训练链
    
    专门用于强化学习训练流程：
    1. 分析进度
    2. 生成环境
    3. 执行实验
    4. 计算奖励
    5. 更新策略
    """
    
    def __init__(
        self,
        agent_a=None,
        agent_b=None,
        trainer=None,
        name: str = "TrainingChain",
    ):
        super().__init__(name=name)
        self.agent_a = agent_a
        self.agent_b = agent_b
        self.trainer = trainer
        
        # 构建训练子链
        self._build_training_chains()
    
    def _build_training_chains(self):
        """构建训练子链"""
        # 1. 分析进度
        self.add_chain(TransformChain(
            transform_fn=self._analyze_progress,
            name="AnalyzeProgress",
        ))
        
        # 2. 生成环境
        self.add_chain(TransformChain(
            transform_fn=self._generate_environment,
            name="GenerateEnvironment",
        ))
        
        # 3. 执行实验
        self.add_chain(TransformChain(
            transform_fn=self._run_experiments,
            name="RunExperiments",
        ))
        
        # 4. 计算奖励
        self.add_chain(TransformChain(
            transform_fn=self._compute_rewards,
            name="ComputeRewards",
        ))
        
        # 5. 更新策略
        self.add_chain(TransformChain(
            transform_fn=self._update_policy,
            name="UpdatePolicy",
        ))
    
    def _analyze_progress(self, data: Dict) -> Dict:
        """分析进度"""
        if self.agent_a:
            progress = self.agent_a.analyze_progress(data.get('results_tsv', ''))
            return {'progress': progress}
        return {'progress': {'keep_rate': 0.5}}
    
    def _generate_environment(self, data: Dict) -> Dict:
        """生成环境"""
        if self.agent_a:
            progress = data.get('progress')
            if progress:
                env = self.agent_a.generate_environment(progress)
                return {'environment': env}
        return {'environment': {'difficulty': 0.5}}
    
    def _run_experiments(self, data: Dict) -> Dict:
        """执行实验"""
        return {'experiments': [], 'experiment_count': 0}
    
    def _compute_rewards(self, data: Dict) -> Dict:
        """计算奖励"""
        if self.trainer:
            experiments = data.get('experiments', [])
            rewards = []
            for exp in experiments:
                reward = self.trainer.reward_calculator.calculate(exp)
                rewards.append(reward)
            return {'rewards': rewards, 'avg_reward': sum(rewards) / len(rewards) if rewards else 0}
        return {'rewards': [], 'avg_reward': 0}
    
    def _update_policy(self, data: Dict) -> Dict:
        """更新策略"""
        if self.trainer:
            result = self.trainer.train_step(data.get('experiments', []))
            return {'training_result': result}
        return {'training_result': {}}


class ChainManager:
    """
    Chain 管理器
    
    管理多个 Chain，支持注册、查找、执行
    """
    
    def __init__(self):
        self.chains: Dict[str, BaseChain] = {}
    
    def register(self, chain: BaseChain):
        """注册 Chain"""
        self.chains[chain.name] = chain
    
    def get(self, name: str) -> Optional[BaseChain]:
        """获取 Chain"""
        return self.chains.get(name)
    
    def run(self, name: str, input_data: Dict[str, Any]) -> ChainResult:
        """运行指定 Chain"""
        chain = self.get(name)
        if chain:
            return chain.run(input_data)
        return ChainResult(
            chain_name=name,
            status=ChainStatus.FAILED,
            input_data=input_data,
            error=f"Chain not found: {name}",
        )
    
    def list_chains(self) -> List[Dict[str, Any]]:
        """列出所有 Chain"""
        return [chain.get_info() for chain in self.chains.values()]
    
    def create_training_pipeline(
        self,
        agent_a=None,
        agent_b=None,
        trainer=None,
    ) -> TrainingChain:
        """创建训练管道"""
        chain = TrainingChain(agent_a, agent_b, trainer)
        self.register(chain)
        return chain
