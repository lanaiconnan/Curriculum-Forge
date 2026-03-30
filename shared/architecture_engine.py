"""ArchitectureRuleEngine - 架构规则引擎

来自 OpenAI 的灵感：
- 定义严格的架构规则
- 代码只能按固定方向依赖
- 违反规则的代码会被自动拦截

核心功能：
1. 定义架构层次
2. 依赖方向检查
3. 违规报告生成
4. 自动修复建议
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable, Set, Tuple
from datetime import datetime
from enum import Enum
import os
import re
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from shared.scratchpad import Scratchpad
    SCRATCHPAD_AVAILABLE = True
except ImportError:
    SCRATCHPAD_AVAILABLE = False
    Scratchpad = None


class ViolationSeverity(Enum):
    """违规严重程度"""
    CRITICAL = "critical"    # 必须修复
    MAJOR = "major"         # 应该修复
    MINOR = "minor"         # 建议修复
    INFO = "info"           # 信息


@dataclass
class ImportInfo:
    """导入信息"""
    module: str           # 模块名
    line_number: int       # 行号
    imported_name: Optional[str] = None


@dataclass
class Violation:
    """违规信息"""
    severity: ViolationSeverity
    file_path: str
    line_number: int
    rule_name: str
    message: str
    from_module: str
    to_module: str
    suggestion: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'severity': self.severity.value,
            'file_path': self.file_path,
            'line_number': self.line_number,
            'rule_name': self.rule_name,
            'message': self.message,
            'from_module': self.from_module,
            'to_module': self.to_module,
            'suggestion': self.suggestion,
        }


@dataclass
class Rule:
    """架构规则"""
    name: str
    description: str
    allowed_layers: List[str]      # 允许的层次
    layer_order: List[str]         # 层次顺序（从低到高）
    allowed_dependencies: Dict[str, List[str]]  # 允许的依赖关系
    forbidden_dependencies: List[Tuple[str, str]]  # 禁止的依赖关系
    
    def can_depend(self, from_layer: str, to_layer: str) -> bool:
        """检查是否允许依赖"""
        # 检查层次顺序（只能从低层依赖高层）
        if from_layer in self.layer_order and to_layer in self.layer_order:
            from_idx = self.layer_order.index(from_layer)
            to_idx = self.layer_order.index(to_layer)
            # 只能从低层到高层（或同层）
            if to_idx < from_idx:
                return False
        
        # 检查允许的依赖关系
        if self.allowed_dependencies:
            allowed = self.allowed_dependencies.get(from_layer, [])
            if allowed and to_layer not in allowed and '*' not in allowed:
                return False
        
        # 检查禁止的依赖关系
        if (from_layer, to_layer) in self.forbidden_dependencies:
            return False
        
        return True


@dataclass
class ArchitectureReport:
    """架构报告"""
    timestamp: str
    total_files: int
    total_violations: int
    critical_violations: int
    major_violations: int
    minor_violations: int
    violations: List[Violation]
    summary: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'total_files': self.total_files,
            'total_violations': self.total_violations,
            'critical_violations': self.critical_violations,
            'major_violations': self.major_violations,
            'minor_violations': self.minor_violations,
            'violations': [v.to_dict() for v in self.violations],
            'summary': self.summary,
        }


class ArchitectureRuleEngine:
    """
    架构规则引擎
    
    来自 OpenAI 的灵感：
    - 代码只能按 Types → Config → Repo → Service → Runtime → UI 这个方向依赖
    - 违反规则的代码会被自动拦截
    - 有了这些约束，AI 写的代码就不会乱
    
    这样速度不会下降，架构不会漂移。
    """
    
    # 默认架构层次（从低到高）
    DEFAULT_LAYER_ORDER = [
        'types',      # 类型定义
        'config',     # 配置
        'repo',       # 数据仓库
        'service',    # 服务层
        'runtime',    # 运行时
        'ui',         # 用户界面
    ]
    
    # 默认规则
    DEFAULT_RULES = [
        Rule(
            name='dependency_direction',
            description='依赖方向只能从低层到高层',
            allowed_layers=['types', 'config', 'repo', 'service', 'runtime', 'ui'],
            layer_order=DEFAULT_LAYER_ORDER,
            allowed_dependencies={},
            forbidden_dependencies=[],
        ),
        Rule(
            name='no_circular_dependency',
            description='禁止循环依赖',
            allowed_layers=[],
            layer_order=[],
            allowed_dependencies={},
            forbidden_dependencies=[],
        ),
    ]
    
    def __init__(
        self,
        workspace: str = ".",
        scratchpad: Scratchpad = None,
        rules: List[Rule] = None,
        layer_mapping: Dict[str, str] = None,
    ):
        """
        初始化架构规则引擎
        
        Args:
            workspace: 工作区路径
            scratchpad: Scratchpad 日志实例
            rules: 自定义规则列表
            layer_mapping: 文件路径到层次的映射
        """
        self.workspace = workspace
        self.scratchpad = scratchpad
        self.rules = rules or self.DEFAULT_RULES
        
        # 文件路径到层次的映射
        self.layer_mapping = layer_mapping or self._default_layer_mapping()
        
        # 违规记录
        self.violations: List[Violation] = []
    
    def _log_thinking(self, thought: str, confidence: float = None):
        """记录思考日志"""
        if self.scratchpad:
            self.scratchpad.log_thinking(
                thought=thought,
                confidence=confidence,
                context='ArchitectureRuleEngine'
            )
    
    def _default_layer_mapping(self) -> Dict[str, str]:
        """默认层次映射"""
        return {
            '/types/': 'types',
            '/config/': 'config',
            '/repo/': 'repo',
            '/repository/': 'repo',
            '/data/': 'repo',
            '/service/': 'service',
            '/services/': 'service',
            '/business/': 'service',
            '/runtime/': 'runtime',
            '/engine/': 'runtime',
            '/ui/': 'ui',
            '/views/': 'ui',
            '/components/': 'ui',
            '/frontend/': 'ui',
        }
    
    def get_layer(self, file_path: str) -> str:
        """获取文件所属层次"""
        for pattern, layer in self.layer_mapping.items():
            if pattern in file_path:
                return layer
        return 'unknown'
    
    # ========== 核心功能 ==========
    
    def validate(self, file_path: str, content: str = None) -> List[Violation]:
        """
        验证文件是否违反架构规则
        
        Args:
            file_path: 文件路径
            content: 文件内容（如果为 None，从文件读取）
        
        Returns:
            List[Violation]: 违规列表
        """
        self._log_thinking(f'验证文件: {file_path}', confidence=0.9)
        
        violations = []
        
        # 获取文件内容
        if content is None:
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
            except Exception:
                return violations
        
        # 解析导入
        imports = self._parse_imports(content)
        
        # 检查每个导入
        from_layer = self.get_layer(file_path)
        
        for imp in imports:
            to_layer = self.get_layer(imp.module)
            
            if to_layer == 'unknown':
                continue
            
            # 检查依赖方向
            for rule in self.rules:
                if rule.name == 'dependency_direction':
                    if not rule.can_depend(from_layer, to_layer):
                        violations.append(Violation(
                            severity=ViolationSeverity.CRITICAL if from_layer == 'ui' else ViolationSeverity.MAJOR,
                            file_path=file_path,
                            line_number=imp.line_number,
                            rule_name=rule.name,
                            message=f'"{from_layer}" 不应该依赖 "{to_layer}"',
                            from_module=from_layer,
                            to_module=to_layer,
                            suggestion=f'重构为从 "{from_layer}" 到更高层的依赖，或将 "{to_layer}" 移到更低层',
                        ))
        
        return violations
    
    def validate_all(self, extensions: List[str] = None) -> ArchitectureReport:
        """
        验证所有文件
        
        Args:
            extensions: 要验证的文件扩展名
        
        Returns:
            ArchitectureReport: 架构报告
        """
        self._log_thinking('开始验证所有文件的架构规则', confidence=0.9)
        
        extensions = extensions or ['.py', '.js', '.ts', '.tsx']
        violations = []
        total_files = 0
        
        for root, _, files in os.walk(self.workspace):
            # 跳过隐藏目录和特殊目录
            if any(p.startswith('.') for p in root.split(os.sep)):
                continue
            
            for file in files:
                if not any(file.endswith(ext) for ext in extensions):
                    continue
                
                file_path = os.path.join(root, file)
                file_violations = self.validate(file_path)
                
                if file_violations:
                    violations.extend(file_violations)
                
                total_files += 1
        
        # 分类违规
        critical = len([v for v in violations if v.severity == ViolationSeverity.CRITICAL])
        major = len([v for v in violations if v.severity == ViolationSeverity.MAJOR])
        minor = len([v for v in violations if v.severity == ViolationSeverity.MINOR])
        
        report = ArchitectureReport(
            timestamp=datetime.now().isoformat(),
            total_files=total_files,
            total_violations=len(violations),
            critical_violations=critical,
            major_violations=major,
            minor_violations=minor,
            violations=violations,
            summary=self._generate_summary(len(violations), critical, major),
        )
        
        self.violations = violations
        self._log_thinking(f'验证完成: {len(violations)} 个违规', confidence=0.95)
        
        return report
    
    def _parse_imports(self, content: str) -> List[ImportInfo]:
        """解析 Python 文件中的导入"""
        imports = []
        
        # Python import 正则
        import_pattern = re.compile(r'^import\s+(\S+)', re.MULTILINE)
        from_import_pattern = re.compile(r'^from\s+(\S+)\s+import', re.MULTILINE)
        
        for i, line in enumerate(content.split('\n'), 1):
            line = line.strip()
            
            # import xxx
            match = import_pattern.match(line)
            if match:
                imports.append(ImportInfo(
                    module=match.group(1).split('.')[0],
                    line_number=i,
                ))
            
            # from xxx import yyy
            match = from_import_pattern.match(line)
            if match:
                module = match.group(1).split('.')[0]
                imports.append(ImportInfo(
                    module=module,
                    line_number=i,
                ))
        
        return imports
    
    def _generate_summary(self, total: int, critical: int, major: int) -> str:
        """生成摘要"""
        if total == 0:
            return '架构检查通过！无违规。'
        
        parts = [f'{total} 个违规']
        if critical > 0:
            parts.append(f'{critical} 个严重')
        if major > 0:
            parts.append(f'{major} 个主要')
        
        return '，'.join(parts)
    
    # ========== 修复功能 ==========
    
    def suggest_fix(self, violation: Violation) -> str:
        """
        建议修复方案
        
        Args:
            violation: 违规信息
        
        Returns:
            str: 修复建议
        """
        suggestions = []
        
        # 基于违规类型生成建议
        if violation.severity == ViolationSeverity.CRITICAL:
            suggestions.append('⚠️ 这是严重违规，必须修复！')
        
        suggestions.append(f'问题：{violation.message}')
        suggestions.append(f'建议：{violation.suggestion}')
        
        # 具体的重构建议
        if violation.from_module == 'ui' and violation.to_module in ['service', 'repo']:
            suggestions.append(
                '提示：UI 层不应该直接依赖业务层或数据层。'
                '建议通过接口/依赖注入来解耦。'
            )
        
        if violation.from_module == 'service' and violation.to_module == 'ui':
            suggestions.append(
                '提示：服务层不应该依赖 UI 层。'
                '考虑使用回调或事件来解耦。'
            )
        
        return '\n'.join(suggestions)
    
    # ========== 报告功能 ==========
    
    def print_report(self, report: ArchitectureReport):
        """打印报告"""
        print("\n" + "=" * 60)
        print("🏛️ Architecture Report")
        print("=" * 60)
        
        print(f"\n⏰ {report.timestamp}")
        print(f"📁 扫描文件: {report.total_files}")
        
        print(f"\n📊 违规统计:")
        print(f"   总数: {report.total_violations}")
        print(f"   🔴 严重: {report.critical_violations}")
        print(f"   🟠 主要: {report.major_violations}")
        print(f"   🟡 轻微: {report.minor_violations}")
        
        if report.violations:
            print(f"\n⚠️ 违规详情:")
            
            for v in report.violations[:10]:  # 只显示前 10 个
                icon = {
                    ViolationSeverity.CRITICAL: '🔴',
                    ViolationSeverity.MAJOR: '🟠',
                    ViolationSeverity.MINOR: '🟡',
                    ViolationSeverity.INFO: 'ℹ️',
                }.get(v.severity, '⚪')
                
                print(f"\n   {icon} {v.file_path}:{v.line_number}")
                print(f"      {v.message}")
                print(f"      建议: {v.suggestion}")
            
            if len(report.violations) > 10:
                print(f"\n   ... 还有 {len(report.violations) - 10} 个违规")
        
        print(f"\n📋 摘要: {report.summary}")
        print("=" * 60)
    
    def should_block(self, report: ArchitectureReport) -> bool:
        """
        判断是否应该阻止提交/合并
        
        Args:
            report: 架构报告
        
        Returns:
            bool: 如果有严重违规返回 True
        """
        return report.critical_violations > 0 or report.major_violations > 2
    
    def get_fix_commands(self, report: ArchitectureReport) -> List[str]:
        """
        生成修复命令
        
        Args:
            report: 架构报告
        
        Returns:
            List[str]: 修复命令列表
        """
        commands = []
        
        if report.critical_violations > 0:
            commands.append('🚨 发现严重违规，必须修复后才能继续！')
            commands.append('')
        
        for v in report.violations:
            commands.append(f'# {v.severity.value.upper()}: {v.file_path}:{v.line_number}')
            commands.append(f'# {v.message}')
            commands.append(f'# 建议: {v.suggestion}')
            commands.append('')
        
        return commands
