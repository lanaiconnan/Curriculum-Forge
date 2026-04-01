"""测试 Chains - 可组合的处理链

测试内容：
1. BaseChain 基础功能
2. SequentialChain 顺序执行
3. TransformChain 数据转换
4. ConditionalChain 条件分支
5. ConversationChain 对话处理
6. RetrievalChain 检索增强
7. ParallelChain 并行执行
8. LoopChain 循环执行
9. TrainingChain 训练流程
10. ChainManager 管理器
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.chains import (
    BaseChain,
    SequentialChain,
    TransformChain,
    ConditionalChain,
    ConversationChain,
    RetrievalChain,
    ParallelChain,
    LoopChain,
    TrainingChain,
    ChainManager,
    ChainResult,
    ChainStatus,
)


class TestChainResult:
    """ChainResult 测试"""
    
    def test_creation(self):
        result = ChainResult(
            chain_name="test",
            status=ChainStatus.COMPLETED,
            input_data={'a': 1},
            output_data={'b': 2},
        )
        assert result.chain_name == "test"
        assert result.status == ChainStatus.COMPLETED
    
    def test_to_dict(self):
        result = ChainResult(
            chain_name="test",
            status=ChainStatus.COMPLETED,
            input_data={},
        )
        d = result.to_dict()
        assert d['chain_name'] == "test"
        assert d['status'] == ChainStatus.COMPLETED


class TestTransformChain:
    """TransformChain 测试"""
    
    def test_simple_transform(self):
        chain = TransformChain(
            transform_fn=lambda d: {'result': d['x'] * 2},
            name="Double",
        )
        result = chain.run({'x': 5})
        
        assert result.status == ChainStatus.COMPLETED
        assert result.output_data['result'] == 10
    
    def test_transform_with_error(self):
        chain = TransformChain(
            transform_fn=lambda d: d['nonexistent'],
            name="Error",
        )
        result = chain.run({})
        
        assert result.status == ChainStatus.FAILED
        assert result.error != ""


class TestSequentialChain:
    """SequentialChain 测试"""
    
    @pytest.fixture
    def chain(self):
        seq = SequentialChain(name="TestSeq")
        seq.add_chain(TransformChain(lambda d: {'step1': True}, "Step1"))
        seq.add_chain(TransformChain(lambda d: {'step2': True, **d}, "Step2"))
        return seq
    
    def test_execution(self, chain):
        result = chain.run({'input': 'data'})
        
        assert result.status == ChainStatus.COMPLETED
        assert result.output_data['step1'] is True
        assert result.output_data['step2'] is True
    
    def test_chain_failure_stops_sequence(self):
        seq = SequentialChain(name="FailSeq")
        seq.add_chain(TransformChain(lambda d: {'step1': True}, "Step1"))
        seq.add_chain(TransformChain(lambda d: d['nonexistent'], "Fail"))
        seq.add_chain(TransformChain(lambda d: {'step3': True}, "Step3"))
        
        result = seq.run({})
        
        assert result.status == ChainStatus.FAILED
        assert 'step3' not in result.output_data
    
    def test_empty_chain(self):
        seq = SequentialChain()
        result = seq.run({'a': 1})
        
        assert result.status == ChainStatus.COMPLETED


class TestConditionalChain:
    """ConditionalChain 测试"""
    
    @pytest.fixture
    def chain(self):
        return ConditionalChain(
            condition_fn=lambda d: d.get('score', 0) > 0.5,
            true_chain=TransformChain(lambda d: {'result': 'pass'}, "Pass"),
            false_chain=TransformChain(lambda d: {'result': 'fail'}, "Fail"),
            name="ScoreCheck",
        )
    
    def test_true_branch(self, chain):
        result = chain.run({'score': 0.8})
        
        assert result.status == ChainStatus.COMPLETED
        assert result.output_data['result'] == 'pass'
    
    def test_false_branch(self, chain):
        result = chain.run({'score': 0.3})
        
        assert result.status == ChainStatus.COMPLETED
        assert result.output_data['result'] == 'fail'
    
    def test_no_false_chain(self):
        chain = ConditionalChain(
            condition_fn=lambda d: d.get('flag', False),
            true_chain=TransformChain(lambda d: {'done': True}, "Done"),
        )
        
        result = chain.run({'flag': False})
        assert result.status == ChainStatus.SKIPPED


class TestConversationChain:
    """ConversationChain 测试"""
    
    @pytest.fixture
    def chain(self):
        return ConversationChain(name="TestConv", max_history=3)
    
    def test_single_message(self, chain):
        result = chain.run({'message': 'Hello', 'role': 'user'})
        
        assert result.status == ChainStatus.COMPLETED
        assert 'response' in result.output_data
    
    def test_history_tracking(self, chain):
        chain.run({'message': 'Msg1', 'role': 'user'})
        chain.run({'message': 'Msg2', 'role': 'user'})
        chain.run({'message': 'Msg3', 'role': 'user'})
        
        history = chain.get_history()
        assert len(history) == 3
    
    def test_history_limit(self, chain):
        # max_history = 3
        for i in range(5):
            chain.run({'message': f'Msg{i}', 'role': 'user'})
        
        history = chain.get_history()
        assert len(history) == 3
    
    def test_clear_history(self, chain):
        chain.run({'message': 'Test', 'role': 'user'})
        chain.clear_history()
        
        assert len(chain.get_history()) == 0


class TestRetrievalChain:
    """RetrievalChain 测试"""
    
    def test_with_custom_retriever(self):
        def retriever(query):
            return [{'content': f"Result for {query}", 'score': 0.9}]
        
        chain = RetrievalChain(retriever=retriever, top_k=5)
        result = chain.run({'query': 'test query'})
        
        assert result.status == ChainStatus.COMPLETED
        assert result.output_data['count'] == 1
    
    def test_default_retriever(self):
        chain = RetrievalChain(name="DefaultRetrieval")
        result = chain.run({'query': 'test'})
        
        assert result.status == ChainStatus.COMPLETED


class TestParallelChain:
    """ParallelChain 测试"""
    
    def test_parallel_execution(self):
        parallel = ParallelChain(name="TestParallel")
        parallel.add_chain(TransformChain(lambda d: {'a': 1}, "A"))
        parallel.add_chain(TransformChain(lambda d: {'b': 2}, "B"))
        parallel.add_chain(TransformChain(lambda d: {'c': 3}, "C"))
        
        result = parallel.run({'input': 'data'})
        
        assert result.status == ChainStatus.COMPLETED
        assert result.output_data['a'] == 1
        assert result.output_data['b'] == 2
        assert result.output_data['c'] == 3
    
    def test_parallel_with_failure(self):
        parallel = ParallelChain(name="FailParallel")
        parallel.add_chain(TransformChain(lambda d: {'a': 1}, "A"))
        parallel.add_chain(TransformChain(lambda d: d['nonexistent'], "Fail"))
        
        result = parallel.run({})
        
        # 有失败，整体状态为 FAILED
        assert result.status == ChainStatus.FAILED
    
    def test_custom_merge(self):
        def merge_fn(outputs):
            return {'merged': outputs}
        
        parallel = ParallelChain(merge_fn=merge_fn)
        parallel.add_chain(TransformChain(lambda d: {'x': 1}, "X"))
        
        result = parallel.run({})
        assert 'merged' in result.output_data


class TestLoopChain:
    """LoopChain 测试"""
    
    def test_loop_until_condition(self):
        inner = TransformChain(lambda d: {'count': d.get('count', 0) + 1}, "Counter")
        
        loop = LoopChain(
            chain=inner,
            condition_fn=lambda d: d.get('count', 0) >= 3,
            max_iterations=10,
        )
        
        result = loop.run({})
        
        assert result.status == ChainStatus.COMPLETED
        assert result.output_data['count'] >= 3
    
    def test_max_iterations(self):
        inner = TransformChain(lambda d: {'count': d.get('count', 0) + 1}, "Counter")
        
        loop = LoopChain(
            chain=inner,
            condition_fn=lambda d: False,  # 永不满足
            max_iterations=5,
        )
        
        result = loop.run({})
        
        # 达到最大迭代次数，状态为 FAILED
        assert result.status == ChainStatus.FAILED
        assert result.metadata['iterations'] == 5


class TestChainManager:
    """ChainManager 测试"""
    
    @pytest.fixture
    def manager(self):
        mgr = ChainManager()
        mgr.register(TransformChain(lambda d: d, "ChainA"))
        mgr.register(TransformChain(lambda d: {'result': 'ok'}, "ChainB"))
        return mgr
    
    def test_register_and_get(self, manager):
        chain = manager.get("ChainA")
        assert chain is not None
        assert chain.name == "ChainA"
    
    def test_get_nonexistent(self, manager):
        chain = manager.get("Nonexistent")
        assert chain is None
    
    def test_run_chain(self, manager):
        result = manager.run("ChainB", {'input': 'test'})
        
        assert result.status == ChainStatus.COMPLETED
        assert result.output_data['result'] == 'ok'
    
    def test_run_nonexistent(self, manager):
        result = manager.run("Nonexistent", {})
        
        assert result.status == ChainStatus.FAILED
    
    def test_list_chains(self, manager):
        chains = manager.list_chains()
        
        assert len(chains) == 2
        names = [c['name'] for c in chains]
        assert 'ChainA' in names
        assert 'ChainB' in names


class TestTrainingChain:
    """TrainingChain 测试"""
    
    def test_creation(self):
        chain = TrainingChain(name="TestTraining")
        
        assert chain.name == "TestTraining"
        assert len(chain.chains) == 5  # 5 个训练步骤
    
    def test_run_without_agents(self):
        chain = TrainingChain(name="SimpleTraining")
        result = chain.run({'results_tsv': ''})
        
        assert result.status == ChainStatus.COMPLETED
    
    def test_with_agent_a(self, tmp_path):
        from agent_a.generator import AgentA
        
        agent_a = AgentA(workspace=str(tmp_path))
        chain = TrainingChain(agent_a=agent_a, name="TrainingWithA")
        
        result = chain.run({'results_tsv': ''})
        
        assert result.status == ChainStatus.COMPLETED


class TestChainIntegration:
    """Chain 集成测试"""
    
    def test_complex_pipeline(self):
        """复杂管道：顺序 + 条件 + 并行"""
        
        # 并行获取数据
        fetch_parallel = ParallelChain(name="FetchParallel")
        fetch_parallel.add_chain(TransformChain(lambda d: {'data1': 'fetched'}, "Fetch1"))
        fetch_parallel.add_chain(TransformChain(lambda d: {'data2': 'fetched'}, "Fetch2"))
        
        # 条件处理
        process_conditional = ConditionalChain(
            condition_fn=lambda d: d.get('process', False),
            true_chain=TransformChain(lambda d: {'processed': True}, "Process"),
            false_chain=TransformChain(lambda d: {'skipped': True}, "Skip"),
        )
        
        # 组合
        pipeline = SequentialChain(name="ComplexPipeline")
        pipeline.add_chain(fetch_parallel)
        pipeline.add_chain(process_conditional)
        
        result = pipeline.run({'process': True})
        
        assert result.status == ChainStatus.COMPLETED
        assert result.output_data['processed'] is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
