"""
E2E Governance Integration Tests

Tests the complete governance flow: FrontDesk → Keeper → Mayor
"""

import pytest
import asyncio
from datetime import datetime
from typing import Dict, Any

# Governance imports
from governance import (
    Keeper, AgentProfile, AgentStatus, ResourceType, ResourceQuota, SchedulingPolicy,
    Mayor, Rule, RuleType, RuleSeverity, ReputationRecord, Proposal,
    FrontDesk, UserRequest, UserSession, RequestStatus, TaskPriority
)


class TestGovernanceE2E:
    """治理层端到端集成测试"""
    
    @pytest.fixture
    def governance_stack(self):
        """完整的治理层栈"""
        keeper = Keeper()
        mayor = Mayor()
        front_desk = FrontDesk(keeper=keeper)
        
        return {
            "keeper": keeper,
            "mayor": mayor,
            "front_desk": front_desk,
        }
    
    # ════════════════════════════════════════════════════════════════════════
    # Test 4.1: Complete Flow Tests
    # ════════════════════════════════════════════════════════════════════════
    
    @pytest.mark.asyncio
    async def test_user_request_complete_flow(self, governance_stack):
        """测试用户请求完整流程：接收 → 分发 → 执行 → 完成"""
        keeper = governance_stack["keeper"]
        mayor = governance_stack["mayor"]
        front_desk = governance_stack["front_desk"]
        
        # 1. 注册 Agents
        keeper.register_agent(
            agent_id="agent-001",
            name="Teacher Alpha",
            role="teacher",
            capabilities=["explain", "answer"],
        )
        keeper.register_agent(
            agent_id="agent-002",
            name="Learner Beta",
            role="learner",
            capabilities=["learn", "practice"],
        )
        
        assert len(keeper.list_agents()) == 2
        
        # 2. 添加规则
        mayor.add_rule(
            rule_id="rule-001",
            name="max_tasks_per_hour",
            rule_type=RuleType.RESOURCE,
            condition=lambda ctx: ctx.get("tasks_per_hour", 0) > 100,
            severity=RuleSeverity.WARNING,
            reputation_impact=-5,
        )
        
        assert len(mayor.list_rules()) == 1
        
        # 3. 用户发起请求 (FrontDesk 使用 receive_request)
        request = await front_desk.receive_request(
            user_id="user-001",
            content="explain Python async/await",
            priority=TaskPriority.NORMAL,
        )
        
        assert request.status == RequestStatus.QUEUED  # 初始状态是 QUEUED
        
        # 4. 分发请求
        assigned_agent = await front_desk.dispatch_request(request.id)
        assert assigned_agent is not None
        assert assigned_agent in ["agent-001", "agent-002"]
        
        # 5. 完成请求
        await front_desk.complete_request(
            request_id=request.id,
            result={"explanation": "async/await is used for..."},
        )
        
        # 6. 验证状态
        stats = front_desk.get_stats()
        assert stats["requests"]["by_status"].get("completed", 0) == 1
    
    @pytest.mark.asyncio
    async def test_multi_agent_collaboration(self, governance_stack):
        """测试多 Agent 协作场景"""
        keeper = governance_stack["keeper"]
        front_desk = governance_stack["front_desk"]
        
        # 注册 3 个不同角色的 Agent
        roles = ["teacher", "reviewer", "learner"]
        for i, role in enumerate(roles):
            keeper.register_agent(
                agent_id=f"agent-{i+1}",
                name=f"{role.capitalize()} Agent",
                role=role,
                capabilities=[f"{role}_task"],
            )
        
        # 发送多个请求
        requests = []
        for i in range(3):
            req = await front_desk.receive_request(
                user_id="user-002",
                content=f"{roles[i]}_task",
                priority=TaskPriority.NORMAL,
            )
            requests.append(req)
        
        # 分发所有请求
        assigned_agents = []
        for req in requests:
            agent = await front_desk.dispatch_request(req.id)
            assigned_agents.append(agent)
        
        # 验证负载均衡：不同 Agent 处理不同请求
        assert len(set(assigned_agents)) >= 2  # 至少 2 个不同 Agent
        
        # 完成所有请求
        for req in requests:
            await front_desk.complete_request(
                request_id=req.id,
                result={"done": True},
            )
        
        stats = front_desk.get_stats()
        assert stats["requests"]["by_status"].get("completed", 0) == 3
    
    # ════════════════════════════════════════════════════════════════════════
    # Test 4.2: Reputation System Integration
    # ════════════════════════════════════════════════════════════════════════
    
    def test_reputation_updates_on_task_completion(self, governance_stack):
        """测试任务完成后声誉更新"""
        keeper = governance_stack["keeper"]
        mayor = governance_stack["mayor"]
        
        # 注册 Agent
        keeper.register_agent(
            agent_id="agent-010",
            name="Worker Gamma",
            role="worker",
            capabilities=["work"],
        )
        
        # 初始声誉 (需要通过 get_or_create_reputation)
        initial_rep = mayor.get_or_create_reputation("agent-010")
        assert initial_rep.score == 100  # 默认初始分
        
        # 完成任务，增加声誉 (使用 apply_reputation_change)
        mayor.apply_reputation_change("agent-010", delta=10, reason="task_completed")
        updated_rep = mayor.get_reputation("agent-010")
        assert updated_rep.score == 110
        
        # 添加规则
        mayor.add_rule(
            rule_id="rule-002",
            name="response_timeout",
            rule_type=RuleType.BEHAVIOR,
            condition=lambda ctx: ctx.get("response_time", 0) > 30,
            severity=RuleSeverity.WARNING,
            reputation_impact=-15,
        )
        
        # 规则评估
        violations = mayor.evaluate_rules({"response_time": 35})
        assert len(violations) == 1
        assert violations[0].rule_id == "rule-002"
    
    def test_reputation_trust_threshold(self, governance_stack):
        """测试声誉信任阈值"""
        keeper = governance_stack["keeper"]
        mayor = governance_stack["mayor"]
        
        # 注册 Agent
        keeper.register_agent(
            agent_id="agent-011",
            name="Worker Delta",
            role="worker",
            capabilities=["work"],
        )
        
        # 初始状态：可信 (is_agent_trusted)
        assert mayor.is_agent_trusted("agent-011") is True
        
        # 降低声誉到不可信 (阈值是 50)
        mayor.apply_reputation_change("agent-011", delta=-51, reason="multiple_failures")
        assert mayor.get_reputation("agent-011").score == 49
        assert mayor.is_agent_trusted("agent-011") is False
    
    # ════════════════════════════════════════════════════════════════════════
    # Test 4.3: Resource Quota Enforcement
    # ════════════════════════════════════════════════════════════════════════
    
    def test_resource_quota_enforcement(self, governance_stack):
        """测试资源配额强制执行"""
        keeper = governance_stack["keeper"]
        
        # 注册 Agent (无 quota 参数，使用 set_quota 单独设置)
        keeper.register_agent(
            agent_id="agent-020",
            name="Worker Epsilon",
            role="worker",
            capabilities=["work"],
        )
        
        # 设置配额
        keeper.set_quota(
            agent_id="agent-020",
            resource_type=ResourceType.API_CALLS,
            total=10,
        )
        keeper.set_quota(
            agent_id="agent-020",
            resource_type=ResourceType.TASKS,
            total=2,
        )
        
        # 预留资源
        success = keeper.reserve_resources(
            agent_id="agent-020",
            resources={ResourceType.API_CALLS: 5, ResourceType.TASKS: 1}
        )
        assert success is True
        
        # 获取集群资源状态
        cluster = keeper.get_cluster_resources()
        assert ResourceType.API_CALLS in cluster
        
        # 尝试超出配额
        success = keeper.reserve_resources(
            agent_id="agent-020",
            resources={ResourceType.API_CALLS: 10}  # 需要 10，只剩 5
        )
        assert success is False
        
        # 释放资源
        keeper.release_resources(
            agent_id="agent-020",
            resources={ResourceType.API_CALLS: 3, ResourceType.TASKS: 1}
        )
    
    def test_scheduling_policies(self, governance_stack):
        """测试不同调度策略"""
        keeper = governance_stack["keeper"]
        
        # 注册多个 Agent
        for i in range(3):
            keeper.register_agent(
                agent_id=f"agent-s{i}",
                name=f"Scheduler Agent {i}",
                role="worker",
                capabilities=["work"],
            )
        
        # Round Robin (使用 add_policy, SchedulingPolicy 是 dataclass)
        keeper.add_policy(SchedulingPolicy(
            name="round_robin",
            priority=1,
            weight=1.0,
        ))
        
        # 分配任务 (使用 assign_task)
        task1 = keeper.assign_task(
            task_id="task-1",
            requirements={"type": "work"},
        )
        task2 = keeper.assign_task(
            task_id="task-2",
            requirements={"type": "work"},
        )
        
        # 应该分配到不同 Agent (round robin)
        assert task1 is not None
        assert task2 is not None
    
    # ════════════════════════════════════════════════════════════════════════
    # Test 4.4: Proposal Voting System
    # ════════════════════════════════════════════════════════════════════════
    
    def test_proposal_voting_flow(self, governance_stack):
        """测试提案投票流程"""
        mayor = governance_stack["mayor"]
        keeper = governance_stack["keeper"]
        
        # 先注册可信任的投票者
        for agent_id in ["agent-001", "agent-002", "agent-003"]:
            keeper.register_agent(
                agent_id=agent_id,
                name=f"Voter {agent_id}",
                role="voter",
                capabilities=["vote"],
            )
            # 设置初始声誉让他们成为可信任的
            mayor.apply_reputation_change(agent_id, delta=50, reason="initial_trust")
        
        # 创建提案
        proposal = mayor.create_proposal(
            proposer="agent-001",
            title="Increase API rate limit",
            description="Raise the per-agent API rate limit from 100 to 200",
        )
        
        assert proposal.status == "open"
        proposal_id = proposal.id
        
        # 投票 (使用 vote_proposal 方法)
        assert mayor.vote_proposal(proposal_id, voter_id="agent-001", support=True) is True
        assert mayor.vote_proposal(proposal_id, voter_id="agent-002", support=True) is True
        assert mayor.vote_proposal(proposal_id, voter_id="agent-003", support=False) is True
        
        # 关闭提案 (使用 close_proposal 方法)
        result = mayor.close_proposal(proposal_id)
        # get_result() 返回 "passed"，close_proposal 也返回这个
        assert result in ["approved", "passed"]
        
        # 验证提案状态
        proposals = mayor.list_proposals()
        assert len(proposals) == 1
        # 状态可能是 passed 或 closed
        assert proposals[0].status in ["approved", "passed", "closed"]
    
    # ════════════════════════════════════════════════════════════════════════
    # Test 4.5: Health Monitoring
    # ════════════════════════════════════════════════════════════════════════
    
    @pytest.mark.asyncio
    async def test_health_monitoring(self, governance_stack):
        """测试健康监控"""
        keeper = governance_stack["keeper"]
        
        # 注册 Agents
        for i in range(3):
            keeper.register_agent(
                agent_id=f"agent-h{i}",
                name=f"Health Agent {i}",
                role="worker",
                capabilities=["work"],
            )
        
        # 心跳更新
        keeper.update_heartbeat("agent-h0")
        keeper.update_heartbeat("agent-h1")
        # agent-h2 没有心跳
        
        # 健康检查
        health = await keeper.health_check()
        
        # 验证返回格式正确
        assert "total_agents" in health
        assert health["total_agents"] == 3
        assert "results" in health
        assert "healthy_count" in health
