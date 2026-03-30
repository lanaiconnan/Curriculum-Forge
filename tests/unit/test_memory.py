"""测试 Letta-style Memory Block 机制

测试 memory.py 的核心功能
"""

import pytest
import sys
import os
import tempfile
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.memory import (
    MemoryBlock,
    CoreMemory,
    ArchivalMemory,
    RecallMemory,
    MemoryManager,
    MemoryType,
    BlockPermission,
)


class TestMemoryBlock:
    """MemoryBlock 测试套件"""
    
    def test_block_initialization(self):
        """测试块初始化"""
        block = MemoryBlock(
            label="test",
            value="Hello",
            memory_type=MemoryType.CORE,
        )
        
        assert block.label == "test"
        assert block.value == "Hello"
        assert block.memory_type == MemoryType.CORE
        assert block.permission == BlockPermission.READ_WRITE
    
    def test_block_read_string(self):
        """测试读取字符串块"""
        block = MemoryBlock(
            label="test",
            value="Hello World",
            memory_type=MemoryType.CORE,
        )
        
        assert block.read() == "Hello World"
    
    def test_block_read_json(self):
        """测试读取 JSON 块"""
        block = MemoryBlock(
            label="test",
            value={"key": "value", "number": 42},
            memory_type=MemoryType.CORE,
        )
        
        result = block.read()
        assert "key" in result
        assert "value" in result
    
    def test_block_write(self):
        """测试写入块"""
        block = MemoryBlock(
            label="test",
            value="initial",
            memory_type=MemoryType.CORE,
        )
        
        success = block.write("updated")
        assert success is True
        assert block.read() == "updated"
    
    def test_block_write_read_only(self):
        """测试写入只读块"""
        block = MemoryBlock(
            label="test",
            value="initial",
            memory_type=MemoryType.CORE,
            permission=BlockPermission.READ_ONLY,
        )
        
        success = block.write("updated")
        assert success is False
        assert block.read() == "initial"
    
    def test_block_write_exceed_limit(self):
        """测试写入超限"""
        block = MemoryBlock(
            label="test",
            value="",
            memory_type=MemoryType.CORE,
            limit=10,
        )
        
        success = block.write("a" * 20)
        assert success is False
    
    def test_block_to_dict(self):
        """测试转换为字典"""
        block = MemoryBlock(
            label="test",
            value="content",
            memory_type=MemoryType.CORE,
        )
        
        data = block.to_dict()
        
        assert data['label'] == "test"
        assert data['value'] == "content"
        assert data['memory_type'] == "core"
    
    def test_block_from_dict(self):
        """测试从字典创建"""
        data = {
            'label': 'test',
            'value': 'content',
            'memory_type': 'core',
            'permission': 'read_write',
            'description': 'Test block',
            'limit': 2000,
        }
        
        block = MemoryBlock.from_dict(data)
        
        assert block.label == "test"
        assert block.value == "content"
        assert block.memory_type == MemoryType.CORE


class TestCoreMemory:
    """CoreMemory 测试套件"""
    
    @pytest.fixture
    def core_memory(self):
        """创建测试用核心记忆"""
        return CoreMemory()
    
    def test_add_block(self, core_memory):
        """测试添加块"""
        block = MemoryBlock(
            label="persona",
            value="I am a helpful assistant",
            memory_type=MemoryType.CORE,
        )
        
        success = core_memory.add_block(block)
        assert success is True
        assert "persona" in core_memory.blocks
    
    def test_add_duplicate_block(self, core_memory):
        """测试添加重复块"""
        block1 = MemoryBlock(
            label="persona",
            value="First",
            memory_type=MemoryType.CORE,
        )
        block2 = MemoryBlock(
            label="persona",
            value="Second",
            memory_type=MemoryType.CORE,
        )
        
        core_memory.add_block(block1)
        success = core_memory.add_block(block2)
        
        assert success is False
        assert core_memory.blocks["persona"].value == "First"
    
    def test_get_block(self, core_memory):
        """测试获取块"""
        block = MemoryBlock(
            label="test",
            value="content",
            memory_type=MemoryType.CORE,
        )
        core_memory.add_block(block)
        
        retrieved = core_memory.get_block("test")
        assert retrieved.value == "content"
    
    def test_update_block(self, core_memory):
        """测试更新块"""
        block = MemoryBlock(
            label="test",
            value="initial",
            memory_type=MemoryType.CORE,
        )
        core_memory.add_block(block)
        
        success = core_memory.update_block("test", "updated")
        assert success is True
        assert core_memory.get_block("test").value == "updated"
    
    def test_remove_block(self, core_memory):
        """测试移除块"""
        block = MemoryBlock(
            label="test",
            value="content",
            memory_type=MemoryType.CORE,
        )
        core_memory.add_block(block)
        
        success = core_memory.remove_block("test")
        assert success is True
        assert "test" not in core_memory.blocks
    
    def test_get_context(self, core_memory):
        """测试获取上下文"""
        block1 = MemoryBlock(
            label="persona",
            value="I am helpful",
            memory_type=MemoryType.CORE,
        )
        block2 = MemoryBlock(
            label="human",
            value="User is friendly",
            memory_type=MemoryType.CORE,
        )
        
        core_memory.add_block(block1)
        core_memory.add_block(block2)
        
        context = core_memory.get_context()
        
        assert "=== Core Memory ===" in context
        assert "[persona]" in context
        assert "[human]" in context


class TestArchivalMemory:
    """ArchivalMemory 测试套件"""
    
    @pytest.fixture
    def archival_memory(self):
        """创建测试用归档记忆"""
        return ArchivalMemory()
    
    def test_insert(self, archival_memory):
        """测试插入条目"""
        index = archival_memory.insert(
            "This is important information",
            {"type": "note"}
        )
        
        assert index == 0
        assert len(archival_memory.entries) == 1
    
    def test_search(self, archival_memory):
        """测试搜索条目"""
        archival_memory.insert("Python is great")
        archival_memory.insert("JavaScript is popular")
        archival_memory.insert("Python is easy to learn")
        
        results = archival_memory.search("Python")
        
        assert len(results) == 2
        assert "Python" in results[0]['content']
    
    def test_get(self, archival_memory):
        """测试获取指定条目"""
        index = archival_memory.insert("Test content")
        
        result = archival_memory.get(index)
        
        assert result is not None
        assert result['content'] == "Test content"
    
    def test_clear(self, archival_memory):
        """测试清空"""
        archival_memory.insert("Content 1")
        archival_memory.insert("Content 2")
        
        archival_memory.clear()
        
        assert len(archival_memory.entries) == 0
        assert len(archival_memory.index) == 0


class TestRecallMemory:
    """RecallMemory 测试套件"""
    
    @pytest.fixture
    def recall_memory(self):
        """创建测试用回忆记忆"""
        return RecallMemory()
    
    def test_add_message(self, recall_memory):
        """测试添加消息"""
        recall_memory.add_message("user", "Hello")
        recall_memory.add_message("assistant", "Hi there!")
        
        assert len(recall_memory.messages) == 2
    
    def test_get_recent(self, recall_memory):
        """测试获取最近消息"""
        for i in range(20):
            recall_memory.add_message("user", f"Message {i}")
        
        recent = recall_memory.get_recent(5)
        
        assert len(recent) == 5
        assert "Message 19" in recent[-1]['content']
    
    def test_search(self, recall_memory):
        """测试搜索消息"""
        recall_memory.add_message("user", "What is Python?")
        recall_memory.add_message("assistant", "Python is a language")
        recall_memory.add_message("user", "What about JavaScript?")
        
        results = recall_memory.search("Python")
        
        assert len(results) == 2
        assert "Python" in results[0]['content']
    
    def test_max_messages(self):
        """测试消息数量限制"""
        recall = RecallMemory(max_messages=10)
        
        for i in range(15):
            recall.add_message("user", f"Message {i}")
        
        assert len(recall.messages) == 10


class TestMemoryManager:
    """MemoryManager 测试套件"""
    
    @pytest.fixture
    def manager(self, tmp_path):
        """创建测试用记忆管理器"""
        return MemoryManager(
            agent_id="test_agent",
            storage_dir=str(tmp_path / ".memory"),
        )
    
    def test_initialization(self, manager):
        """测试初始化"""
        assert manager.agent_id == "test_agent"
        assert "persona" in manager.core_memory.blocks
        assert "human" in manager.core_memory.blocks
    
    def test_core_memory_append(self, manager):
        """测试追加核心记忆"""
        success = manager.core_memory_append("persona", "I am helpful.")
        
        assert success is True
        content = manager.core_memory.get_block("persona").read()
        assert "helpful" in content
    
    def test_core_memory_replace(self, manager):
        """测试替换核心记忆"""
        manager.core_memory_append("persona", "I am old.")
        success = manager.core_memory_replace("persona", "old", "new")
        
        assert success is True
        content = manager.core_memory.get_block("persona").read()
        assert "new" in content
    
    def test_archival_operations(self, manager):
        """测试归档记忆操作"""
        # 插入
        index = manager.archival_memory_insert(
            "Important fact",
            {"category": "knowledge"}
        )
        
        assert index >= 0
        
        # 搜索
        results = manager.archival_memory_search("fact")
        assert len(results) > 0
    
    def test_recall_operations(self, manager):
        """测试回忆记忆操作"""
        # 添加消息
        manager.recall_memory.add_message("user", "Hello")
        manager.recall_memory.add_message("assistant", "Hi!")
        
        # 搜索
        results = manager.conversation_search("Hello")
        assert len(results) == 1
    
    def test_save_and_load(self, manager):
        """测试保存和加载"""
        # 修改记忆
        manager.core_memory_append("persona", "Test persona")
        manager.archival_memory_insert("Archived info")
        manager.recall_memory.add_message("user", "Test message")
        
        # 保存
        manager.save()
        
        # 创建新管理器并加载
        new_manager = MemoryManager(
            agent_id="test_agent",
            storage_dir=manager.storage_dir,
        )
        new_manager.load()
        
        # 验证
        assert "Test persona" in new_manager.core_memory.get_block("persona").read()
        assert len(new_manager.archival_memory.entries) == 1
        assert len(new_manager.recall_memory.messages) == 1
    
    def test_get_tools(self, manager):
        """测试获取工具定义"""
        tools = manager.get_tools()
        
        assert len(tools) >= 5
        tool_names = [t['name'] for t in tools]
        assert 'core_memory_append' in tool_names
        assert 'core_memory_read' in tool_names
        assert 'archival_memory_search' in tool_names
    
    def test_get_status(self, manager):
        """测试获取状态"""
        status = manager.get_status()
        
        assert status['agent_id'] == "test_agent"
        assert 'core_memory' in status
        assert 'archival_memory' in status
        assert 'recall_memory' in status


class TestMemoryIntegration:
    """记忆系统集成测试"""
    
    @pytest.mark.integration
    def test_full_memory_workflow(self, tmp_path):
        """测试完整记忆工作流"""
        manager = MemoryManager(
            agent_id="integration_test",
            storage_dir=str(tmp_path / ".memory"),
        )
        
        # 1. 设置 Persona
        manager.core_memory_append("persona", "I am a helpful AI assistant.")
        manager.core_memory_append("persona", "I specialize in Python and JavaScript.")
        
        # 2. 设置 Human 信息
        manager.core_memory_append("human", "User prefers Python over JavaScript.")
        
        # 3. 添加任务
        manager.core_memory.update_block("tasks", [
            {"id": 1, "task": "Review code", "status": "pending"},
            {"id": 2, "task": "Write tests", "status": "in_progress"},
        ])
        
        # 4. 归档重要信息
        manager.archival_memory_insert(
            "Project deadline is next Friday",
            {"priority": "high"}
        )
        
        # 5. 添加对话
        manager.recall_memory.add_message("user", "What's the project deadline?")
        manager.recall_memory.add_message(
            "assistant",
            manager.core_memory_read("tasks")
        )
        
        # 6. 搜索
        deadline_results = manager.archival_memory_search("deadline")
        assert len(deadline_results) > 0
        
        # 7. 保存
        manager.save()
        
        # 8. 加载并验证
        new_manager = MemoryManager(
            agent_id="integration_test",
            storage_dir=manager.storage_dir,
        )
        new_manager.load()
        
        # 验证核心记忆
        persona = new_manager.core_memory.get_block("persona").read()
        assert "helpful" in persona
        assert "Python" in persona
        
        # 验证任务
        tasks = new_manager.core_memory.get_block("tasks").value
        assert len(tasks) == 2
        
        # 验证归档
        assert len(new_manager.archival_memory.entries) == 1
        
        # 验证对话
        assert len(new_manager.recall_memory.messages) == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
