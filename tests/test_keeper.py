"""
Tests for Keeper - Resource Manager
"""

import pytest
import asyncio
from datetime import datetime, timedelta

from governance.keeper import (
    Keeper,
    AgentProfile,
    AgentStatus,
    ResourceType,
    ResourceQuota,
    SchedulingPolicy,
)


class TestAgentRegistration:
    """Test Agent registration"""
    
    def test_register_agent(self):
        """Test basic registration"""
        keeper = Keeper()
        
        agent = keeper.register_agent(
            agent_id="agent_001",
            name="Teacher Alpha",
            role="teacher",
            capabilities={"curriculum", "guidance"},
            max_concurrent_tasks=2,
        )
        
        assert agent.id == "agent_001"
        assert agent.name == "Teacher Alpha"
        assert agent.role == "teacher"
        assert "curriculum" in agent.capabilities
        assert agent.status == AgentStatus.IDLE
        assert len(keeper.list_agents()) == 1
    
    def test_register_duplicate(self):
        """Test registering duplicate agent"""
        keeper = Keeper()
        
        keeper.register_agent("agent_001", "Agent 1", "teacher")
        keeper.register_agent("agent_001", "Agent 1 Updated", "reviewer")
        
        agents = keeper.list_agents()
        assert len(agents) == 1
        assert agents[0].role == "reviewer"
    
    def test_unregister_agent(self):
        """Test unregistering agent"""
        keeper = Keeper()
        
        keeper.register_agent("agent_001", "Agent 1", "teacher")
        result = keeper.unregister_agent("agent_001")
        
        assert result is True
        assert len(keeper.list_agents()) == 0
    
    def test_unregister_nonexistent(self):
        """Test unregistering non-existent agent"""
        keeper = Keeper()
        result = keeper.unregister_agent("nonexistent")
        assert result is False
    
    def test_unregister_with_active_tasks(self):
        """Test cannot unregister agent with active tasks"""
        keeper = Keeper()
        
        keeper.register_agent("agent_001", "Agent 1", "teacher")
        keeper._agents["agent_001"].current_tasks = ["task_001"]
        
        result = keeper.unregister_agent("agent_001")
        assert result is False
    
    def test_get_agent(self):
        """Test getting agent by ID"""
        keeper = Keeper()
        keeper.register_agent("agent_001", "Agent 1", "teacher")
        
        agent = keeper.get_agent("agent_001")
        assert agent is not None
        assert agent.name == "Agent 1"
        
        assert keeper.get_agent("nonexistent") is None
    
    def test_list_agents_filters(self):
        """Test listing agents with filters"""
        keeper = Keeper()
        
        keeper.register_agent("agent_001", "Teacher 1", "teacher")
        keeper.register_agent("agent_002", "Learner 1", "learner")
        keeper.register_agent("agent_003", "Teacher 2", "teacher")
        
        # Filter by role
        teachers = keeper.list_agents(role="teacher")
        assert len(teachers) == 2
        
        # Filter by status
        keeper._agents["agent_001"].status = AgentStatus.BUSY
        idle = keeper.list_agents(status=AgentStatus.IDLE)
        assert len(idle) == 2
    
    def test_update_heartbeat(self):
        """Test heartbeat update"""
        keeper = Keeper()
        keeper.register_agent("agent_001", "Agent 1", "teacher")
        
        before = keeper._agents["agent_001"].last_heartbeat
        keeper.update_heartbeat("agent_001")
        after = keeper._agents["agent_001"].last_heartbeat
        
        assert after > before
        assert keeper.update_heartbeat("nonexistent") is False


class TestResourceQuotas:
    """Test resource quota management"""
    
    def test_set_quota(self):
        """Test setting resource quota"""
        keeper = Keeper()
        keeper.register_agent("agent_001", "Agent 1", "teacher")
        
        result = keeper.set_quota(
            "agent_001",
            ResourceType.TASKS,
            total=10.0,
        )
        
        assert result is True
        agent = keeper.get_agent("agent_001")
        assert ResourceType.TASKS in agent.quotas
        assert agent.quotas[ResourceType.TASKS].total == 10.0
    
    def test_reserve_resources(self):
        """Test reserving resources"""
        keeper = Keeper()
        keeper.register_agent("agent_001", "Agent 1", "teacher")
        keeper.set_quota("agent_001", ResourceType.TASKS, total=10.0)
        
        result = keeper.reserve_resources(
            "agent_001",
            {ResourceType.TASKS: 3.0},
        )
        
        assert result is True
        agent = keeper.get_agent("agent_001")
        assert agent.quotas[ResourceType.TASKS].reserved == 3.0
        assert agent.quotas[ResourceType.TASKS].available == 7.0
    
    def test_reserve_insufficient_resources(self):
        """Test reserving more than available"""
        keeper = Keeper()
        keeper.register_agent("agent_001", "Agent 1", "teacher")
        keeper.set_quota("agent_001", ResourceType.TASKS, total=10.0)
        
        result = keeper.reserve_resources(
            "agent_001",
            {ResourceType.TASKS: 15.0},
        )
        
        assert result is False
    
    def test_release_resources(self):
        """Test releasing resources"""
        keeper = Keeper()
        keeper.register_agent("agent_001", "Agent 1", "teacher")
        keeper.set_quota("agent_001", ResourceType.TASKS, total=10.0)
        
        keeper.reserve_resources("agent_001", {ResourceType.TASKS: 3.0})
        keeper._agents["agent_001"].quotas[ResourceType.TASKS].used = 3.0
        
        result = keeper.release_resources(
            "agent_001",
            {ResourceType.TASKS: 2.0},
        )
        
        assert result is True
        agent = keeper.get_agent("agent_001")
        assert agent.quotas[ResourceType.TASKS].used == 1.0
    
    def test_get_cluster_resources(self):
        """Test getting cluster-wide resources"""
        keeper = Keeper()
        
        keeper.register_agent("agent_001", "Agent 1", "teacher")
        keeper.register_agent("agent_002", "Agent 2", "learner")
        
        keeper.set_quota("agent_001", ResourceType.TASKS, total=10.0)
        keeper.set_quota("agent_002", ResourceType.TASKS, total=5.0)
        
        cluster = keeper.get_cluster_resources()
        
        assert cluster[ResourceType.TASKS]["total"] == 15.0
        assert cluster[ResourceType.TASKS]["available"] == 15.0


class TestScheduling:
    """Test task scheduling"""
    
    def test_assign_task_round_robin(self):
        """Test round-robin scheduling"""
        keeper = Keeper()
        keeper.register_agent("agent_001", "Agent 1", "teacher")
        keeper.register_agent("agent_002", "Agent 2", "teacher")
        
        # Assign to first agent
        agent_id = keeper.assign_task(task_id="task_001")
        assert agent_id == "agent_001"
        
        # Assign to second agent (round-robin)
        agent_id = keeper.assign_task(task_id="task_002")
        assert agent_id == "agent_002"
    
    def test_assign_task_least_loaded(self):
        """Test least-loaded scheduling"""
        keeper = Keeper()
        
        policy = SchedulingPolicy(name="least_loaded", strategy="least_loaded")
        keeper.add_policy(policy)
        
        keeper.register_agent("agent_001", "Agent 1", "teacher")
        keeper.register_agent("agent_002", "Agent 2", "teacher")
        
        # Make agent_001 busier
        keeper._agents["agent_001"].current_tasks = ["task_001"]
        
        # Should assign to less loaded agent
        agent_id = keeper.assign_task(task_id="task_002")
        assert agent_id == "agent_002"
    
    def test_assign_task_capability_match(self):
        """Test capability-based scheduling"""
        keeper = Keeper()
        
        policy = SchedulingPolicy(name="cap_match", strategy="capability_match")
        keeper.add_policy(policy)
        
        keeper.register_agent(
            "agent_001",
            "Agent 1",
            "teacher",
            capabilities={"curriculum", "guidance"},
        )
        keeper.register_agent(
            "agent_002",
            "Agent 2",
            "teacher",
            capabilities={"evaluation"},
        )
        
        # Assign task requiring specific capability
        agent_id = keeper.assign_task(
            task_id="task_001",
            requirements={"capabilities": ["curriculum"]},
        )
        
        assert agent_id == "agent_001"
    
    def test_assign_task_no_available(self):
        """Test assigning when no agents available"""
        keeper = Keeper()
        keeper.register_agent("agent_001", "Agent 1", "teacher")
        
        # Mark agent as busy
        keeper._agents["agent_001"].status = AgentStatus.BUSY
        
        agent_id = keeper.assign_task(task_id="task_001")
        assert agent_id is None
    
    def test_assign_task_role_filter(self):
        """Test assigning to specific role"""
        keeper = Keeper()
        keeper.register_agent("agent_001", "Teacher", "teacher")
        keeper.register_agent("agent_002", "Learner", "learner")
        
        agent_id = keeper.assign_task(
            task_id="task_001",
            role="learner",
        )
        
        assert agent_id == "agent_002"
    
    def test_release_task(self):
        """Test releasing task from agent"""
        keeper = Keeper()
        keeper.register_agent("agent_001", "Agent 1", "teacher")
        
        keeper.assign_task(task_id="task_001")
        result = keeper.release_task("agent_001", "task_001", success=True)
        
        assert result is True
        agent = keeper.get_agent("agent_001")
        assert len(agent.current_tasks) == 0
        assert agent.total_tasks_completed == 1


class TestHealthCheck:
    """Test health check functionality"""
    
    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        """Test health check with healthy agents"""
        keeper = Keeper()
        keeper.register_agent("agent_001", "Agent 1", "teacher")
        keeper.register_agent("agent_002", "Agent 2", "learner")
        
        result = await keeper.health_check()
        
        assert result["healthy_count"] == 2
        assert result["unhealthy_count"] == 0
        assert len(result["results"]["healthy"]) == 2
    
    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self):
        """Test health check with unhealthy agent"""
        keeper = Keeper()
        keeper.register_agent("agent_001", "Agent 1", "teacher")
        
        # Set old heartbeat
        keeper._agents["agent_001"].last_heartbeat = datetime.now() - timedelta(seconds=60)
        
        result = await keeper.health_check(timeout_seconds=30)
        
        assert result["unhealthy_count"] == 1
        assert "heartbeat_timeout" in result["results"]["unhealthy"][0]["reason"]


class TestStatistics:
    """Test statistics and monitoring"""
    
    def test_get_stats(self):
        """Test getting statistics"""
        keeper = Keeper()
        
        keeper.register_agent("agent_001", "Teacher", "teacher")
        keeper.register_agent("agent_002", "Learner", "learner")
        keeper.register_agent("agent_003", "Reviewer", "reviewer")
        
        stats = keeper.get_stats()
        
        assert stats["total_agents"] == 3
        assert stats["by_role"]["teacher"] == 1
        assert stats["by_role"]["learner"] == 1
        assert stats["by_status"]["idle"] == 3
    
    def test_assignment_stats(self):
        """Test assignment statistics"""
        keeper = Keeper()
        keeper.register_agent("agent_001", "Agent 1", "teacher")
        
        keeper.assign_task("task_001")
        keeper.release_task("agent_001", "task_001", success=True)
        
        stats = keeper.get_stats()
        
        assert stats["assignments"]["total"] == 1
        assert stats["task_stats"]["completed"] == 1


class TestCallbacks:
    """Test callback functionality"""
    
    def test_on_agent_registered(self):
        """Test registration callback"""
        keeper = Keeper()
        
        registered = []
        keeper.on_agent_registered(lambda a: registered.append(a.id))
        
        keeper.register_agent("agent_001", "Agent 1", "teacher")
        
        assert "agent_001" in registered
    
    def test_on_task_assigned(self):
        """Test task assignment callback"""
        keeper = Keeper()
        keeper.register_agent("agent_001", "Agent 1", "teacher")
        
        assigned = []
        keeper.on_task_assigned(lambda a, t: assigned.append((a.id, t)))
        
        keeper.assign_task("task_001")
        
        assert ("agent_001", "task_001") in assigned
