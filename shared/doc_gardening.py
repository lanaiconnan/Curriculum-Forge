"""DocGardeningAgent - 文档整理 Agent

来自 OpenAI 的灵感：
- 定期扫描过时的文档
- 发起到期文档的修复
- 保持知识库最新

核心功能：
1. 扫描文档更新时间
2. 检测过期文档
3. 发起修复流程
4. 记录整理历史
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime, timedelta
from enum import Enum
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


class DocStatus(Enum):
    """文档状态"""
    CURRENT = "current"           # 最新
    STALE = "stale"               # 过期
    OUTDATED = "outdated"         # 严重过期
    UNKNOWN = "unknown"            # 未知


@dataclass
class DocInfo:
    """文档信息"""
    path: str
    name: str
    last_modified: datetime
    last_reviewed: datetime
    status: DocStatus
    age_days: int
    suggestions: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'path': self.path,
            'name': self.name,
            'last_modified': self.last_modified.isoformat(),
            'last_reviewed': self.last_reviewed.isoformat(),
            'status': self.status.value,
            'age_days': self.age_days,
            'suggestions': self.suggestions,
        }


@dataclass
class GardenReport:
    """整理报告"""
    timestamp: str
    total_docs: int
    current_docs: int
    stale_docs: int
    outdated_docs: int
    scanned_dirs: List[str]
    actions_taken: List[str]
    summary: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'total_docs': self.total_docs,
            'current_docs': self.current_docs,
            'stale_docs': self.stale_docs,
            'outdated_docs': self.outdated_docs,
            'scanned_dirs': self.scanned_dirs,
            'actions_taken': self.actions_taken,
            'summary': self.summary,
        }


class DocGardeningAgent:
    """
    文档整理 Agent
    
    来自 OpenAI 的灵感：
    - 定期运行的 doc-gardening Agent
    - 专门扫描那些过时的文档
    - 发起到修复
    
    这样知识库始终是最新的。
    """
    
    def __init__(
        self,
        workspace: str = ".",
        scratchpad: Scratchpad = None,
        stale_threshold_days: int = 7,
        outdated_threshold_days: int = 30,
        scan_dirs: List[str] = None,
        file_extensions: List[str] = None,
    ):
        """
        初始化 DocGardeningAgent
        
        Args:
            workspace: 工作区路径
            scratchpad: Scratchpad 日志实例
            stale_threshold_days: 过期阈值（天）
            outdated_threshold_days: 严重过期阈值（天）
            scan_dirs: 扫描目录列表
            file_extensions: 扫描文件扩展名
        """
        self.workspace = workspace
        self.scratchpad = scratchpad
        self.stale_threshold = timedelta(days=stale_threshold_days)
        self.outdated_threshold = timedelta(days=outdated_threshold_days)
        self.scan_dirs = scan_dirs or ['docs', '.scratchpad', 'agent_a', 'agent_b', 'rl', 'shared']
        self.file_extensions = file_extensions or ['.md', '.py', '.txt', '.json']
        
        # 历史记录
        self.history: List[GardenReport] = []
        
        # 状态文件
        self.state_file = os.path.join(workspace, '.doc_garden_state.json')
    
    def _log_thinking(self, thought: str, confidence: float = None):
        """记录思考日志"""
        if self.scratchpad:
            self.scratchpad.log_thinking(
                thought=thought,
                confidence=confidence,
                context='DocGardeningAgent'
            )
    
    # ========== 核心功能 ==========
    
    def scan(self, force: bool = False) -> GardenReport:
        """
        扫描文档状态
        
        Args:
            force: 是否强制扫描（忽略缓存）
        
        Returns:
            GardenReport: 整理报告
        """
        self._log_thinking(f'开始扫描文档目录: {self.scan_dirs}', confidence=0.9)
        
        # 获取上次扫描时间
        last_scan = self._get_last_scan_time()
        now = datetime.now()
        
        # 检查是否需要扫描
        if last_scan and not force:
            time_since_scan = now - last_scan
            if time_since_scan < self.stale_threshold:
                self._log_thinking(
                    f'上次扫描 {time_since_scan.days} 天前，尚未达到阈值',
                    confidence=0.8
                )
        
        # 扫描文档
        docs = self._scan_directories()
        
        # 分类文档
        current_docs = []
        stale_docs = []
        outdated_docs = []
        
        for doc in docs:
            if doc.status == DocStatus.CURRENT:
                current_docs.append(doc)
            elif doc.status == DocStatus.STALE:
                stale_docs.append(doc)
            elif doc.status == DocStatus.OUTDATED:
                outdated_docs.append(doc)
        
        # 生成建议
        self._generate_suggestions(current_docs, stale_docs, outdated_docs)
        
        # 构建报告
        report = GardenReport(
            timestamp=now.isoformat(),
            total_docs=len(docs),
            current_docs=len(current_docs),
            stale_docs=len(stale_docs),
            outdated_docs=len(outdated_docs),
            scanned_dirs=self.scan_dirs,
            actions_taken=[],
            summary=self._generate_summary(len(current_docs), len(stale_docs), len(outdated_docs)),
        )
        
        # 更新状态
        self._update_state(now)
        self.history.append(report)
        
        self._log_thinking(
            f'扫描完成: {report.total_docs} 个文档，'
            f'{report.stale_docs} 个过期，{report.outdated_docs} 个严重过期',
            confidence=0.95
        )
        
        return report
    
    def _scan_directories(self) -> List[DocInfo]:
        """扫描目录"""
        docs = []
        now = datetime.now()
        
        for scan_dir in self.scan_dirs:
            full_path = os.path.join(self.workspace, scan_dir)
            
            if not os.path.exists(full_path) or not os.path.isdir(full_path):
                continue
            
            for root, _, files in os.walk(full_path):
                for file in files:
                    # 检查扩展名
                    if not any(file.endswith(ext) for ext in self.file_extensions):
                        continue
                    
                    # 获取文档信息
                    file_path = os.path.join(root, file)
                    doc_info = self._get_doc_info(file_path, now)
                    
                    if doc_info:
                        docs.append(doc_info)
        
        return docs
    
    def _get_doc_info(self, file_path: str, now: datetime) -> Optional[DocInfo]:
        """获取文档信息"""
        try:
            stat = os.stat(file_path)
            last_modified = datetime.fromtimestamp(stat.st_mtime)
            
            # 计算年龄
            age = now - last_modified
            
            # 判断状态
            if age < self.stale_threshold:
                status = DocStatus.CURRENT
            elif age < self.outdated_threshold:
                status = DocStatus.STALE
            else:
                status = DocStatus.OUTDATED
            
            # 获取上次审阅时间（从状态文件）
            last_reviewed = self._get_last_reviewed(file_path)
            
            return DocInfo(
                path=file_path,
                name=os.path.basename(file_path),
                last_modified=last_modified,
                last_reviewed=last_reviewed,
                status=status,
                age_days=age.days,
                suggestions=[],
            )
        except Exception:
            return None
    
    def _get_last_scan_time(self) -> Optional[datetime]:
        """获取上次扫描时间"""
        if not os.path.exists(self.state_file):
            return None
        
        try:
            import json
            with open(self.state_file) as f:
                state = json.load(f)
                if 'last_scan' in state:
                    return datetime.fromisoformat(state['last_scan'])
        except Exception:
            pass
        
        return None
    
    def _get_last_reviewed(self, file_path: str) -> datetime:
        """获取上次审阅时间"""
        if not os.path.exists(self.state_file):
            return datetime.now()
        
        try:
            import json
            with open(self.state_file) as f:
                state = json.load(f)
                reviewed = state.get('reviewed_docs', {})
                if file_path in reviewed:
                    return datetime.fromisoformat(reviewed[file_path])
        except Exception:
            pass
        
        return datetime.now()
    
    def _update_state(self, scan_time: datetime):
        """更新状态文件"""
        import json
        
        state = {
            'last_scan': scan_time.isoformat(),
            'reviewed_docs': {},
        }
        
        # 保留已有的审阅时间
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file) as f:
                    old_state = json.load(f)
                    state['reviewed_docs'] = old_state.get('reviewed_docs', {})
            except Exception:
                pass
        
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)
    
    def _generate_suggestions(
        self,
        current: List[DocInfo],
        stale: List[DocInfo],
        outdated: List[DocInfo]
    ):
        """生成建议"""
        for doc in stale:
            doc.suggestions.append(f'文档 {doc.name} 已 {doc.age_days} 天未更新，建议审阅')
        
        for doc in outdated:
            doc.suggestions.append(f'⚠️ 文档 {doc.name} 已 {doc.age_days} 天未更新，需要立即审阅')
            doc.suggestions.append('建议：检查内容是否仍然准确，删除或归档不相关的文档')
    
    def _generate_summary(self, current: int, stale: int, outdated: int) -> str:
        """生成摘要"""
        parts = []
        
        if current > 0:
            parts.append(f'{current} 个文档最新')
        if stale > 0:
            parts.append(f'{stale} 个文档需要审阅')
        if outdated > 0:
            parts.append(f'{outdated} 个文档严重过期')
        
        return '，'.join(parts) if parts else '所有文档状态良好'
    
    # ========== 修复功能 ==========
    
    def trigger_fix(self, doc_info: DocInfo) -> Dict[str, Any]:
        """
        发起到文档修复
        
        Args:
            doc_info: 文档信息
        
        Returns:
            Dict: 修复任务信息
        """
        self._log_thinking(f'发起到文档修复: {doc_info.name}', confidence=0.8)
        
        # 更新审阅时间
        self._mark_reviewed(doc_info.path)
        
        return {
            'task': 'review_doc',
            'doc_path': doc_info.path,
            'doc_name': doc_info.name,
            'age_days': doc_info.age_days,
            'suggestions': doc_info.suggestions,
            'priority': 'high' if doc_info.status == DocStatus.OUTDATED else 'medium',
        }
    
    def _mark_reviewed(self, file_path: str):
        """标记文档已审阅"""
        import json
        
        state = {'last_scan': datetime.now().isoformat(), 'reviewed_docs': {}}
        
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file) as f:
                    state = json.load(f)
            except Exception:
                pass
        
        state['reviewed_docs'][file_path] = datetime.now().isoformat()
        
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)
    
    def mark_current(self, file_path: str):
        """标记文档为最新"""
        self._mark_reviewed(file_path)
        self._log_thinking(f'标记文档为最新: {file_path}', confidence=0.9)
    
    # ========== 报告功能 ==========
    
    def print_report(self, report: GardenReport):
        """打印报告"""
        print("\n" + "=" * 60)
        print("🌱 DocGardening Report")
        print("=" * 60)
        
        print(f"\n⏰ {report.timestamp}")
        print(f"📁 扫描目录: {', '.join(report.scanned_dirs)}")
        
        print(f"\n📊 文档状态统计:")
        print(f"   最新: {report.current_docs}")
        print(f"   过期: {report.stale_docs}")
        print(f"   严重过期: {report.outdated_docs}")
        
        if report.stale_docs > 0 or report.outdated_docs > 0:
            print(f"\n⚠️  需要关注的文档:")
            
            docs = self._scan_directories()
            for doc in docs:
                if doc.status in [DocStatus.STALE, DocStatus.OUTDATED]:
                    status_icon = '🔴' if doc.status == DocStatus.OUTDATED else '🟡'
                    print(f"   {status_icon} {doc.name} ({doc.age_days} 天)")
                    for suggestion in doc.suggestions[:1]:
                        print(f"      → {suggestion}")
        
        print(f"\n📋 摘要: {report.summary}")
        print("=" * 60)
    
    def get_stale_docs(self) -> List[DocInfo]:
        """获取过期文档列表"""
        docs = self._scan_directories()
        return [d for d in docs if d.status in [DocStatus.STALE, DocStatus.OUTDATED]]
    
    def get_outdated_docs(self) -> List[DocInfo]:
        """获取严重过期文档列表"""
        docs = self._scan_directories()
        return [d for d in docs if d.status == DocStatus.OUTDATED]
