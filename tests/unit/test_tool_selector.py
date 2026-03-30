"""测试 Tool Selector

测试内容：
1. 工具选择
2. 参数推断
3. 工具组合建议
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.tool_selector import ToolSelector, ToolCandidate


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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
