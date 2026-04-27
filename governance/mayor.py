"""
Mayor - 规则与声誉管理器

负责：
- 规则引擎（定义和执行规则）
- 声誉系统（Agent 信用评分）
- 行为审计（记录违规和奖励）
- 社区治理（投票、提案）
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Callable, Any
from enum import Enum
from datetime import datetime
import logging
import json

from governance.metrics import (
    track_rule_evaluation,
    track_rule_violation,
    track_reputation_change,
    MAYOR_AGENTS_TRUSTED,
    MAYOR_AGENTS_BANNED,
    MAYOR_PROPOSALS_TOTAL,
    MAYOR_PROPOSALS_RESOLVED,
    MAYOR_VOTES_CAST,
)

logger = logging.getLogger(__name__)


class RuleType(Enum):
    """规则类型"""
    BEHAVIOR = "behavior"      # 行为规则
    RESOURCE = "resource"      # 资源规则
    QUALITY = "quality"        # 质量规则
    SCHEDULE = "schedule"      # 调度规则
    CUSTOM = "custom"          # 自定义规则


class RuleSeverity(Enum):
    """规则严重程度"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ReputationAction(Enum):
    """声誉动作"""
    REWARD = "reward"
    PENALTY = "penalty"
    NEUTRAL = "neutral"


@dataclass
class Rule:
    """规则定义"""
    id: str
    name: str
    rule_type: RuleType
    severity: RuleSeverity = RuleSeverity.WARNING
    description: str = ""
    
    # 条件和动作
    condition: Optional[Callable[[Dict[str, Any]], bool]] = None
    action: Optional[Callable[[Dict[str, Any]], Any]] = None
    
    # 声誉影响
    reputation_impact: int = 0  # 正数=奖励，负数=惩罚
    
    # 元数据
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def evaluate(self, context: Dict[str, Any]) -> Optional["RuleViolation"]:
        """评估规则"""
        if not self.enabled:
            return None
        
        if self.condition and self.condition(context):
            return RuleViolation(
                rule_id=self.id,
                rule_name=self.name,
                severity=self.severity,
                context=context,
                reputation_impact=self.reputation_impact,
                timestamp=datetime.now(),
            )
        return None


@dataclass
class RuleViolation:
    """规则违规记录"""
    rule_id: str
    rule_name: str
    severity: RuleSeverity
    context: Dict[str, Any]
    reputation_impact: int
    timestamp: datetime
    resolved: bool = False
    resolution: Optional[str] = None


@dataclass
class ReputationRecord:
    """声誉记录"""
    agent_id: str
    score: int = 100  # 初始声誉 100
    history: List[Dict[str, Any]] = field(default_factory=list)
    
    # 统计
    total_rewards: int = 0
    total_penalties: int = 0
    
    # 状态
    is_trusted: bool = True
    is_banned: bool = False
    ban_reason: Optional[str] = None
    
    def apply_change(self, delta: int, reason: str, rule_id: Optional[str] = None):
        """应用声誉变化"""
        self.score = max(0, min(200, self.score + delta))  # 限制在 0-200
        
        record = {
            "delta": delta,
            "reason": reason,
            "rule_id": rule_id,
            "timestamp": datetime.now().isoformat(),
            "new_score": self.score,
        }
        self.history.append(record)
        
        if delta > 0:
            self.total_rewards += delta
        else:
            self.total_penalties += abs(delta)
        
        # 更新状态
        self.is_trusted = self.score >= 50
        if self.score < 10:
            self.is_banned = True
            self.ban_reason = f"Reputation too low: {self.score}"
        
        logger.info(f"Reputation change for {self.agent_id}: {delta:+d} ({reason}), new score: {self.score}")
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "agent_id": self.agent_id,
            "score": self.score,
            "is_trusted": self.is_trusted,
            "is_banned": self.is_banned,
            "total_rewards": self.total_rewards,
            "total_penalties": self.total_penalties,
            "history_count": len(self.history),
        }


@dataclass
class Proposal:
    """治理提案"""
    id: str
    title: str
    description: str
    proposer: str
    created_at: datetime = field(default_factory=datetime.now)
    
    # 投票
    votes_for: int = 0
    votes_against: int = 0
    voters: Set[str] = field(default_factory=set)
    
    # 状态
    status: str = "open"  # open, passed, rejected, executed
    executed_at: Optional[datetime] = None
    
    def vote(self, voter_id: str, support: bool) -> bool:
        """投票"""
        if voter_id in self.voters:
            return False
        
        self.voters.add(voter_id)
        if support:
            self.votes_for += 1
        else:
            self.votes_against += 1
        
        return True
    
    def get_result(self) -> str:
        """获取投票结果"""
        if self.votes_for > self.votes_against:
            return "passed"
        elif self.votes_against > self.votes_for:
            return "rejected"
        return "tie"


class Mayor:
    """
    规则与声誉管理器
    
    负责 Agent 行为治理和声誉系统
    """
    
    # 声誉阈值
    TRUSTED_THRESHOLD = 50
    WARNING_THRESHOLD = 30
    BAN_THRESHOLD = 10
    
    def __init__(self):
        # 规则
        self._rules: Dict[str, Rule] = {}
        self._violations: List[RuleViolation] = []
        
        # 声誉
        self._reputations: Dict[str, ReputationRecord] = {}
        
        # 提案
        self._proposals: Dict[str, Proposal] = {}
        self._proposal_counter = 0
        
        # 回调
        self._on_violation: Optional[Callable] = None
        self._on_reputation_change: Optional[Callable] = None
    
    # ════════════════════════════════════════════════════════════════════════
    # 规则管理
    # ════════════════════════════════════════════════════════════════════════
    
    def add_rule(
        self,
        rule_id: str,
        name: str,
        rule_type: RuleType,
        condition: Callable[[Dict[str, Any]], bool],
        action: Optional[Callable[[Dict[str, Any]], Any]] = None,
        severity: RuleSeverity = RuleSeverity.WARNING,
        reputation_impact: int = 0,
        description: str = "",
    ) -> Rule:
        """添加规则"""
        rule = Rule(
            id=rule_id,
            name=name,
            rule_type=rule_type,
            condition=condition,
            action=action,
            severity=severity,
            reputation_impact=reputation_impact,
            description=description,
        )
        
        self._rules[rule_id] = rule
        logger.info(f"Added rule: {rule_id} ({rule_type.value})")
        return rule
    
    def remove_rule(self, rule_id: str) -> bool:
        """移除规则"""
        if rule_id in self._rules:
            del self._rules[rule_id]
            return True
        return False
    
    def get_rule(self, rule_id: str) -> Optional[Rule]:
        """获取规则"""
        return self._rules.get(rule_id)
    
    def list_rules(
        self,
        rule_type: Optional[RuleType] = None,
        enabled_only: bool = True,
    ) -> List[Rule]:
        """列出规则"""
        rules = list(self._rules.values())
        
        if rule_type:
            rules = [r for r in rules if r.rule_type == rule_type]
        if enabled_only:
            rules = [r for r in rules if r.enabled]
        
        return rules
    
    def evaluate_rules(self, context: Dict[str, Any]) -> List[RuleViolation]:
        """评估所有规则"""
        violations = []
        
        for rule in self._rules.values():
            violation = rule.evaluate(context)
            passed = violation is None
            track_rule_evaluation(rule.rule_type.value, passed)
            
            if violation:
                violations.append(violation)
                self._violations.append(violation)
                track_rule_violation(rule.id, violation.severity.value)
                
                # 应用声誉影响
                if "agent_id" in context and violation.reputation_impact != 0:
                    self.apply_reputation_change(
                        context["agent_id"],
                        violation.reputation_impact,
                        f"Rule violation: {rule.name}",
                        rule.id,
                    )
                
                # 回调
                if self._on_violation:
                    self._on_violation(violation)
        
        return violations
    
    # ════════════════════════════════════════════════════════════════════════
    # 声誉管理
    # ════════════════════════════════════════════════════════════════════════
    
    def get_or_create_reputation(self, agent_id: str) -> ReputationRecord:
        """获取或创建声誉记录"""
        if agent_id not in self._reputations:
            self._reputations[agent_id] = ReputationRecord(agent_id=agent_id)
        return self._reputations[agent_id]
    
    def get_reputation(self, agent_id: str) -> Optional[ReputationRecord]:
        """获取声誉记录"""
        return self._reputations.get(agent_id)
    
    def apply_reputation_change(
        self,
        agent_id: str,
        delta: int,
        reason: str,
        rule_id: Optional[str] = None,
    ) -> ReputationRecord:
        """应用声誉变化"""
        record = self.get_or_create_reputation(agent_id)
        old_score = record.score
        record.apply_change(delta, reason, rule_id)
        
        # Metrics
        track_reputation_change(agent_id, old_score, record.score)
        
        # 更新可信/封禁计数
        if old_score < self.TRUSTED_THRESHOLD and record.score >= self.TRUSTED_THRESHOLD:
            MAYOR_AGENTS_TRUSTED.inc()
        elif old_score >= self.TRUSTED_THRESHOLD and record.score < self.TRUSTED_THRESHOLD:
            MAYOR_AGENTS_TRUSTED.dec()
        
        if old_score >= self.BAN_THRESHOLD and record.score < self.BAN_THRESHOLD:
            MAYOR_AGENTS_BANNED.inc()
        elif old_score < self.BAN_THRESHOLD and record.score >= self.BAN_THRESHOLD:
            MAYOR_AGENTS_BANNED.dec()
        
        # 回调
        if self._on_reputation_change:
            self._on_reputation_change(record, delta, reason)
        
        return record
    
    def reward_agent(self, agent_id: str, points: int, reason: str) -> ReputationRecord:
        """奖励 Agent"""
        return self.apply_reputation_change(agent_id, points, reason)
    
    def penalize_agent(self, agent_id: str, points: int, reason: str) -> ReputationRecord:
        """惩罚 Agent"""
        return self.apply_reputation_change(agent_id, -points, reason)
    
    def is_agent_trusted(self, agent_id: str) -> bool:
        """检查 Agent 是否可信"""
        record = self.get_reputation(agent_id)
        if not record:
            return True  # 新 agent 默认可信
        return record.is_trusted and not record.is_banned
    
    def get_top_agents(self, limit: int = 10) -> List[ReputationRecord]:
        """获取声誉最高的 Agent"""
        records = sorted(
            self._reputations.values(),
            key=lambda r: r.score,
            reverse=True,
        )
        return records[:limit]
    
    # ════════════════════════════════════════════════════════════════════════
    # 提案管理
    # ════════════════════════════════════════════════════════════════════════
    
    def create_proposal(
        self,
        title: str,
        description: str,
        proposer: str,
    ) -> Proposal:
        """创建提案"""
        self._proposal_counter += 1
        proposal_id = f"proposal_{self._proposal_counter:04d}"
        
        proposal = Proposal(
            id=proposal_id,
            title=title,
            description=description,
            proposer=proposer,
        )
        
        self._proposals[proposal_id] = proposal
        logger.info(f"Created proposal: {proposal_id} by {proposer}")
        return proposal
    
    def vote_proposal(
        self,
        proposal_id: str,
        voter_id: str,
        support: bool,
    ) -> bool:
        """对提案投票"""
        proposal = self._proposals.get(proposal_id)
        if not proposal or proposal.status != "open":
            return False
        
        # 检查投票者声誉
        if not self.is_agent_trusted(voter_id):
            logger.warning(f"Untrusted agent {voter_id} tried to vote")
            return False
        
        return proposal.vote(voter_id, support)
    
    def close_proposal(self, proposal_id: str) -> Optional[str]:
        """关闭提案"""
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            return None
        
        result = proposal.get_result()
        proposal.status = result
        proposal.executed_at = datetime.now()
        
        logger.info(f"Closed proposal {proposal_id}: {result}")
        return result
    
    def list_proposals(self, status: Optional[str] = None) -> List[Proposal]:
        """列出提案"""
        proposals = list(self._proposals.values())
        
        if status:
            proposals = [p for p in proposals if p.status == status]
        
        return proposals
    
    # ════════════════════════════════════════════════════════════════════════
    # 审计与统计
    # ════════════════════════════════════════════════════════════════════════
    
    def get_violations(
        self,
        agent_id: Optional[str] = None,
        severity: Optional[RuleSeverity] = None,
        limit: int = 100,
    ) -> List[RuleViolation]:
        """获取违规记录"""
        violations = self._violations
        
        if agent_id:
            violations = [v for v in violations if v.context.get("agent_id") == agent_id]
        if severity:
            violations = [v for v in violations if v.severity == severity]
        
        return violations[-limit:]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "rules": {
                "total": len(self._rules),
                "by_type": {
                    rt.value: len([r for r in self._rules.values() if r.rule_type == rt])
                    for rt in RuleType
                },
            },
            "reputation": {
                "total_agents": len(self._reputations),
                "trusted": len([r for r in self._reputations.values() if r.is_trusted]),
                "banned": len([r for r in self._reputations.values() if r.is_banned]),
                "average_score": (
                    sum(r.score for r in self._reputations.values()) / len(self._reputations)
                    if self._reputations else 0.0
                ),
            },
            "violations": {
                "total": len(self._violations),
                "by_severity": {
                    s.value: len([v for v in self._violations if v.severity == s])
                    for s in RuleSeverity
                },
            },
            "proposals": {
                "total": len(self._proposals),
                "open": len([p for p in self._proposals.values() if p.status == "open"]),
                "passed": len([p for p in self._proposals.values() if p.status == "passed"]),
            },
        }
    
    # ════════════════════════════════════════════════════════════════════════
    # 回调设置
    # ════════════════════════════════════════════════════════════════════════
    
    def on_violation(self, callback: Callable):
        """设置违规回调"""
        self._on_violation = callback
    
    def on_reputation_change(self, callback: Callable):
        """设置声誉变化回调"""
        self._on_reputation_change = callback
