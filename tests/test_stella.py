"""
Tests for Stella - Memory-Enhanced Coordinator
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from knowledge.syzygy import SyzygyVault, ExperiencePage
from knowledge.experience_generator import ExperienceGenerator
from roles.stella import Stella, MemoryContext


@pytest.fixture
def temp_vault():
    """Create a temporary vault for testing"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def vault(temp_vault):
    """Create SyzygyVault instance"""
    return SyzygyVault(temp_vault)


@pytest.fixture
def experience_generator(vault):
    """Create ExperienceGenerator instance"""
    return ExperienceGenerator(vault)


@pytest.fixture
def mock_coordinator():
    """Create mock Coordinator"""
    coordinator = Mock()
    coordinator.event_bus = Mock()
    coordinator.event_bus.subscribe = Mock(return_value="stella_test")
    coordinator._on_task_complete = None
    coordinator._on_workflow_complete = None
    return coordinator


@pytest.fixture
def mock_task():
    """Create mock Task"""
    task = Mock()
    task.id = "test_task_001"
    task.type = "optimization"
    task.name = "测试任务"
    task.description = "优化API响应时间，使用缓存提升性能"
    task.status = Mock()
    task.status.value = "pending"
    task.payload = {
        "target": "api",
        "method": "cache",
    }
    return task


@pytest.fixture
def mock_result():
    """Create mock task result"""
    result = Mock()
    result.status = Mock()
    result.status.value = "completed"
    result.output = {"response_time": "50ms"}
    result.error = None
    result.metrics = {"improvement": "10x"}
    return result


class TestMemoryContext:
    """Test MemoryContext"""
    
    def test_empty_context(self):
        """Test empty context string"""
        ctx = MemoryContext(task_id="test")
        assert ctx.to_context_string() == "无历史经验参考"
    
    def test_context_with_experiences(self):
        """Test context with experiences"""
        exp = ExperiencePage(
            title="优化经验",
            content="使用LRU缓存可以有效提升响应速度\n\n## 经验教训\n缓存命中率很重要",
            tags=["performance", "cache"],
        )
        
        ctx = MemoryContext(
            task_id="test",
            relevant_experiences=[exp],
            recommendations=["参考此案例"],
        )
        
        context_str = ctx.to_context_string()
        assert "优化经验" in context_str
        assert "performance" in context_str
        assert "参考此案例" in context_str


class TestStella:
    """Test Stella memory-enhanced coordinator"""
    
    def test_stella_init(self, mock_coordinator, vault, experience_generator):
        """Test Stella initialization"""
        stella = Stella(
            coordinator=mock_coordinator,
            vault=vault,
            experience_generator=experience_generator,
        )
        
        assert stella.coordinator == mock_coordinator
        assert stella.vault == vault
        assert stella.experience_generator == experience_generator
        assert stella.enable_reflection is True
        
        # Verify hooks were set
        mock_coordinator.event_bus.subscribe.assert_called_once_with("stella")
    
    def test_retrieve_experiences_empty(self, mock_coordinator, vault, mock_task):
        """Test retrieve experiences with empty vault"""
        stella = Stella(mock_coordinator, vault)
        ctx = stella.retrieve_experiences(mock_task)
        
        assert ctx.task_id == "test_task_001"
        assert len(ctx.relevant_experiences) == 0
        assert ctx.confidence_score == 0.0
    
    def test_retrieve_experiences_by_type(self, mock_coordinator, vault, mock_task):
        """Test retrieve experiences by task type"""
        # Create experience page with matching type tag
        vault.create_page(
            title="优化经验1",
            content="使用缓存优化性能",
            tags=["optimization", "cache"],
        )
        
        stella = Stella(mock_coordinator, vault)
        ctx = stella.retrieve_experiences(mock_task)
        
        assert len(ctx.relevant_experiences) >= 1
        assert ctx.confidence_score > 0.0
    
    def test_retrieve_experiences_by_keyword(self, mock_coordinator, vault):
        """Test retrieve experiences by keyword"""
        # Create experience page with keyword in content
        vault.create_page(
            title="Redis缓存策略",
            content="使用Redis作为缓存层，解决缓存问题",
            tags=["redis"],  # Different tag than task type
        )
        
        # Create task with matching keyword in description
        task = Mock()
        task.id = "test_002"
        task.type = "database"
        task.description = "需要缓存优化"  # Contains '缓存'
        task.status = Mock()
        task.status.value = "pending"
        
        stella = Stella(mock_coordinator, vault)
        ctx = stella.retrieve_experiences(task)
        
        # Should find the cache-related experience by keyword '缓存'
        # Note: keyword extraction gives '缓存', and content contains '缓存'
        assert len(ctx.relevant_experiences) >= 1
    
    def test_store_experience_success(self, mock_coordinator, vault, experience_generator, mock_task, mock_result):
        """Test storing experience after task completion"""
        stella = Stella(
            mock_coordinator,
            vault,
            experience_generator=experience_generator,
        )
        
        # Simulate task result
        mock_task.result = mock_result
        
        # Store experience
        stella._store_experience(mock_task)
        
        # Verify experience was stored
        pages = vault.list_all_pages()
        assert len(pages) >= 1
        assert "测试任务" in pages[0]
    
    def test_build_context(self, mock_coordinator, vault, mock_task):
        """Test building context for task execution"""
        stella = Stella(mock_coordinator, vault)
        ctx = stella.build_context(mock_task)
        
        assert "task_id" in ctx
        assert "task_type" in ctx
        assert "memory_context" in ctx
        assert ctx["task_id"] == "test_task_001"
    
    def test_generate_recommendations(self, mock_coordinator, vault, mock_task):
        """Test generating recommendations"""
        # Create successful experience
        vault.create_page(
            title="成功优化案例",
            content="## 经验教训\n使用缓存有效",
            tags=["optimization"],
            metadata={"status": "completed"},
        )
        
        # Create failed experience
        vault.create_page(
            title="失败案例",
            content="## 结果\n配置错误",
            tags=["optimization"],
            metadata={"status": "failed"},
        )
        
        stella = Stella(mock_coordinator, vault)
        ctx = stella.retrieve_experiences(mock_task)
        
        # Should have recommendations
        assert len(ctx.recommendations) >= 1
    
    def test_memory_stats(self, mock_coordinator, vault):
        """Test memory stats"""
        vault.create_page("经验1", "内容", ["tag1"])
        vault.create_page("经验2", "内容", ["tag2"])
        
        stella = Stella(mock_coordinator, vault)
        stella._memory_cache["test"] = MemoryContext(task_id="test")
        
        stats = stella.get_memory_stats()
        
        assert stats["total_experiences"] == 2
        assert stats["cached_contexts"] == 1
    
    def test_clear_cache(self, mock_coordinator, vault):
        """Test clearing memory cache"""
        stella = Stella(mock_coordinator, vault)
        stella._memory_cache["test"] = MemoryContext(task_id="test")
        
        assert len(stella._memory_cache) == 1
        
        stella.clear_cache()
        
        assert len(stella._memory_cache) == 0
    
    def test_extract_keywords(self, mock_coordinator, vault):
        """Test keyword extraction"""
        stella = Stella(mock_coordinator, vault)
        
        keywords = stella._extract_keywords("优化API性能，使用缓存策略")
        
        # Should extract multi-char Chinese words and English words
        assert len(keywords) >= 1
        # Check that we got some meaningful keywords
        assert any(k in keywords for k in ['优化', 'api', '性能', '缓存', '策略'])
    
    def test_reflection_generation(self, mock_coordinator, vault, mock_task, mock_result):
        """Test reflection text generation"""
        stella = Stella(mock_coordinator, vault, enable_reflection=True)
        
        # Success case
        reflection = stella._generate_reflection(mock_task, mock_result)
        assert reflection is not None
        assert "成功" in reflection
        
        # Failure case
        fail_result = Mock()
        fail_result.status = Mock()
        fail_result.status.value = "failed"
        fail_result.error = "配置错误"
        
        reflection = stella._generate_reflection(mock_task, fail_result)
        assert "失败" in reflection or "错误" in reflection
    
    def test_delegation_to_coordinator(self, mock_coordinator, vault):
        """Test that unknown attributes are delegated to coordinator"""
        mock_coordinator.some_method = Mock(return_value="result")
        
        stella = Stella(mock_coordinator, vault)
        
        # Should delegate to coordinator
        result = stella.some_method()
        
        assert result == "result"
        mock_coordinator.some_method.assert_called_once()


class TestStellaIntegration:
    """Integration tests for Stella"""
    
    def test_full_workflow(self, temp_vault):
        """Test full workflow: retrieve -> execute -> store"""
        vault = SyzygyVault(temp_vault)
        generator = ExperienceGenerator(vault)
        
        # Setup coordinator with real components
        from services.coordinator import Coordinator, Task
        
        coordinator = Coordinator()  # Uses default constructor
        
        stella = Stella(
            coordinator=coordinator,
            vault=vault,
            experience_generator=generator,
        )
        
        # Create task
        task = Task(
            id="integration_test_001",
            type="test",
            payload={"key": "value"},
        )
        
        # Retrieve context (should be empty initially)
        ctx = stella.retrieve_experiences(task)
        assert len(ctx.relevant_experiences) == 0
        
        # Simulate storing experience
        from types import SimpleNamespace
        mock_result = SimpleNamespace(
            status=SimpleNamespace(value="completed"),
            output={"result": "success"},
            error=None,
        )
        task.result = mock_result
        
        stella._store_experience(task)
        
        # Verify stored
        pages = vault.list_all_pages()
        assert len(pages) >= 1
        
        # Retrieve again - should find the experience
        new_task = Task(
            id="integration_test_002",
            type="test",
            payload={},
        )
        
        ctx2 = stella.retrieve_experiences(new_task)
        # Should find the previous experience by type tag
        assert len(ctx2.relevant_experiences) >= 1
