"""
Tests for Mayor - Rule and Reputation Manager
"""

import pytest
from datetime import datetime

from governance.mayor import (
    Mayor,
    Rule,
    RuleType,
    RuleSeverity,
    ReputationRecord,
    Proposal,
)


class TestRules:
    """Test rule management"""
    
    def test_add_rule(self):
        """Test adding a rule"""
        mayor = Mayor()
        
        rule = mayor.add_rule(
            rule_id="rule_001",
            name="Max Tasks",
            rule_type=RuleType.RESOURCE,
            condition=lambda ctx: ctx.get("task_count", 0) > 10,
            severity=RuleSeverity.WARNING,
            reputation_impact=-5,
            description="Too many concurrent tasks",
        )
        
        assert rule.id == "rule_001"
        assert rule.name == "Max Tasks"
        assert len(mayor.list_rules()) == 1
    
    def test_remove_rule(self):
        """Test removing a rule"""
        mayor = Mayor()
        
        mayor.add_rule(
            rule_id="rule_001",
            name="Test Rule",
            rule_type=RuleType.BEHAVIOR,
            condition=lambda ctx: False,
        )
        
        result = mayor.remove_rule("rule_001")
        assert result is True
        assert len(mayor.list_rules()) == 0
        
        assert mayor.remove_rule("nonexistent") is False
    
    def test_list_rules_filter(self):
        """Test listing rules with filter"""
        mayor = Mayor()
        
        mayor.add_rule("r1", "Behavior", RuleType.BEHAVIOR, lambda c: False)
        mayor.add_rule("r2", "Resource", RuleType.RESOURCE, lambda c: False)
        mayor.add_rule("r3", "Quality", RuleType.QUALITY, lambda c: False)
        
        behavior_rules = mayor.list_rules(rule_type=RuleType.BEHAVIOR)
        assert len(behavior_rules) == 1
    
    def test_evaluate_rules_no_violation(self):
        """Test rule evaluation without violation"""
        mayor = Mayor()
        
        mayor.add_rule(
            rule_id="rule_001",
            name="Task Limit",
            rule_type=RuleType.RESOURCE,
            condition=lambda ctx: ctx.get("task_count", 0) > 5,
        )
        
        violations = mayor.evaluate_rules({"task_count": 3})
        assert len(violations) == 0
    
    def test_evaluate_rules_with_violation(self):
        """Test rule evaluation with violation"""
        mayor = Mayor()
        
        mayor.add_rule(
            rule_id="rule_001",
            name="Task Limit",
            rule_type=RuleType.RESOURCE,
            condition=lambda ctx: ctx.get("task_count", 0) > 5,
            severity=RuleSeverity.ERROR,
            reputation_impact=-10,
        )
        
        violations = mayor.evaluate_rules({"task_count": 10, "agent_id": "agent_001"})
        
        assert len(violations) == 1
        assert violations[0].rule_id == "rule_001"
        assert violations[0].severity == RuleSeverity.ERROR
        
        # Check reputation impact applied
        rep = mayor.get_reputation("agent_001")
        assert rep.score == 90  # 100 - 10
    
    def test_disabled_rule_not_evaluated(self):
        """Test disabled rules are not evaluated"""
        mayor = Mayor()
        
        rule = mayor.add_rule(
            rule_id="rule_001",
            name="Test",
            rule_type=RuleType.BEHAVIOR,
            condition=lambda ctx: True,  # Always triggers
        )
        rule.enabled = False
        
        violations = mayor.evaluate_rules({"test": "data"})
        assert len(violations) == 0


class TestReputation:
    """Test reputation management"""
    
    def test_get_or_create_reputation(self):
        """Test getting or creating reputation"""
        mayor = Mayor()
        
        rep = mayor.get_or_create_reputation("agent_001")
        
        assert rep.agent_id == "agent_001"
        assert rep.score == 100
        assert rep.is_trusted is True
    
    def test_reward_agent(self):
        """Test rewarding an agent"""
        mayor = Mayor()
        
        rep = mayor.reward_agent("agent_001", 10, "Good performance")
        
        assert rep.score == 110
        assert rep.total_rewards == 10
        assert len(rep.history) == 1
    
    def test_penalize_agent(self):
        """Test penalizing an agent"""
        mayor = Mayor()
        
        rep = mayor.penalize_agent("agent_001", 20, "Bad behavior")
        
        assert rep.score == 80
        assert rep.total_penalties == 20
    
    def test_reputation_bounds(self):
        """Test reputation bounds (0-200)"""
        mayor = Mayor()
        
        # Upper bound
        rep = mayor.reward_agent("agent_001", 200, "Max reward")
        assert rep.score == 200  # Capped at 200
        
        # Lower bound
        rep = mayor.penalize_agent("agent_002", 150, "Max penalty")
        assert rep.score == 0  # Capped at 0
    
    def test_trusted_status(self):
        """Test trusted status based on reputation"""
        mayor = Mayor()
        
        rep = mayor.get_or_create_reputation("agent_001")
        assert rep.is_trusted is True  # 100 >= 50
        
        mayor.penalize_agent("agent_001", 60, "Major penalty")
        rep = mayor.get_reputation("agent_001")
        assert rep.is_trusted is False  # 40 < 50
    
    def test_ban_status(self):
        """Test ban status when reputation too low"""
        mayor = Mayor()
        
        rep = mayor.penalize_agent("agent_001", 95, "Severe violation")
        
        assert rep.score < 10
        assert rep.is_banned is True
    
    def test_is_agent_trusted(self):
        """Test trusted check"""
        mayor = Mayor()
        
        assert mayor.is_agent_trusted("agent_001") is True  # New agent
        
        mayor.penalize_agent("agent_001", 60, "Penalty")
        assert mayor.is_agent_trusted("agent_001") is False
    
    def test_get_top_agents(self):
        """Test getting top agents by reputation"""
        mayor = Mayor()
        
        mayor.reward_agent("agent_001", 50, "Top performer")
        mayor.reward_agent("agent_002", 30, "Good performer")
        mayor.penalize_agent("agent_003", 20, "Underperformer")
        
        top = mayor.get_top_agents(limit=2)
        
        assert len(top) == 2
        assert top[0].agent_id == "agent_001"  # 150
        assert top[1].agent_id == "agent_002"  # 130


class TestProposals:
    """Test proposal/voting system"""
    
    def test_create_proposal(self):
        """Test creating a proposal"""
        mayor = Mayor()
        
        proposal = mayor.create_proposal(
            title="Add new agent type",
            description="Proposal to add analyst agent",
            proposer="agent_001",
        )
        
        assert proposal.id == "proposal_0001"
        assert proposal.title == "Add new agent type"
        assert proposal.status == "open"
    
    def test_vote_proposal(self):
        """Test voting on a proposal"""
        mayor = Mayor()
        
        proposal = mayor.create_proposal(
            title="Test",
            description="Test proposal",
            proposer="agent_001",
        )
        
        result = mayor.vote_proposal("proposal_0001", "agent_002", support=True)
        assert result is True
        
        assert proposal.votes_for == 1
        assert "agent_002" in proposal.voters
    
    def test_vote_twice_fails(self):
        """Test that voting twice fails"""
        mayor = Mayor()
        
        mayor.create_proposal("Test", "Test", "agent_001")
        
        mayor.vote_proposal("proposal_0001", "agent_002", True)
        result = mayor.vote_proposal("proposal_0001", "agent_002", False)
        
        assert result is False
    
    def test_untrusted_voter_rejected(self):
        """Test that untrusted agents cannot vote"""
        mayor = Mayor()
        
        mayor.create_proposal("Test", "Test", "agent_001")
        mayor.penalize_agent("agent_002", 60, "Low reputation")
        
        result = mayor.vote_proposal("proposal_0001", "agent_002", True)
        assert result is False
    
    def test_close_proposal_passed(self):
        """Test closing a passed proposal"""
        mayor = Mayor()
        
        proposal = mayor.create_proposal("Test", "Test", "agent_001")
        mayor.vote_proposal("proposal_0001", "agent_002", True)
        mayor.vote_proposal("proposal_0001", "agent_003", True)
        
        result = mayor.close_proposal("proposal_0001")
        
        assert result == "passed"
        assert proposal.status == "passed"
    
    def test_close_proposal_rejected(self):
        """Test closing a rejected proposal"""
        mayor = Mayor()
        
        proposal = mayor.create_proposal("Test", "Test", "agent_001")
        mayor.vote_proposal("proposal_0001", "agent_002", False)
        mayor.vote_proposal("proposal_0001", "agent_003", False)
        
        result = mayor.close_proposal("proposal_0001")
        
        assert result == "rejected"
    
    def test_list_proposals_filter(self):
        """Test listing proposals with filter"""
        mayor = Mayor()
        
        mayor.create_proposal("P1", "P1", "agent_001")
        mayor.create_proposal("P2", "P2", "agent_001")
        
        mayor.vote_proposal("proposal_0001", "agent_002", True)
        mayor.close_proposal("proposal_0001")
        
        open_proposals = mayor.list_proposals(status="open")
        assert len(open_proposals) == 1
        assert open_proposals[0].id == "proposal_0002"


class TestViolations:
    """Test violation tracking"""
    
    def test_get_violations(self):
        """Test getting violations"""
        mayor = Mayor()
        
        mayor.add_rule(
            "r1", "Rule 1", RuleType.BEHAVIOR,
            lambda ctx: True,
            severity=RuleSeverity.WARNING,
        )
        mayor.add_rule(
            "r2", "Rule 2", RuleType.RESOURCE,
            lambda ctx: True,
            severity=RuleSeverity.ERROR,
        )
        
        mayor.evaluate_rules({"agent_id": "agent_001"})
        mayor.evaluate_rules({"agent_id": "agent_002"})
        
        violations = mayor.get_violations()
        assert len(violations) == 4  # 2 rules x 2 evaluations
    
    def test_get_violations_by_agent(self):
        """Test filtering violations by agent"""
        mayor = Mayor()
        
        mayor.add_rule("r1", "Rule", RuleType.BEHAVIOR, lambda c: True)
        
        mayor.evaluate_rules({"agent_id": "agent_001"})
        mayor.evaluate_rules({"agent_id": "agent_002"})
        
        violations = mayor.get_violations(agent_id="agent_001")
        assert len(violations) == 1
    
    def test_get_violations_by_severity(self):
        """Test filtering violations by severity"""
        mayor = Mayor()
        
        mayor.add_rule("r1", "Warning", RuleType.BEHAVIOR, lambda c: True, severity=RuleSeverity.WARNING)
        mayor.add_rule("r2", "Error", RuleType.BEHAVIOR, lambda c: True, severity=RuleSeverity.ERROR)
        
        mayor.evaluate_rules({"test": "data"})
        
        errors = mayor.get_violations(severity=RuleSeverity.ERROR)
        assert len(errors) == 1


class TestStatistics:
    """Test statistics"""
    
    def test_get_stats(self):
        """Test getting statistics"""
        mayor = Mayor()
        
        mayor.add_rule("r1", "Rule", RuleType.BEHAVIOR, lambda c: False)
        mayor.reward_agent("agent_001", 10, "Good")
        mayor.penalize_agent("agent_002", 5, "Bad")
        mayor.create_proposal("Test", "Test", "agent_001")
        
        stats = mayor.get_stats()
        
        assert stats["rules"]["total"] == 1
        assert stats["reputation"]["total_agents"] == 2
        assert stats["proposals"]["total"] == 1


class TestCallbacks:
    """Test callbacks"""
    
    def test_on_violation(self):
        """Test violation callback"""
        mayor = Mayor()
        
        violations = []
        mayor.on_violation(lambda v: violations.append(v.rule_id))
        
        mayor.add_rule("r1", "Rule", RuleType.BEHAVIOR, lambda c: True)
        mayor.evaluate_rules({"test": "data"})
        
        assert "r1" in violations
    
    def test_on_reputation_change(self):
        """Test reputation change callback"""
        mayor = Mayor()
        
        changes = []
        mayor.on_reputation_change(lambda r, d, reason: changes.append((r.agent_id, d)))
        
        mayor.reward_agent("agent_001", 10, "Good")
        
        assert ("agent_001", 10) in changes
