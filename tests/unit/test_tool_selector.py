"""测试 Tool Selector + ReAct 推理模式

测试内容：
1. 工具选择
2. 参数推断
3. 工具组合建议
4. ReAct 推理链（新增）
5. ReActAgent（新增）
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.tool_selector import ToolSelector, ToolCandidate, ReActStep, ReActAgent


class TestToolSelector:
    """ToolSelector 测试套件"""
    
    @pytest.fixture
    def selector(self):
        return ToolSelector(['git', 'moon', 'memory'])
    
    def test_select_git(self, selector):
        candidates = selector.select("commit and push the code", top_k=3)
        
        names = [c.name for c in candidates]
        assert 'git' in names
        assert candidates[0].name == 'git'
        assert candidates[0].score > 0
    
    def test_select_memory(self, selector):
        candidates = selector.select("save this information to memory", top_k=3)
        
        names = [c.name for c in candidates]
        assert 'memory' in names
    
    def test_select_moon(self, selector):
        candidates = selector.select("query the moon API for data", top_k=3)
        
        names = [c.name for c in candidates]
        assert 'moon' in names
    
    def test_select_multiple(self, selector):
        candidates = selector.select(
            "commit code and save to memory",
            top_k=3
        )
        
        names = [c.name for c in candidates]
        assert len(names) >= 2
    
    def test_select_no_match(self, selector):
        candidates = selector.select("do something completely unrelated xyz", top_k=3)
        
        # 可能返回空或低分候选
        assert isinstance(candidates, list)
    
    def test_select_top_k(self, selector):
        candidates = selector.select("commit to git and save to memory", top_k=1)
        
        assert len(candidates) <= 1
    
    def test_select_scores_sorted(self, selector):
        candidates = selector.select("commit git push memory save", top_k=5)
        
        for i in range(len(candidates) - 1):
            assert candidates[i].score >= candidates[i+1].score
    
    def test_candidate_has_reason(self, selector):
        candidates = selector.select("commit code", top_k=1)
        
        if candidates:
            assert len(candidates[0].reason) > 0


class TestToolInferParams:
    """参数推断测试"""
    
    @pytest.fixture
    def selector(self):
        return ToolSelector(['git', 'moon', 'memory'])
    
    def test_infer_git_commit(self, selector):
        params = selector.infer_params('git', 'commit the changes')
        
        assert 'action' in params
        assert params['action'] == 'commit'
    
    def test_infer_git_push(self, selector):
        params = selector.infer_params('git', 'push to remote')
        
        assert params.get('action') == 'push'
    
    def test_infer_git_branch(self, selector):
        params = selector.infer_params('git', 'switch branch: develop')
        
        assert params.get('branch') == 'develop'
    
    def test_infer_memory_save(self, selector):
        params = selector.infer_params('memory', 'remember this information')
        
        assert params.get('action') == 'save'
    
    def test_infer_memory_recall(self, selector):
        params = selector.infer_params('memory', 'recall previous conversations')
        
        assert params.get('action') == 'load'
    
    def test_infer_moon_query(self, selector):
        params = selector.infer_params('moon', 'search for recent data')
        
        assert 'query' in params


class TestToolCombination:
    """工具组合测试"""
    
    @pytest.fixture
    def selector(self):
        return ToolSelector(['git', 'moon', 'memory'])
    
    def test_suggest_combination(self, selector):
        combo = selector.suggest_combination("commit code and save memory")
        
        assert isinstance(combo, list)
        assert len(combo) >= 1
        
        for name, params in combo:
            assert isinstance(name, str)
            assert isinstance(params, dict)
    
    def test_suggest_empty_task(self, selector):
        combo = selector.suggest_combination("")
        
        assert isinstance(combo, list)


class TestToolSelectorWithCustomTools:
    """自定义工具测试"""
    
    def test_custom_tools(self):
        selector = ToolSelector(['weather', 'calculator'])
        
        # 没有关键词匹配，应该返回空
        candidates = selector.select("do something", top_k=3)
        assert isinstance(candidates, list)
    
    def test_empty_tools(self):
        selector = ToolSelector([])
        
        candidates = selector.select("do something completely unrelated", top_k=3)
        assert isinstance(candidates, list)
        # No matching tools when empty
        assert len(candidates) == 0


class TestReActReasoning:
    """ReAct 推理链测试"""
    
    @pytest.fixture
    def selector(self):
        return ToolSelector(['git', 'moon', 'memory'])
    
    def test_react_reason_git(self, selector):
        """测试 Git 任务的 ReAct 推理"""
        steps = selector.react_reason('commit the code to git')
        
        assert len(steps) >= 1
        assert steps[0].action == 'git'
        assert steps[0].thought is not None
        assert steps[0].observation is not None
    
    def test_react_reason_memory(self, selector):
        """测试 Memory 任务的 ReAct 推理"""
        steps = selector.react_reason('save important data to memory')
        
        assert len(steps) >= 1
        assert steps[0].action == 'memory'
    
    def test_react_reason_no_match(self, selector):
        """测试无匹配工具的 ReAct 推理"""
        steps = selector.react_reason('do something completely unrelated xyz')
        
        # 应该返回 no_tool 或空
        assert len(steps) >= 1
        assert steps[0].action in ['no_tool', 'git', 'moon', 'memory']
    
    def test_react_reason_max_steps(self, selector):
        """测试最大步数限制"""
        steps = selector.react_reason('commit and save to memory', max_steps=2)
        
        assert len(steps) <= 2
    
    def test_react_format(self, selector):
        """测试格式化输出"""
        steps = selector.react_reason('commit code')
        formatted = selector.react_format(steps)
        
        assert 'ReAct' in formatted or 'Step' in formatted
        assert 'Thought' in formatted
        assert 'Action' in formatted
    
    def test_react_execute(self, selector):
        """测试 ReAct 执行"""
        result = selector.react_execute('save to memory')
        
        assert 'steps' in result
        assert 'success' in result
        assert 'final_answer' in result
        assert result['success'] is True
    
    def test_react_execute_no_match(self, selector):
        """测试无匹配时的执行结果"""
        result = selector.react_execute('xyz unrelated task')
        
        assert 'steps' in result
        # 可能成功或失败，取决于是否有默认工具
    
    def test_react_step_dataclass(self):
        """测试 ReActStep 数据类"""
        step = ReActStep(
            step=1,
            thought="Test thought",
            action="git",
            action_input='{"action": "commit"}',
            observation="Done",
        )
        
        assert step.step == 1
        assert step.is_final is False


class TestReActAgent:
    """ReActAgent 测试"""
    
    @pytest.fixture
    def agent(self):
        return ReActAgent(tools=['git', 'moon', 'memory'], max_iterations=3)
    
    def test_initialization(self, agent):
        assert agent.max_iterations == 3
        assert agent.selector is not None
        assert len(agent.history) == 0
    
    def test_run_git_task(self, agent):
        """运行 Git 任务"""
        result = agent.run('commit the code')
        
        assert 'success' in result
        assert 'steps' in result
        assert len(agent.history) >= 1
    
    def test_run_memory_task(self, agent):
        """运行 Memory 任务"""
        result = agent.run('remember this info')
        
        assert result['success'] is True
        assert len(agent.history) >= 1
    
    def test_run_with_executor(self, agent):
        """运行带自定义执行器"""
        def executor(action, params):
            return f"Custom result for {action}"
        
        result = agent.run('commit code', tool_executor=executor)
        
        assert result['success'] is True
    
    def test_get_history(self, agent):
        """获取推理历史"""
        agent.run('commit code')
        history = agent.get_history()
        
        assert len(history) >= 1
        assert isinstance(history[0], ReActStep)
    
    def test_reset(self, agent):
        """重置状态"""
        agent.run('commit code')
        assert len(agent.history) >= 1
        
        agent.reset()
        assert len(agent.history) == 0
    
    def test_verbose_mode(self, agent):
        """详细模式"""
        agent_verbose = ReActAgent(verbose=True)
        result = agent_verbose.run('commit code')
        
        # 不应该崩溃
        assert result is not None
    
    def test_max_iterations_respected(self):
        """测试最大迭代次数被遵守"""
        agent = ReActAgent(max_iterations=2)
        result = agent.run('complex task with multiple steps')
        
        # 步骤数应该不超过 max_iterations
        assert len(result['steps']) <= 2


class TestReActIntegration:
    """ReAct 集成测试"""
    
    def test_full_react_workflow(self):
        """完整 ReAct 工作流"""
        selector = ToolSelector(['git', 'moon', 'memory'])
        
        # 1. 推理
        steps = selector.react_reason('commit and push the code')
        
        # 2. 执行
        result = selector.react_execute('commit and push the code')
        
        # 3. 验证
        assert result['success'] is True
        assert len(result['steps']) >= 1
    
    def test_react_with_real_executor(self):
        """使用真实执行器的 ReAct"""
        call_log = []
        
        def executor(action, params):
            call_log.append((action, params))
            return f"Executed {action}"
        
        agent = ReActAgent()
        result = agent.run('save to memory', tool_executor=executor)
        
        # 执行器应该被调用
        assert len(call_log) >= 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
