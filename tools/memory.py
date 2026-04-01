"""Letta-style Memory Block 机制

来自 Letta (MemGPT) 的灵感：
- 分层记忆架构（Core Memory + Archival Memory + Recall Memory）
- 结构化的 Memory Blocks
- 工具可读写的记忆系统
- 支持共享记忆和私有记忆

核心概念：
1. MemoryBlock - 单个记忆块
2. CoreMemory - 核心记忆（始终在上下文中）
3. ArchivalMemory - 归档记忆（长期存储+检索）
4. RecallMemory - 回忆记忆（对话历史）
5. MemoryManager - 记忆管理器
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from enum import Enum
import json
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from shared.scratchpad import Scratchpad
    SCRATCHPAD_AVAILABLE = True
except ImportError:
    SCRATCHPAD_AVAILABLE = False
    Scratchpad = None


class MemoryType(Enum):
    """记忆类型"""
    CORE = "core"           # 核心记忆（始终在上下文）
    ARCHIVAL = "archival"   # 归档记忆（长期存储）
    RECALL = "recall"       # 回忆记忆（对话历史）


class BlockPermission(Enum):
    """块权限"""
    READ_ONLY = "read_only"       # 只读
    READ_WRITE = "read_write"     # 读写
    PRIVATE = "private"           # 私有（仅所有者可见）
    SHARED = "shared"             # 共享（所有 Agent 可见）


@dataclass
class MemoryBlock:
    """
    记忆块
    
    来自 Letta 的设计：
    - 结构化的记忆单元
    - 可被工具读写
    - 支持模板和变量
    """
    label: str                          # 块标签（唯一标识）
    value: Any                          # 块值
    memory_type: MemoryType             # 记忆类型
    permission: BlockPermission = BlockPermission.READ_WRITE
    description: str = ""               # 描述
    template: str = ""                  # 模板（用于自动生成）
    limit: int = 2000                   # 字符限制
    last_modified: datetime = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.last_modified is None:
            self.last_modified = datetime.now()
    
    def read(self) -> str:
        """读取块内容"""
        if isinstance(self.value, (dict, list)):
            return json.dumps(self.value, ensure_ascii=False, indent=2)
        return str(self.value) if self.value else ""
    
    def write(self, new_value: Any) -> bool:
        """
        写入块内容
        
        Returns:
            bool: 是否成功
        """
        if self.permission == BlockPermission.READ_ONLY:
            return False
        
        # 检查大小限制
        value_str = json.dumps(new_value) if isinstance(new_value, (dict, list)) else str(new_value)
        if len(value_str) > self.limit:
            # 截断或拒绝
            return False
        
        self.value = new_value
        self.last_modified = datetime.now()
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'label': self.label,
            'value': self.value,
            'memory_type': self.memory_type.value,
            'permission': self.permission.value,
            'description': self.description,
            'limit': self.limit,
            'last_modified': self.last_modified.isoformat() if self.last_modified else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryBlock':
        """从字典创建"""
        return cls(
            label=data['label'],
            value=data['value'],
            memory_type=MemoryType(data['memory_type']),
            permission=BlockPermission(data.get('permission', 'read_write')),
            description=data.get('description', ''),
            limit=data.get('limit', 2000),
            last_modified=datetime.fromisoformat(data['last_modified']) if data.get('last_modified') else None,
        )


@dataclass
class CoreMemory:
    """
    核心记忆
    
    来自 Letta 的设计：
    - 始终保持在上下文中
    - 用于存储 Agent 的核心信息
    - 包括 Persona、Human、Custom 等
    """
    blocks: Dict[str, MemoryBlock] = field(default_factory=dict)
    max_total_size: int = 10000         # 总大小限制（字符）
    
    def add_block(self, block: MemoryBlock) -> bool:
        """添加块"""
        if block.label in self.blocks:
            return False
        
        # 检查总大小
        current_size = sum(len(b.read()) for b in self.blocks.values())
        if current_size + len(block.read()) > self.max_total_size:
            return False
        
        self.blocks[block.label] = block
        return True
    
    def get_block(self, label: str) -> Optional[MemoryBlock]:
        """获取块"""
        return self.blocks.get(label)
    
    def update_block(self, label: str, value: Any) -> bool:
        """更新块"""
        block = self.blocks.get(label)
        if block:
            return block.write(value)
        return False
    
    def remove_block(self, label: str) -> bool:
        """移除块"""
        if label in self.blocks:
            del self.blocks[label]
            return True
        return False
    
    def get_context(self) -> str:
        """
        获取核心记忆上下文
        
        用于注入到 Agent 的 system prompt
        """
        lines = ["=== Core Memory ==="]
        
        for label, block in self.blocks.items():
            lines.append(f"\n[{label}]")
            lines.append(block.read())
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'blocks': {k: v.to_dict() for k, v in self.blocks.items()},
            'max_total_size': self.max_total_size,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CoreMemory':
        """从字典创建"""
        memory = cls(max_total_size=data.get('max_total_size', 10000))
        for label, block_data in data.get('blocks', {}).items():
            memory.blocks[label] = MemoryBlock.from_dict(block_data)
        return memory


@dataclass
class ArchivalMemory:
    """
    归档记忆
    
    来自 Letta 的设计：
    - 长期存储
    - 支持检索
    - 无限容量（但需要检索才能访问）
    """
    entries: List[Dict[str, Any]] = field(default_factory=list)
    index: Dict[str, List[int]] = field(default_factory=dict)  # 简单索引
    
    def insert(self, content: str, metadata: Dict[str, Any] = None) -> int:
        """
        插入条目
        
        Returns:
            int: 条目索引
        """
        entry = {
            'content': content,
            'metadata': metadata or {},
            'timestamp': datetime.now().isoformat(),
        }
        
        self.entries.append(entry)
        index = len(self.entries) - 1
        
        # 更新索引（简单的关键词索引）
        words = set(content.lower().split())
        for word in words:
            if word not in self.index:
                self.index[word] = []
            self.index[word].append(index)
        
        return index
    
    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        搜索条目
        
        简单的关键词搜索（可扩展为向量搜索）
        """
        query_words = set(query.lower().split())
        
        # 找到匹配的索引
        matched_indices = set()
        for word in query_words:
            if word in self.index:
                matched_indices.update(self.index[word])
        
        # 返回匹配的条目
        results = []
        for idx in sorted(matched_indices)[:top_k]:
            if idx < len(self.entries):
                results.append({
                    'index': idx,
                    **self.entries[idx]
                })
        
        return results
    
    def get(self, index: int) -> Optional[Dict[str, Any]]:
        """获取指定索引的条目"""
        if 0 <= index < len(self.entries):
            return {
                'index': index,
                **self.entries[index]
            }
        return None
    
    def clear(self):
        """清空归档记忆"""
        self.entries.clear()
        self.index.clear()


@dataclass
class RecallMemory:
    """
    回忆记忆（来自 Letta + Claude Code 灵感）
    
    来自 Letta 的设计：
    - 存储对话历史
    - 支持时间范围查询
    - 支持关键词搜索
    
    来自 Claude Code 灵感：
    - 自动摘要（周期性）
    - 初始化状态追踪
    - Token 计数
    """
    messages: List[Dict[str, Any]] = field(default_factory=list)
    max_messages: int = 1000
    
    # Claude Code 风格的配置
    is_initialized: bool = False                     # 初始化状态
    auto_summarize_threshold: int = 50               # 自动摘要阈值
    summarized_count: int = 0                        # 已摘要消息数
    last_summarized_index: int = -1                  # 上次摘要位置
    extraction_token_count: int = 0                  # 摘要 token 计数
    
    def add_message(
        self,
        role: str,
        content: str,
        metadata: Dict[str, Any] = None
    ):
        """添加消息"""
        # 检查是否需要初始化
        if not self.is_initialized and len(self.messages) >= 5:
            self.is_initialized = True
        
        if len(self.messages) >= self.max_messages:
            # 移除最旧的消息前，先检查是否需要摘要
            self._maybe_summarize()
            self.messages.pop(0)
        
        self.messages.append({
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {},
        })
        
        # 达到阈值时自动摘要（Claude Code 风格）
        if len(self.messages) >= self.auto_summarize_threshold:
            self._maybe_summarize()
    
    def _maybe_summarize(self):
        """
        条件性摘要（Claude Code 风格）
        
        当消息达到阈值时，提取关键信息并压缩
        """
        if len(self.messages) <= self.last_summarized_index + 1:
            return
        
        # 计算待摘要的消息
        pending_count = len(self.messages) - self.last_summarized_index - 1
        if pending_count < 10:  # 至少 10 条消息才摘要
            return
        
        # 简单摘要：提取关键信息
        new_summary = self._extract_summary(
            self.messages[self.last_summarized_index + 1:]
        )
        
        # 更新统计
        self.summarized_count += pending_count
        self.last_summarized_index = len(self.messages) - 1
        
        # 记录 token 估计
        self.extraction_token_count += len(new_summary) // 4
    
    def _extract_summary(self, messages: List[Dict]) -> str:
        """
        提取摘要（简化版）
        
        在生产环境中，这里可以接入 LLM 进行更智能的摘要
        """
        if not messages:
            return ""
        
        # 统计信息
        roles = {}
        total_chars = 0
        for msg in messages:
            role = msg.get('role', 'unknown')
            roles[role] = roles.get(role, 0) + 1
            total_chars += len(msg.get('content', ''))
        
        # 生成摘要
        summary = f"[摘要] 最近 {len(messages)} 条消息 ({total_chars} 字符)\n"
        summary += f"角色分布: {roles}\n"
        
        # 添加最近一条消息的预览
        if messages:
            last_msg = messages[-1].get('content', '')[:100]
            summary += f"\n最新: {last_msg}..."
        
        return summary
    
    def force_summarize(self):
        """强制摘要所有未摘要的消息"""
        if self.last_summarized_index < len(self.messages) - 1:
            self._maybe_summarize()
    
    def get_token_count(self) -> int:
        """获取消息的 token 估计"""
        total = 0
        for msg in self.messages:
            content = msg.get('content', '')
            # 简单估算：约 4 字符 = 1 token
            total += len(content) // 4
        return total
    
    def is_initialized_check(self) -> bool:
        """检查是否已初始化"""
        return self.is_initialized
    
    def get_extraction_stats(self) -> Dict[str, Any]:
        """获取摘要统计"""
        return {
            'is_initialized': self.is_initialized,
            'total_messages': len(self.messages),
            'summarized_count': self.summarized_count,
            'last_summarized_index': self.last_summarized_index,
            'extraction_token_count': self.extraction_token_count,
            'auto_summarize_threshold': self.auto_summarize_threshold,
        }
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态（Claude Code 风格）"""
        return {
            'messages_count': len(self.messages),
            'is_initialized': self.is_initialized,
            'summarized_count': self.summarized_count,
            'token_count': self.get_token_count(),
            'max_messages': self.max_messages,
        }
    
    def reset_memory(self):
        """重置记忆（Claude Code 风格）"""
        self.messages.clear()
        self.is_initialized = False
        self.summarized_count = 0
        self.last_summarized_index = -1
        self.extraction_token_count = 0
    
    def get_recent(self, n: int = 10) -> List[Dict[str, Any]]:
        """获取最近的 n 条消息"""
        return self.messages[-n:] if n > 0 else []
    
    def get_by_timerange(
        self,
        start: datetime,
        end: datetime
    ) -> List[Dict[str, Any]]:
        """按时间范围获取消息"""
        results = []
        for msg in self.messages:
            msg_time = datetime.fromisoformat(msg['timestamp'])
            if start <= msg_time <= end:
                results.append(msg)
        return results
    
    def search(self, query: str) -> List[Dict[str, Any]]:
        """搜索消息"""
        query_lower = query.lower()
        return [
            msg for msg in self.messages
            if query_lower in msg['content'].lower()
        ]


@dataclass
class BufferWindowMemory:
    """
    固定窗口记忆（来自 Flowise 灵感）
    
    特点：
    - 保留最近 K 条消息
    - 自动丢弃旧消息
    - 适用于对话场景
    """
    messages: List[Dict[str, Any]] = field(default_factory=list)
    window_size: int = 10                          # 窗口大小
    
    def __post_init__(self):
        # window_size 至少为 1
        self.window_size = max(1, self.window_size)
    
    def add_message(
        self,
        role: str,
        content: str,
        metadata: Dict[str, Any] = None
    ):
        """添加消息，自动维护窗口大小"""
        self.messages.append({
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {},
        })
        
        # 超过窗口大小时移除最旧的消息
        while len(self.messages) > self.window_size:
            self.messages.pop(0)
    
    def get_context(self) -> str:
        """获取窗口内的对话上下文"""
        if not self.messages:
            return ""
        
        lines = ["=== Recent Conversation ==="]
        for msg in self.messages:
            role = msg['role'].upper()
            content = msg['content'][:200]  # 截断长内容
            lines.append(f"{role}: {content}")
        
        return "\n".join(lines)
    
    def get_recent(self, n: int = None) -> List[Dict[str, Any]]:
        """获取最近的 n 条消息"""
        if n is None:
            n = self.window_size
        return self.messages[-n:] if n > 0 else []
    
    def clear(self):
        """清空窗口"""
        self.messages.clear()
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            'window_size': self.window_size,
            'current_messages': len(self.messages),
            'utilization': len(self.messages) / self.window_size if self.window_size > 0 else 0,
        }


@dataclass
class ConversationSummaryMemory:
    """
    对话摘要记忆（来自 Flowise 灵感）
    
    特点：
    - 自动生成对话摘要
    - 保留关键信息
    - 节省上下文空间
    """
    summary: str = ""                               # 当前摘要
    messages: List[Dict[str, Any]] = field(default_factory=list)
    max_messages_before_summarize: int = 20          # 多少消息后生成摘要
    summarized_count: int = 0                        # 已摘要的消息数
    
    def __post_init__(self):
        self.max_messages_before_summarize = max(1, self.max_messages_before_summarize)
    
    def add_message(
        self,
        role: str,
        content: str,
        metadata: Dict[str, Any] = None
    ):
        """添加消息，达到阈值时自动生成摘要"""
        self.messages.append({
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {},
        })
        
        # 达到阈值时生成摘要
        if len(self.messages) >= self.max_messages_before_summarize:
            self._summarize()
    
    def _summarize(self):
        """生成摘要（简化版，可扩展为 LLM 调用）"""
        if not self.messages:
            return
        
        # 简单摘要策略：提取关键信息
        total_chars = sum(len(m['content']) for m in self.messages)
        
        # 统计对话角色分布
        role_counts = {}
        for msg in self.messages:
            role = msg['role']
            role_counts[role] = role_counts.get(role, 0) + 1
        
        # 生成摘要
        self.summary = f"""[摘要] 共 {len(self.messages)} 条消息 ({total_chars} 字符)
角色分布: {role_counts}
时间范围: {self.messages[0]['timestamp'][:19]} ~ {self.messages[-1]['timestamp'][:19]}

关键内容预览:
{self.messages[-1]['content'][:200]}
"""
        
        # 清空已摘要的消息，保留摘要
        self.summarized_count += len(self.messages)
        self.messages.clear()
    
    def get_context(self) -> str:
        """获取记忆上下文（摘要 + 最近消息）"""
        parts = []
        
        if self.summary:
            parts.append(self.summary)
        
        if self.messages:
            parts.append("=== Recent Messages ===")
            for msg in self.messages:
                role = msg['role'].upper()
                content = msg['content'][:150]
                parts.append(f"{role}: {content}")
        
        return "\n".join(parts) if parts else ""
    
    def force_summarize(self):
        """强制生成摘要"""
        self._summarize()
    
    def clear(self):
        """清空摘要和消息"""
        self.summary = ""
        self.messages.clear()
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        return {
            'summary_length': len(self.summary),
            'pending_messages': len(self.messages),
            'total_summarized': self.summarized_count,
            'next_summarize_at': self.max_messages_before_summarize,
        }


class MemoryManager:
    """
    记忆管理器
    
    统一管理 Core Memory、Archival Memory、Recall Memory
    支持工具接口读写
    """
    
    def __init__(
        self,
        agent_id: str = "default",
        storage_dir: str = None,
        scratchpad: Scratchpad = None,
    ):
        """
        初始化记忆管理器
        
        Args:
            agent_id: Agent ID
            storage_dir: 存储目录
            scratchpad: Scratchpad 实例
        """
        self.agent_id = agent_id
        self.storage_dir = storage_dir or f".memory/{agent_id}"
        self.scratchpad = scratchpad
        
        # 初始化记忆系统
        self.core_memory = CoreMemory()
        self.archival_memory = ArchivalMemory()
        self.recall_memory = RecallMemory()
        
        # 新增：固定窗口记忆（来自 Flowise 灵感）
        self.buffer_window_memory = BufferWindowMemory(window_size=10)
        
        # 新增：对话摘要记忆（来自 Flowise 灵感）
        self.conversation_summary_memory = ConversationSummaryMemory(max_messages_before_summarize=20)
        
        # 初始化默认块
        self._init_default_blocks()
    
    def _init_default_blocks(self):
        """初始化默认块"""
        # Persona Block
        self.core_memory.add_block(MemoryBlock(
            label="persona",
            value="",
            memory_type=MemoryType.CORE,
            permission=BlockPermission.READ_WRITE,
            description="Agent 的人设和角色定义",
            limit=2000,
        ))
        
        # Human Block
        self.core_memory.add_block(MemoryBlock(
            label="human",
            value="",
            memory_type=MemoryType.CORE,
            permission=BlockPermission.READ_WRITE,
            description="用户信息和偏好",
            limit=2000,
        ))
        
        # Tasks Block
        self.core_memory.add_block(MemoryBlock(
            label="tasks",
            value=[],
            memory_type=MemoryType.CORE,
            permission=BlockPermission.READ_WRITE,
            description="当前任务列表",
            limit=3000,
        ))
        
        # Context Block
        self.core_memory.add_block(MemoryBlock(
            label="context",
            value={},
            memory_type=MemoryType.CORE,
            permission=BlockPermission.READ_WRITE,
            description="工作上下文信息",
            limit=3000,
        ))
    
    # ========== Core Memory 操作 ==========
    
    def core_memory_append(self, label: str, content: str) -> bool:
        """
        追加内容到核心记忆块
        
        Tool: core_memory_append
        """
        block = self.core_memory.get_block(label)
        if not block:
            return False
        
        current = block.read()
        new_value = current + "\n" + content if current else content
        return block.write(new_value)
    
    def core_memory_replace(self, label: str, old_content: str, new_content: str) -> bool:
        """
        替换核心记忆块中的内容
        
        Tool: core_memory_replace
        """
        block = self.core_memory.get_block(label)
        if not block:
            return False
        
        current = block.read()
        updated = current.replace(old_content, new_content)
        return block.write(updated)
    
    def core_memory_read(self, label: str = None) -> str:
        """
        读取核心记忆
        
        Tool: core_memory_read
        """
        if label:
            block = self.core_memory.get_block(label)
            return block.read() if block else ""
        return self.core_memory.get_context()
    
    # ========== Archival Memory 操作 ==========
    
    def archival_memory_insert(self, content: str, metadata: Dict = None) -> int:
        """
        插入到归档记忆
        
        Tool: archival_memory_insert
        """
        return self.archival_memory.insert(content, metadata)
    
    def archival_memory_search(self, query: str, top_k: int = 10) -> List[Dict]:
        """
        搜索归档记忆
        
        Tool: archival_memory_search
        """
        return self.archival_memory.search(query, top_k)
    
    # ========== Recall Memory 操作 ==========
    
    def conversation_search(self, query: str) -> List[Dict]:
        """
        搜索对话历史
        
        Tool: conversation_search
        """
        return self.recall_memory.search(query)
    
    def conversation_search_date(
        self,
        start_date: str,
        end_date: str
    ) -> List[Dict]:
        """
        按日期范围搜索对话
        
        Tool: conversation_search_date
        """
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        return self.recall_memory.get_by_timerange(start, end)
    
    # ========== 持久化 ==========
    
    def save(self):
        """保存记忆到文件"""
        os.makedirs(self.storage_dir, exist_ok=True)
        
        # 保存 Core Memory
        core_path = os.path.join(self.storage_dir, "core_memory.json")
        with open(core_path, 'w') as f:
            json.dump(self.core_memory.to_dict(), f, indent=2, ensure_ascii=False)
        
        # 保存 Archival Memory
        archival_path = os.path.join(self.storage_dir, "archival_memory.json")
        with open(archival_path, 'w') as f:
            json.dump({
                'entries': self.archival_memory.entries,
                'index': self.archival_memory.index,
            }, f, indent=2, ensure_ascii=False)
        
        # 保存 Recall Memory
        recall_path = os.path.join(self.storage_dir, "recall_memory.json")
        with open(recall_path, 'w') as f:
            json.dump({
                'messages': self.recall_memory.messages,
            }, f, indent=2, ensure_ascii=False)
        
        if self.scratchpad:
            self.scratchpad.log_thinking(
                f'记忆已保存到 {self.storage_dir}',
                confidence=1.0
            )
    
    def load(self):
        """从文件加载记忆"""
        # 加载 Core Memory
        core_path = os.path.join(self.storage_dir, "core_memory.json")
        if os.path.exists(core_path):
            with open(core_path) as f:
                data = json.load(f)
                self.core_memory = CoreMemory.from_dict(data)
        
        # 加载 Archival Memory
        archival_path = os.path.join(self.storage_dir, "archival_memory.json")
        if os.path.exists(archival_path):
            with open(archival_path) as f:
                data = json.load(f)
                self.archival_memory.entries = data.get('entries', [])
                self.archival_memory.index = data.get('index', {})
        
        # 加载 Recall Memory
        recall_path = os.path.join(self.storage_dir, "recall_memory.json")
        if os.path.exists(recall_path):
            with open(recall_path) as f:
                data = json.load(f)
                self.recall_memory.messages = data.get('messages', [])
    
    # ========== 工具接口 ==========
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """
        获取记忆工具定义
        
        用于注册到 Agent 的工具系统
        """
        return [
            {
                'name': 'core_memory_append',
                'description': '追加内容到核心记忆块',
                'parameters': {
                    'label': {'type': 'string', 'description': '块标签'},
                    'content': {'type': 'string', 'description': '要追加的内容'},
                },
                'function': self.core_memory_append,
            },
            {
                'name': 'core_memory_replace',
                'description': '替换核心记忆块中的内容',
                'parameters': {
                    'label': {'type': 'string', 'description': '块标签'},
                    'old_content': {'type': 'string', 'description': '旧内容'},
                    'new_content': {'type': 'string', 'description': '新内容'},
                },
                'function': self.core_memory_replace,
            },
            {
                'name': 'core_memory_read',
                'description': '读取核心记忆',
                'parameters': {
                    'label': {'type': 'string', 'description': '块标签（可选）'},
                },
                'function': self.core_memory_read,
            },
            {
                'name': 'archival_memory_insert',
                'description': '插入内容到归档记忆',
                'parameters': {
                    'content': {'type': 'string', 'description': '内容'},
                    'metadata': {'type': 'object', 'description': '元数据（可选）'},
                },
                'function': self.archival_memory_insert,
            },
            {
                'name': 'archival_memory_search',
                'description': '搜索归档记忆',
                'parameters': {
                    'query': {'type': 'string', 'description': '搜索查询'},
                    'top_k': {'type': 'integer', 'description': '返回数量', 'default': 10},
                },
                'function': self.archival_memory_search,
            },
            {
                'name': 'conversation_search',
                'description': '搜索对话历史',
                'parameters': {
                    'query': {'type': 'string', 'description': '搜索查询'},
                },
                'function': self.conversation_search,
            },
        ]
    
    def get_status(self) -> Dict[str, Any]:
        """获取记忆状态"""
        return {
            'agent_id': self.agent_id,
            'core_memory': {
                'blocks': len(self.core_memory.blocks),
                'total_size': sum(len(b.read()) for b in self.core_memory.blocks.values()),
            },
            'archival_memory': {
                'entries': len(self.archival_memory.entries),
                'index_size': len(self.archival_memory.index),
            },
            'recall_memory': {
                'messages': len(self.recall_memory.messages),
                'max_messages': self.recall_memory.max_messages,
            },
            'buffer_window_memory': self.buffer_window_memory.get_status(),
            'conversation_summary_memory': self.conversation_summary_memory.get_status(),
        }
