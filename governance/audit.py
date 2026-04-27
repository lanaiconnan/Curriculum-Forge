"""
Governance Audit Integration

Provides audit logging for Keeper, Mayor, and FrontDesk operations.
"""

from typing import Optional, Dict, Any
from audit.logger import AuditLogger


class GovernanceAudit:
    """治理层审计日志包装器"""
    
    def __init__(self, audit_logger: Optional[AuditLogger] = None):
        self._audit = audit_logger or AuditLogger()
    
    # ════════════════════════════════════════════════════════════════════════
    # Keeper Events
    # ════════════════════════════════════════════════════════════════════════
    
    def log_agent_registered(self, agent_id: str, role: str, capabilities: list):
        """Agent 注册"""
        self._audit.log(
            category="governance",
            event="agent_registered",
            actor="keeper",
            target=agent_id,
            metadata={"role": role, "capabilities": list(capabilities)},
        )
    
    def log_agent_deregistered(self, agent_id: str, role: str):
        """Agent 注销"""
        self._audit.log(
            category="governance",
            event="agent_deregistered",
            actor="keeper",
            target=agent_id,
            metadata={"role": role},
        )
    
    def log_task_assigned(self, task_id: str, agent_id: str, policy: str):
        """任务分配"""
        self._audit.log(
            category="governance",
            event="task_assigned",
            actor="keeper",
            target=task_id,
            metadata={"agent_id": agent_id, "policy": policy},
        )
    
    def log_task_rejected(self, task_id: str, reason: str):
        """任务拒绝"""
        self._audit.log(
            category="governance",
            event="task_rejected",
            actor="keeper",
            target=task_id,
            metadata={"reason": reason},
        )
    
    def log_health_check(self, healthy: int, unhealthy: int):
        """健康检查"""
        self._audit.log(
            category="governance",
            event="health_check",
            actor="keeper",
            target="all_agents",
            metadata={"healthy": healthy, "unhealthy": unhealthy},
        )
    
    # ════════════════════════════════════════════════════════════════════════
    # Mayor Events
    # ════════════════════════════════════════════════════════════════════════
    
    def log_rule_violation(self, agent_id: str, rule_id: str, severity: str, reputation_impact: int):
        """规则违规"""
        self._audit.log(
            category="governance",
            event="rule_violation",
            actor="mayor",
            target=agent_id,
            metadata={"rule_id": rule_id, "severity": severity, "reputation_impact": reputation_impact},
        )
    
    def log_reputation_change(self, agent_id: str, old_score: int, new_score: int, reason: str):
        """声誉变化"""
        self._audit.log(
            category="governance",
            event="reputation_change",
            actor="mayor",
            target=agent_id,
            metadata={"old_score": old_score, "new_score": new_score, "reason": reason},
        )
    
    def log_proposal_created(self, proposal_id: str, proposer: str, title: str):
        """提案创建"""
        self._audit.log(
            category="governance",
            event="proposal_created",
            actor=proposer,
            target=proposal_id,
            metadata={"title": title},
        )
    
    def log_vote_cast(self, proposal_id: str, voter_id: str, vote: str):
        """投票"""
        self._audit.log(
            category="governance",
            event="vote_cast",
            actor=voter_id,
            target=proposal_id,
            metadata={"vote": vote},
        )
    
    def log_proposal_resolved(self, proposal_id: str, result: str, votes_for: int, votes_against: int):
        """提案解决"""
        self._audit.log(
            category="governance",
            event="proposal_resolved",
            actor="mayor",
            target=proposal_id,
            metadata={"result": result, "votes_for": votes_for, "votes_against": votes_against},
        )
    
    # ════════════════════════════════════════════════════════════════════════
    # FrontDesk Events
    # ════════════════════════════════════════════════════════════════════════
    
    def log_request_received(self, request_id: str, user_id: str, priority: str):
        """请求接收"""
        self._audit.log(
            category="governance",
            event="request_received",
            actor=user_id,
            target=request_id,
            metadata={"priority": priority},
        )
    
    def log_request_dispatched(self, request_id: str, agent_id: str):
        """请求分发"""
        self._audit.log(
            category="governance",
            event="request_dispatched",
            actor="frontdesk",
            target=request_id,
            metadata={"agent_id": agent_id},
        )
    
    def log_request_completed(self, request_id: str, user_id: str, status: str, duration_seconds: float):
        """请求完成"""
        self._audit.log(
            category="governance",
            event="request_completed",
            actor=user_id,
            target=request_id,
            metadata={"status": status, "duration_seconds": duration_seconds},
        )
    
    def log_session_created(self, session_id: str, user_id: str):
        """会话创建"""
        self._audit.log(
            category="governance",
            event="session_created",
            actor=user_id,
            target=session_id,
        )
    
    def log_session_ended(self, session_id: str, user_id: str, request_count: int):
        """会话结束"""
        self._audit.log(
            category="governance",
            event="session_ended",
            actor=user_id,
            target=session_id,
            metadata={"request_count": request_count},
        )
