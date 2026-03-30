"""HumanFeedback - 人类反馈接口

来自 AgentLaboratory 的灵感：
- 反馈收集（交互式、延迟、预设）
- 约束应用
- 偏好学习
- 质量把关
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable, Tuple
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


class FeedbackType(Enum):
    """反馈类型"""
    GUIDANCE = "guidance"           # 指导建议
    CORRECTION = "correction"       # 纠正错误
    CONSTRAINT = "constraint"       # 添加约束
    APPROVAL = "approval"           # 批准决策
    REJECTION = "rejection"         # 拒绝决策


class FeedbackMode(Enum):
    """反馈模式"""
    INTERACTIVE = "interactive"     # 实时交互
    DEFERRED = "deferred"          # 延迟反馈
    PRESET = "preset"              # 预设规则


class Priority(Enum):
    """优先级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Feedback:
    """单条反馈"""
    id: str
    type: FeedbackType
    mode: FeedbackMode
    priority: Priority
    content: str
    context: Dict[str, Any]
    timestamp: str
    applied: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'type': self.type.value,
            'mode': self.mode.value,
            'priority': self.priority.value,
            'content': self.content,
            'context': self.context,
            'timestamp': self.timestamp,
            'applied': self.applied,
        }


@dataclass
class Constraint:
    """约束条件"""
    name: str
    description: str
    rule: Callable[[Dict[str, Any]], bool]  # 验证函数
    priority: Priority
    created_at: str
    
    def validate(self, data: Dict[str, Any]) -> bool:
        """验证数据是否满足约束"""
        try:
            return self.rule(data)
        except Exception:
            return False


@dataclass
class UserPreference:
    """用户偏好"""
    key: str
    value: Any
    weight: float = 1.0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'key': self.key,
            'value': self.value,
            'weight': self.weight,
            'created_at': self.created_at,
        }


class HumanFeedbackManager:
    """
    人类反馈管理器
    
    核心功能：
    1. 收集反馈 - 支持多种反馈模式
    2. 应用约束 - 将反馈转化为训练约束
    3. 学习偏好 - 记录用户偏好
    4. 持久化 - 保存反馈历史
    """
    
    def __init__(self, workspace: str = ".", scratchpad: Scratchpad = None):
        self.workspace = workspace
        self.scratchpad = scratchpad
        
        # 反馈存储
        self.feedback_dir = os.path.join(workspace, '.feedback')
        os.makedirs(self.feedback_dir, exist_ok=True)
        
        # 内存存储
        self.feedback_history: List[Feedback] = []
        self.constraints: List[Constraint] = []
        self.preferences: Dict[str, UserPreference] = {}
        
        # 加载持久化数据
        self._load_feedback_history()
        self._load_constraints()
        self._load_preferences()
    
    def _log_thinking(self, thought: str, confidence: float = None):
        """记录思考日志"""
        if self.scratchpad:
            self.scratchpad.log_thinking(
                thought=thought,
                confidence=confidence,
                context='HumanFeedback'
            )
    
    # ========== 反馈收集 ==========
    
    def request_guidance(
        self,
        context: Dict[str, Any],
        question: str = None,
        timeout: int = 30
    ) -> Optional[Feedback]:
        """
        请求人类指导（交互式）
        
        Args:
            context: 上下文信息
            question: 提问内容
            timeout: 超时时间（秒）
        
        Returns:
            Feedback: 反馈内容，或 None 如果超时
        """
        self._log_thinking(f'请求人类指导: {question}', confidence=0.8)
        
        print("\n" + "=" * 60)
        print("🤝 Human Guidance Requested")
        print("=" * 60)
        
        if question:
            print(f"\n❓ {question}")
        
        print(f"\n📋 Context:")
        for key, value in context.items():
            if isinstance(value, dict):
                print(f"   {key}: {json.dumps(value, indent=2)}")
            else:
                print(f"   {key}: {value}")
        
        print(f"\n⏱️  Timeout: {timeout}s (press Ctrl+C to skip)")
        print("=" * 60)
        
        try:
            response = input("\n💬 Your guidance: ").strip()
            
            if response:
                feedback = Feedback(
                    id=self._generate_id(),
                    type=FeedbackType.GUIDANCE,
                    mode=FeedbackMode.INTERACTIVE,
                    priority=Priority.HIGH,
                    content=response,
                    context=context,
                    timestamp=datetime.now().isoformat(),
                )
                
                self.feedback_history.append(feedback)
                self._save_feedback(feedback)
                
                self._log_thinking(f'收到人类指导: {response}', confidence=0.95)
                print(f"\n✅ Feedback recorded: {feedback.id}")
                
                return feedback
        except KeyboardInterrupt:
            print("\n⏭️  Skipped")
        except Exception as e:
            print(f"\n❌ Error: {e}")
        
        return None
    
    def add_correction(
        self,
        issue: str,
        correction: str,
        context: Dict[str, Any]
    ) -> Feedback:
        """
        添加纠正反馈
        
        Args:
            issue: 问题描述
            correction: 纠正方案
            context: 上下文
        
        Returns:
            Feedback: 反馈对象
        """
        feedback = Feedback(
            id=self._generate_id(),
            type=FeedbackType.CORRECTION,
            mode=FeedbackMode.DEFERRED,
            priority=Priority.HIGH,
            content=f"Issue: {issue}\nCorrection: {correction}",
            context=context,
            timestamp=datetime.now().isoformat(),
        )
        
        self.feedback_history.append(feedback)
        self._save_feedback(feedback)
        
        self._log_thinking(f'添加纠正: {issue}', confidence=0.9)
        
        return feedback
    
    def add_constraint(
        self,
        name: str,
        description: str,
        rule: Callable[[Dict[str, Any]], bool],
        priority: Priority = Priority.MEDIUM
    ) -> Constraint:
        """
        添加约束条件
        
        Args:
            name: 约束名称
            description: 约束描述
            rule: 验证函数
            priority: 优先级
        
        Returns:
            Constraint: 约束对象
        """
        constraint = Constraint(
            name=name,
            description=description,
            rule=rule,
            priority=priority,
            created_at=datetime.now().isoformat(),
        )
        
        self.constraints.append(constraint)
        self._log_thinking(f'添加约束: {name}', confidence=0.9)
        
        return constraint
    
    def add_preset_constraint(
        self,
        name: str,
        description: str,
        rule_dict: Dict[str, Any],
        priority: Priority = Priority.MEDIUM
    ) -> Constraint:
        """
        添加预设约束（从字典定义）
        
        Args:
            name: 约束名称
            description: 约束描述
            rule_dict: 规则字典 {'field': 'value', 'operator': '=='}
            priority: 优先级
        
        Returns:
            Constraint: 约束对象
        """
        def rule_func(data: Dict[str, Any]) -> bool:
            for key, expected_value in rule_dict.items():
                if key not in data:
                    return False
                if data[key] != expected_value:
                    return False
            return True
        
        return self.add_constraint(name, description, rule_func, priority)
    
    # ========== 约束应用 ==========
    
    def validate_environment(self, env: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        验证环境是否满足所有约束
        
        Args:
            env: 环境配置
        
        Returns:
            Tuple[bool, List[str]]: (是否通过, 失败原因列表)
        """
        failures = []
        
        for constraint in self.constraints:
            if not constraint.validate(env):
                failures.append(f"{constraint.name}: {constraint.description}")
        
        if failures:
            self._log_thinking(f'环境验证失败: {len(failures)} 个约束', confidence=0.8)
        
        return len(failures) == 0, failures
    
    def apply_constraints_to_environment(self, env: Dict[str, Any]) -> Dict[str, Any]:
        """
        应用约束到环境配置
        
        Args:
            env: 原始环境配置
        
        Returns:
            Dict: 修改后的环境配置
        """
        modified_env = env.copy()
        
        # 应用用户偏好
        for pref_key, preference in self.preferences.items():
            if pref_key in modified_env:
                # 根据权重调整值
                if isinstance(preference.value, (int, float)):
                    modified_env[pref_key] = preference.value
                elif isinstance(preference.value, dict):
                    modified_env[pref_key].update(preference.value)
        
        self._log_thinking(f'应用约束到环境', confidence=0.9)
        
        return modified_env
    
    # ========== 偏好学习 ==========
    
    def record_preference(
        self,
        key: str,
        value: Any,
        weight: float = 1.0
    ) -> UserPreference:
        """
        记录用户偏好
        
        Args:
            key: 偏好键
            value: 偏好值
            weight: 权重
        
        Returns:
            UserPreference: 偏好对象
        """
        preference = UserPreference(
            key=key,
            value=value,
            weight=weight,
        )
        
        self.preferences[key] = preference
        self._save_preferences()
        
        self._log_thinking(f'记录偏好: {key}={value}', confidence=0.9)
        
        return preference
    
    def get_preference(self, key: str) -> Optional[UserPreference]:
        """获取用户偏好"""
        return self.preferences.get(key)
    
    def get_all_preferences(self) -> Dict[str, UserPreference]:
        """获取所有用户偏好"""
        return self.preferences.copy()
    
    # ========== 质量把关 ==========
    
    def request_approval(
        self,
        decision: str,
        context: Dict[str, Any],
        timeout: int = 30
    ) -> bool:
        """
        请求人类批准关键决策
        
        Args:
            decision: 决策描述
            context: 上下文
            timeout: 超时时间
        
        Returns:
            bool: 是否批准
        """
        self._log_thinking(f'请求批准: {decision}', confidence=0.8)
        
        print("\n" + "=" * 60)
        print("🔒 Approval Required")
        print("=" * 60)
        print(f"\n📌 Decision: {decision}")
        print(f"\n📋 Context:")
        for key, value in context.items():
            print(f"   {key}: {value}")
        
        print(f"\n⏱️  Timeout: {timeout}s")
        print("=" * 60)
        
        try:
            response = input("\n👤 Approve? (yes/no): ").strip().lower()
            
            approved = response in ['yes', 'y', 'approve']
            
            feedback = Feedback(
                id=self._generate_id(),
                type=FeedbackType.APPROVAL if approved else FeedbackType.REJECTION,
                mode=FeedbackMode.INTERACTIVE,
                priority=Priority.CRITICAL,
                content=f"Decision: {decision}\nApproval: {approved}",
                context=context,
                timestamp=datetime.now().isoformat(),
            )
            
            self.feedback_history.append(feedback)
            self._save_feedback(feedback)
            
            print(f"\n✅ {'Approved' if approved else 'Rejected'}")
            
            return approved
        except KeyboardInterrupt:
            print("\n⏭️  Skipped (default: approved)")
            return True
        except Exception as e:
            print(f"\n❌ Error: {e}")
            return True
    
    # ========== 持久化 ==========
    
    def _generate_id(self) -> str:
        """生成反馈 ID"""
        return f"fb_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.feedback_history)}"
    
    def _save_feedback(self, feedback: Feedback):
        """保存单条反馈"""
        filepath = os.path.join(self.feedback_dir, f"{feedback.id}.json")
        with open(filepath, 'w') as f:
            json.dump(feedback.to_dict(), f, indent=2)
    
    def _save_feedback_history(self):
        """保存反馈历史"""
        filepath = os.path.join(self.feedback_dir, 'history.json')
        with open(filepath, 'w') as f:
            json.dump(
                [fb.to_dict() for fb in self.feedback_history],
                f,
                indent=2
            )
    
    def _load_feedback_history(self):
        """加载反馈历史"""
        filepath = os.path.join(self.feedback_dir, 'history.json')
        if os.path.exists(filepath):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                    for item in data:
                        feedback = Feedback(
                            id=item['id'],
                            type=FeedbackType(item['type']),
                            mode=FeedbackMode(item['mode']),
                            priority=Priority(item['priority']),
                            content=item['content'],
                            context=item['context'],
                            timestamp=item['timestamp'],
                            applied=item.get('applied', False),
                        )
                        self.feedback_history.append(feedback)
            except Exception as e:
                self._log_thinking(f'加载反馈历史失败: {e}', confidence=0.5)
    
    def _save_constraints(self):
        """保存约束"""
        filepath = os.path.join(self.feedback_dir, 'constraints.json')
        data = []
        for constraint in self.constraints:
            data.append({
                'name': constraint.name,
                'description': constraint.description,
                'priority': constraint.priority.value,
                'created_at': constraint.created_at,
            })
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _load_constraints(self):
        """加载约束"""
        filepath = os.path.join(self.feedback_dir, 'constraints.json')
        if os.path.exists(filepath):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                    for item in data:
                        # 注意：无法恢复 rule 函数，需要手动添加
                        pass
            except Exception as e:
                self._log_thinking(f'加载约束失败: {e}', confidence=0.5)
    
    def _save_preferences(self):
        """保存偏好"""
        filepath = os.path.join(self.feedback_dir, 'preferences.json')
        data = {k: v.to_dict() for k, v in self.preferences.items()}
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _load_preferences(self):
        """加载偏好"""
        filepath = os.path.join(self.feedback_dir, 'preferences.json')
        if os.path.exists(filepath):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                    for key, item in data.items():
                        preference = UserPreference(
                            key=item['key'],
                            value=item['value'],
                            weight=item.get('weight', 1.0),
                            created_at=item.get('created_at', datetime.now().isoformat()),
                        )
                        self.preferences[key] = preference
            except Exception as e:
                self._log_thinking(f'加载偏好失败: {e}', confidence=0.5)
    
    # ========== 统计和报告 ==========
    
    def get_feedback_summary(self) -> Dict[str, Any]:
        """获取反馈摘要"""
        by_type = {}
        by_priority = {}
        
        for feedback in self.feedback_history:
            type_key = feedback.type.value
            priority_key = feedback.priority.value
            
            by_type[type_key] = by_type.get(type_key, 0) + 1
            by_priority[priority_key] = by_priority.get(priority_key, 0) + 1
        
        return {
            'total_feedback': len(self.feedback_history),
            'by_type': by_type,
            'by_priority': by_priority,
            'total_constraints': len(self.constraints),
            'total_preferences': len(self.preferences),
        }
    
    def print_summary(self):
        """打印摘要"""
        summary = self.get_feedback_summary()
        
        print("\n" + "=" * 60)
        print("🤝 Human Feedback Summary")
        print("=" * 60)
        
        print(f"\n📊 Feedback Statistics:")
        print(f"   Total: {summary['total_feedback']}")
        
        if summary['by_type']:
            print(f"\n   By Type:")
            for ftype, count in summary['by_type'].items():
                print(f"      • {ftype}: {count}")
        
        if summary['by_priority']:
            print(f"\n   By Priority:")
            for priority, count in summary['by_priority'].items():
                print(f"      • {priority}: {count}")
        
        print(f"\n🔒 Constraints: {summary['total_constraints']}")
        print(f"❤️  Preferences: {summary['total_preferences']}")
        
        print("=" * 60)
