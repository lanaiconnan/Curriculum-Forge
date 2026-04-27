"""
Tests for Governance Audit Integration
"""

import pytest
import tempfile
from pathlib import Path

from governance.audit import GovernanceAudit
from audit.logger import AuditLogger


class TestGovernanceAudit:
    """Governance audit tests"""
    
    @pytest.fixture
    def audit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(base_dir=Path(tmpdir))
            yield GovernanceAudit(logger)
    
    def test_log_agent_registered(self, audit):
        audit.log_agent_registered("agent_001", "teacher", ["teach", "evaluate"])
        
        stats = audit._audit.stats()
        assert stats["total"] == 1
        assert stats["by_category"].get("governance") == 1
        assert stats["by_event"].get("agent_registered") == 1
    
    def test_log_agent_deregistered(self, audit):
        audit.log_agent_deregistered("agent_001", "teacher")
        
        records = audit._audit.query(category="governance", event="agent_deregistered")
        assert len(records) == 1
        assert records[0]["target"] == "agent_001"
    
    def test_log_task_assigned(self, audit):
        audit.log_task_assigned("task_123", "agent_001", "least_loaded")
        
        records = audit._audit.query(event="task_assigned")
        assert len(records) == 1
        assert records[0]["metadata"]["agent_id"] == "agent_001"
        assert records[0]["metadata"]["policy"] == "least_loaded"
    
    def test_log_task_rejected(self, audit):
        audit.log_task_rejected("task_456", "no_available_agent")
        
        records = audit._audit.query(event="task_rejected")
        assert len(records) == 1
        assert records[0]["metadata"]["reason"] == "no_available_agent"
    
    def test_log_rule_violation(self, audit):
        audit.log_rule_violation("agent_002", "rule_timeout", "warning", -5)
        
        records = audit._audit.query(event="rule_violation")
        assert len(records) == 1
        assert records[0]["target"] == "agent_002"
        assert records[0]["metadata"]["reputation_impact"] == -5
    
    def test_log_reputation_change(self, audit):
        audit.log_reputation_change("agent_002", 80, 75, "rule_violation")
        
        records = audit._audit.query(event="reputation_change")
        assert len(records) == 1
        assert records[0]["metadata"]["old_score"] == 80
        assert records[0]["metadata"]["new_score"] == 75
    
    def test_log_proposal_created(self, audit):
        audit.log_proposal_created("prop_001", "agent_003", "Add new scheduling policy")
        
        records = audit._audit.query(event="proposal_created")
        assert len(records) == 1
        assert records[0]["actor"] == "agent_003"
    
    def test_log_vote_cast(self, audit):
        audit.log_vote_cast("prop_001", "agent_004", "for")
        
        records = audit._audit.query(event="vote_cast")
        assert len(records) == 1
        assert records[0]["metadata"]["vote"] == "for"
    
    def test_log_proposal_resolved(self, audit):
        audit.log_proposal_resolved("prop_001", "passed", 5, 2)
        
        records = audit._audit.query(event="proposal_resolved")
        assert len(records) == 1
        assert records[0]["metadata"]["result"] == "passed"
        assert records[0]["metadata"]["votes_for"] == 5
    
    def test_log_request_lifecycle(self, audit):
        # Full request lifecycle
        audit.log_request_received("req_001", "user_123", "NORMAL")
        audit.log_request_dispatched("req_001", "agent_005")
        audit.log_request_completed("req_001", "user_123", "completed", 5.5)
        
        records = audit._audit.query(category="governance")
        assert len(records) == 3
        
        events = [r["event"] for r in records]
        assert "request_received" in events
        assert "request_dispatched" in events
        assert "request_completed" in events
    
    def test_log_session_lifecycle(self, audit):
        audit.log_session_created("sess_001", "user_456")
        audit.log_session_ended("sess_001", "user_456", 3)
        
        records = audit._audit.query(category="governance")
        assert len(records) == 2
        
        session_events = [r for r in records if "session" in r["event"]]
        assert len(session_events) == 2
    
    def test_query_filters(self, audit):
        # Create multiple records
        audit.log_agent_registered("agent_001", "teacher", ["teach"])
        audit.log_agent_registered("agent_002", "learner", ["learn"])
        audit.log_task_assigned("task_001", "agent_001", "round_robin")
        
        # Query by category
        records = audit._audit.query(category="governance")
        assert len(records) == 3
        
        # Query by event
        records = audit._audit.query(event="agent_registered")
        assert len(records) == 2
        
        # Query by target
        records = audit._audit.query(target="agent_001")
        assert len(records) == 1
        assert records[0]["event"] == "agent_registered"
