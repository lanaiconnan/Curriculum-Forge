"""
知识层测试
"""

import pytest
import tempfile
import shutil
from pathlib import Path

from knowledge import SyzygyVault, ExperienceGenerator, ExperiencePage


class TestSyzygyVault:
    """测试 Syzygy Vault"""
    
    @pytest.fixture
    def vault(self, tmp_path):
        """创建临时 vault"""
        vault_path = tmp_path / "vault"
        vault_path.mkdir()
        return SyzygyVault(str(vault_path))
    
    def test_create_page(self, vault):
        """测试创建页面"""
        filepath = vault.create_page(
            title="测试页面",
            content="这是测试内容",
            tags=["测试", "示例"],
            links=["相关页面"]
        )
        
        assert Path(filepath).exists()
        
        # 验证可以读取
        page = vault.get_page("测试页面")
        assert page is not None
        assert page.title == "测试页面"
        assert "测试" in page.tags
    
    def test_search_by_tag(self, vault):
        """测试标签搜索"""
        vault.create_page(
            title="页面1",
            content="内容1",
            tags=["标签A", "标签B"]
        )
        vault.create_page(
            title="页面2",
            content="内容2",
            tags=["标签A", "标签C"]
        )
        
        results = vault.search_by_tag("标签A")
        assert len(results) == 2
        
        results = vault.search_by_tag("标签B")
        assert len(results) == 1
        assert results[0].title == "页面1"
    
    def test_search_by_keyword(self, vault):
        """测试关键词搜索"""
        vault.create_page(
            title="性能优化指南",
            content="如何提升 API 响应速度",
            tags=["性能"]
        )
        vault.create_page(
            title="缓存设计",
            content="使用 Redis 缓存提升性能",
            tags=["缓存"]
        )
        
        results = vault.search_by_keyword("性能")
        assert len(results) == 2
        
        results = vault.search_by_keyword("Redis")
        assert len(results) == 1
    
    def test_get_linked_pages(self, vault):
        """测试链接页面"""
        vault.create_page(
            title="页面A",
            content="A 的内容",
            tags=["A"],
            links=["页面B", "页面C"]
        )
        vault.create_page(
            title="页面B",
            content="B 的内容",
            tags=["B"]
        )
        
        linked = vault.get_linked_pages("页面A")
        assert len(linked) == 1
        assert linked[0].title == "页面B"
    
    def test_get_backlinks(self, vault):
        """测试反向链接"""
        vault.create_page(
            title="页面A",
            content="A 的内容",
            tags=["A"],
            links=["页面B"]
        )
        vault.create_page(
            title="页面B",
            content="B 的内容",
            tags=["B"]
        )
        
        backlinks = vault.get_backlinks("页面B")
        assert len(backlinks) == 1
        assert backlinks[0].title == "页面A"
    
    def test_ascii_graph(self, vault):
        """测试 ASCII 知识图谱"""
        vault.create_page(
            title="页面A",
            content="A",
            tags=["A"],
            links=["页面B"]
        )
        vault.create_page(
            title="页面B",
            content="B",
            tags=["B"]
        )
        
        graph = vault.generate_ascii_graph()
        assert "页面A" in graph
        assert "页面B" in graph


class TestExperiencePage:
    """测试经验页"""
    
    def test_to_markdown(self):
        """测试 Markdown 转换"""
        page = ExperiencePage(
            title="测试页面",
            content="测试内容",
            tags=["标签1", "标签2"],
            links=["链接1", "链接2"]
        )
        
        md = page.to_markdown()
        assert "# 测试页面" in md
        assert "测试内容" in md
        assert "#标签1" in md
        assert "[[链接1]]" in md
    
    def test_from_markdown(self, tmp_path):
        """测试从 Markdown 解析"""
        md_content = """# 测试页面

这是测试内容

## 标签
#标签1 #标签2

## 相关链接
- [[链接1]]
- [[链接2]]

---
创建时间：2026-04-28 01:00
更新时间：2026-04-28 01:00
"""
        filepath = tmp_path / "test.md"
        filepath.write_text(md_content, encoding='utf-8')
        
        page = ExperiencePage.from_markdown(filepath)
        assert page.title == "测试页面"
        assert "测试内容" in page.content
        assert "标签1" in page.tags
        assert "链接1" in page.links


class TestExperienceGenerator:
    """测试经验生成器"""
    
    @pytest.fixture
    def vault_and_generator(self, tmp_path):
        """创建 vault 和 generator"""
        vault_path = tmp_path / "vault"
        vault_path.mkdir()
        vault = SyzygyVault(str(vault_path))
        generator = ExperienceGenerator(vault)
        return vault, generator
    
    def test_generate_from_task(self, vault_and_generator):
        """测试从任务生成经验"""
        vault, generator = vault_and_generator
        
        # 创建模拟任务和结果
        from services.coordinator import Task
        from providers.base import RunState, TaskPhase
        
        # Task 在 services/coordinator.py 中定义，没有 name 字段
        # 使用 payload 存储 name
        task = Task(
            id="task-001",
            type="curriculum",
            payload={"name": "优化 API 响应时间", "method": "cache"}
        )
        
        # 简化测试：直接测试生成器逻辑
        from unittest.mock import Mock
        
        result = Mock()
        result.status = RunState.COMPLETED
        result.output = Mock()
        result.output.data = {"response_time": "50ms"}
        result.error = None
        result.metrics = None
        
        # 生成经验页
        filepath = generator.generate_from_task(task, result)
        
        # 验证
        page = vault.get_page("任务：task-001")
        assert page is not None
        assert "成功" in page.content
