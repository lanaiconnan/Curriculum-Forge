"""Scratchpad 日志系统

基于 dexter 的 Scratchpad 设计，
完整记录执行过程，便于调试和追溯。
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import os


@dataclass
class LogEntry:
    """日志条目"""
    type: str  # thinking, tool_call, result, error, reflection
    timestamp: str
    data: Dict[str, Any]
    
    def to_dict(self) -> dict:
        return {
            'type': self.type,
            'timestamp': self.timestamp,
            **self.data
        }


@dataclass
class ScratchpadSession:
    """Scratchpad 会话"""
    session_id: str
    started_at: str
    ended_at: Optional[str]
    entries: List[LogEntry]
    
    def to_jsonl(self) -> str:
        """转换为 JSONL 格式"""
        lines = []
        for entry in self.entries:
            lines.append(json.dumps(entry.to_dict()))
        return '\n'.join(lines)


class Scratchpad:
    """
    Scratchpad 日志系统
    
    完整记录执行过程，包括：
    - 思考过程
    - 工具调用
    - 执行结果
    - 错误信息
    - 反思内容
    
    参考自 dexter 的 Scratchpad 设计。
    """
    
    def __init__(self, base_dir: str = ".scratchpad"):
        """
        初始化 Scratchpad
        
        Args:
            base_dir: 日志存储目录
        """
        self.base_dir = base_dir
        self._ensure_dir()
        
        # 创建新会话
        self.session = self._create_session()
        self.entries = self.session.entries
    
    def _ensure_dir(self):
        """确保目录存在"""
        os.makedirs(self.base_dir, exist_ok=True)
    
    def _create_session(self) -> ScratchpadSession:
        """创建新会话"""
        session_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        return ScratchpadSession(
            session_id=session_id,
            started_at=datetime.now().isoformat(),
            ended_at=None,
            entries=[],
        )
    
    def _now(self) -> str:
        """获取当前时间戳"""
        return datetime.now().isoformat()
    
    def _add_entry(self, entry_type: str, data: Dict[str, Any]):
        """添加日志条目"""
        entry = LogEntry(
            type=entry_type,
            timestamp=self._now(),
            data=data,
        )
        self.entries.append(entry)
    
    def log(self, entry_type: str, data: Dict[str, Any]):
        """
        通用日志方法
        
        Args:
            entry_type: 条目类型
            data: 数据内容
        """
        self._add_entry(entry_type, data)
    
    def log_thinking(self, thought: str, confidence: float = None, context: str = None):
        """
        记录思考过程
        
        Args:
            thought: 思考内容
            confidence: 置信度（可选）
            context: 上下文（可选）
        """
        self._add_entry('thinking', {
            'thought': thought,
            'confidence': confidence,
            'context': context,
        })
    
    def log_tool_call(self, tool: str, args: Dict[str, Any], result: Any = None):
        """
        记录工具调用
        
        Args:
            tool: 工具名称
            args: 调用参数
            result: 执行结果（可选）
        """
        entry_data = {
            'tool': tool,
            'args': args,
        }
        
        if result is not None:
            # 简化结果，避免过大的日志
            if isinstance(result, dict):
                # 只保留关键信息
                simplified = {k: v for k, v in result.items() if k in ['status', 'score', 'reward', 'message']}
                entry_data['result'] = simplified
            elif isinstance(result, (str, int, float, bool)):
                entry_data['result'] = result
            else:
                entry_data['result'] = str(result)[:500]  # 截断过长的结果
        
        self._add_entry('tool_call', entry_data)
    
    def log_result(self, status: str, message: str, metrics: Dict[str, float] = None):
        """
        记录执行结果
        
        Args:
            status: 状态 (success, failure, timeout)
            message: 结果消息
            metrics: 指标（可选）
        """
        self._add_entry('result', {
            'status': status,
            'message': message,
            'metrics': metrics or {},
        })
    
    def log_error(self, error: str, stack: str = None):
        """
        记录错误
        
        Args:
            error: 错误消息
            stack: 堆栈信息（可选）
        """
        self._add_entry('error', {
            'error': error,
            'stack': stack,
        })
    
    def log_reflection(self, analysis: str, issues: List[str] = None, improvements: List[str] = None):
        """
        记录反思
        
        Args:
            analysis: 分析内容
            issues: 发现的问题（可选）
            improvements: 改进建议（可选）
        """
        self._add_entry('reflection', {
            'analysis': analysis,
            'issues': issues or [],
            'improvements': improvements or [],
        })
    
    def log_experiment(self, experiment_id: str, config: Dict[str, Any], status: str):
        """
        记录实验
        
        Args:
            experiment_id: 实验 ID
            config: 实验配置
            status: 实验状态
        """
        self._add_entry('experiment', {
            'experiment_id': experiment_id,
            'config': config,
            'status': status,
        })
    
    def log_reward(self, total: float, breakdown: Dict[str, float], verification: Dict[str, Any] = None):
        """
        记录奖励计算
        
        Args:
            total: 总奖励
            breakdown: 奖励分解
            verification: 验证结果（可选）
        """
        entry_data = {
            'total': total,
            'breakdown': breakdown,
        }
        
        if verification:
            entry_data['verification'] = {
                'exact_match': verification.get('exact_match'),
                'partial_match': verification.get('partial_match'),
                'confidence': verification.get('confidence'),
            }
        
        self._add_entry('reward', entry_data)
    
    def save(self, filename: str = None) -> str:
        """
        保存日志到文件
        
        Args:
            filename: 文件名（可选，默认使用会话 ID）
        
        Returns:
            str: 保存的文件路径
        """
        if filename is None:
            filename = f"{self.session.session_id}.jsonl"
        
        filepath = os.path.join(self.base_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(self.session.to_jsonl())
        
        return filepath
    
    def load(self, filename: str) -> ScratchpadSession:
        """
        从文件加载日志
        
        Args:
            filename: 文件名
        
        Returns:
            ScratchpadSession: 加载的会话
        """
        filepath = os.path.join(self.base_dir, filename)
        
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Scratchpad file not found: {filepath}")
        
        entries = []
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    entry = LogEntry(
                        type=data.get('type', 'unknown'),
                        timestamp=data.get('timestamp', ''),
                        data={k: v for k, v in data.items() if k not in ['type', 'timestamp']},
                    )
                    entries.append(entry)
        
        return ScratchpadSession(
            session_id=filename.replace('.jsonl', ''),
            started_at=entries[0].timestamp if entries else '',
            ended_at=entries[-1].timestamp if entries else None,
            entries=entries,
        )
    
    def get_entries(self, entry_type: str = None) -> List[LogEntry]:
        """
        获取日志条目
        
        Args:
            entry_type: 条目类型过滤（可选）
        
        Returns:
            List[LogEntry]: 日志条目列表
        """
        if entry_type is None:
            return self.entries
        
        return [e for e in self.entries if e.type == entry_type]
    
    def get_thinkings(self) -> List[Dict]:
        """获取所有思考记录"""
        return [e.data for e in self.get_entries('thinking')]
    
    def get_tool_calls(self) -> List[Dict]:
        """获取所有工具调用"""
        return [e.data for e in self.get_entries('tool_call')]
    
    def get_errors(self) -> List[Dict]:
        """获取所有错误"""
        return [e.data for e in self.get_entries('error')]
    
    def print_summary(self):
        """打印摘要"""
        print(f"\n📝 Scratchpad Summary")
        print(f"   Session: {self.session.session_id}")
        print(f"   Started: {self.session.started_at}")
        print(f"   Entries: {len(self.entries)}")
        
        # 统计各类型条目
        type_counts = {}
        for entry in self.entries:
            type_counts[entry.type] = type_counts.get(entry.type, 0) + 1
        
        print(f"\n   Type breakdown:")
        for entry_type, count in type_counts.items():
            print(f"      - {entry_type}: {count}")
    
    def print_thinkings(self):
        """打印所有思考"""
        thinkings = self.get_thinkings()
        if not thinkings:
            print("\n💭 No thinking records")
            return
        
        print(f"\n💭 Thinkings ({len(thinkings)}):")
        for i, thinking in enumerate(thinkings, 1):
            print(f"\n   {i}. {thinking.get('thought', '')[:100]}")
            if thinking.get('confidence'):
                print(f"      Confidence: {thinking['confidence']:.1%}")
    
    def print_tool_calls(self):
        """打印所有工具调用"""
        calls = self.get_tool_calls()
        if not calls:
            print("\n🔧 No tool calls")
            return
        
        print(f"\n🔧 Tool Calls ({len(calls)}):")
        for i, call in enumerate(calls, 1):
            print(f"\n   {i}. {call.get('tool')}")
            print(f"      Args: {call.get('args')}")
    
    def __repr__(self) -> str:
        return f"Scratchpad(session={self.session.session_id}, entries={len(self.entries)})"


class ScratchpadManager:
    """Scratchpad 管理器"""
    
    def __init__(self, base_dir: str = ".scratchpad"):
        self.base_dir = base_dir
        self.current: Optional[Scratchpad] = None
    
    def create(self) -> Scratchpad:
        """创建新的 Scratchpad"""
        self.current = Scratchpad(self.base_dir)
        return self.current
    
    def save_current(self) -> str:
        """保存当前的 Scratchpad"""
        if self.current is None:
            raise ValueError("No active Scratchpad")
        return self.current.save()
    
    def list_sessions(self) -> List[str]:
        """列出所有会话"""
        os.makedirs(self.base_dir, exist_ok=True)
        files = [f for f in os.listdir(self.base_dir) if f.endswith('.jsonl')]
        return sorted(files, reverse=True)
    
    def load(self, filename: str) -> Scratchpad:
        """加载会话"""
        filepath = os.path.join(self.base_dir, filename)
        
        scratchpad = Scratchpad(self.base_dir)
        session = scratchpad.load(filename)
        
        return scratchpad
