"""
Tests for FrontDesk - User Front Service
"""

import pytest
import asyncio
from datetime import datetime

from governance.front_desk import (
    FrontDesk,
    UserRequest,
    UserSession,
    RequestStatus,
    TaskPriority,
)
from governance.keeper import Keeper
from governance.mayor import Mayor


class TestUserRequest:
    """Test UserRequest dataclass"""
    
    def test_create_request(self):
        """Test creating a request"""
        request = UserRequest(
            id="req_001",
            user_id="user_001",
            content="Test request",
        )
        
        assert request.id == "req_001"
        assert request.user_id == "user_001"
        assert request.status == RequestStatus.PENDING
        assert request.priority == TaskPriority.NORMAL
    
    def test_to_dict(self):
        """Test converting to dict"""
        request = UserRequest(
            id="req_001",
            user_id="user_001",
            content="Test",
            priority=TaskPriority.HIGH,
        )
        
        data = request.to_dict()
        
        assert data["id"] == "req_001"
        assert data["priority"] == 10  # HIGH.value
        assert data["status"] == "pending"


class TestRequestManagement:
    """Test request management"""
    
    @pytest.mark.asyncio
    async def test_receive_request(self):
        """Test receiving a request"""
        desk = FrontDesk()
        
        request = await desk.receive_request(
            user_id="user_001",
            content="Hello, I need help",
        )
        
        assert request.id.startswith("req_")
        assert request.user_id == "user_001"
        assert request.status == RequestStatus.QUEUED
        assert len(desk.list_requests()) == 1
    
    @pytest.mark.asyncio
    async def test_get_request(self):
        """Test getting a request"""
        desk = FrontDesk()
        
        created = await desk.receive_request("user_001", "Test")
        request = desk.get_request(created.id)
        
        assert request is not None
        assert request.id == created.id
        assert desk.get_request("nonexistent") is None
    
    @pytest.mark.asyncio
    async def test_list_requests_filter(self):
        """Test listing requests with filter"""
        desk = FrontDesk()
        
        await desk.receive_request("user_001", "Request 1")
        await desk.receive_request("user_002", "Request 2")
        await desk.receive_request("user_001", "Request 3")
        
        user1_requests = desk.list_requests(user_id="user_001")
        assert len(user1_requests) == 2
    
    @pytest.mark.asyncio
    async def test_cancel_request(self):
        """Test cancelling a request"""
        desk = FrontDesk()
        
        request = await desk.receive_request("user_001", "Test")
        result = await desk.cancel_request(request.id)
        
        assert result is True
        assert request.status == RequestStatus.CANCELLED
        
        # Cannot cancel completed
        request.status = RequestStatus.COMPLETED
        result = await desk.cancel_request(request.id)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self):
        """Test cancelling nonexistent request"""
        desk = FrontDesk()
        result = await desk.cancel_request("nonexistent")
        assert result is False


class TestTaskDispatch:
    """Test task dispatch"""
    
    @pytest.mark.asyncio
    async def test_dispatch_without_keeper(self):
        """Test dispatch without keeper"""
        desk = FrontDesk()
        
        request = await desk.receive_request("user_001", "Test")
        agent_id = await desk.dispatch_request(request.id)
        
        assert agent_id is None
    
    @pytest.mark.asyncio
    async def test_dispatch_with_keeper(self):
        """Test dispatch with keeper"""
        keeper = Keeper()
        keeper.register_agent("agent_001", "Worker", "worker")
        
        desk = FrontDesk(keeper=keeper)
        
        request = await desk.receive_request("user_001", "Test")
        agent_id = await desk.dispatch_request(request.id)
        
        assert agent_id == "agent_001"
        assert request.status == RequestStatus.PROCESSING
        assert request.assigned_agent == "agent_001"
    
    @pytest.mark.asyncio
    async def test_dispatch_no_available_agent(self):
        """Test dispatch when no agent available"""
        keeper = Keeper()
        keeper.register_agent("agent_001", "Worker", "worker")
        keeper._agents["agent_001"].status = "busy"  # Not AgentStatus enum
        
        desk = FrontDesk(keeper=keeper)
        
        request = await desk.receive_request("user_001", "Test")
        agent_id = await desk.dispatch_request(request.id)
        
        assert agent_id is None
    
    @pytest.mark.asyncio
    async def test_dispatch_untrusted_user(self):
        """Test dispatch for untrusted user"""
        keeper = Keeper()
        keeper.register_agent("agent_001", "Worker", "worker")
        
        mayor = Mayor()
        mayor.penalize_agent("user_001", 80, "Bad reputation")  # score=20, not trusted
        
        desk = FrontDesk(keeper=keeper, mayor=mayor)
        
        request = await desk.receive_request("user_001", "Test")
        agent_id = await desk.dispatch_request(request.id)
        
        assert agent_id is None
        assert request.status == RequestStatus.FAILED


class TestRequestCompletion:
    """Test request completion"""
    
    @pytest.mark.asyncio
    async def test_complete_success(self):
        """Test completing request successfully"""
        keeper = Keeper()
        keeper.register_agent("agent_001", "Worker", "worker")
        
        desk = FrontDesk(keeper=keeper)
        
        request = await desk.receive_request("user_001", "Test")
        await desk.dispatch_request(request.id)
        
        result = await desk.complete_request(
            request.id,
            result={"answer": "Done"},
            success=True,
        )
        
        assert result.status == RequestStatus.COMPLETED
        assert result.result == {"answer": "Done"}
    
    @pytest.mark.asyncio
    async def test_complete_failure(self):
        """Test completing request with failure"""
        keeper = Keeper()
        keeper.register_agent("agent_001", "Worker", "worker")
        
        desk = FrontDesk(keeper=keeper)
        
        request = await desk.receive_request("user_001", "Test")
        await desk.dispatch_request(request.id)
        
        result = await desk.complete_request(
            request.id,
            result="Something went wrong",
            success=False,
        )
        
        assert result.status == RequestStatus.FAILED
        assert result.error == "Something went wrong"
    
    @pytest.mark.asyncio
    async def test_complete_updates_reputation(self):
        """Test completion updates user reputation"""
        keeper = Keeper()
        keeper.register_agent("agent_001", "Worker", "worker")
        
        mayor = Mayor()
        
        desk = FrontDesk(keeper=keeper, mayor=mayor)
        
        request = await desk.receive_request("user_001", "Test")
        await desk.dispatch_request(request.id)
        await desk.complete_request(request.id, {"result": "ok"}, success=True)
        
        rep = mayor.get_reputation("user_001")
        assert rep.score == 101  # 100 + 1 (reward)
    
    @pytest.mark.asyncio
    async def test_complete_nonexistent(self):
        """Test completing nonexistent request"""
        desk = FrontDesk()
        
        result = await desk.complete_request("nonexistent", {}, success=True)
        assert result is None


class TestSessionManagement:
    """Test session management"""
    
    @pytest.mark.asyncio
    async def test_session_created_on_request(self):
        """Test session created when receiving request"""
        desk = FrontDesk()
        
        await desk.receive_request("user_001", "Test")
        
        session = desk.get_session("user_001")
        assert session is not None
        assert session.user_id == "user_001"
    
    @pytest.mark.asyncio
    async def test_session_tracks_requests(self):
        """Test session tracks request history"""
        desk = FrontDesk()
        
        req1 = await desk.receive_request("user_001", "Request 1")
        req2 = await desk.receive_request("user_001", "Request 2")
        
        session = desk.get_session("user_001")
        assert len(session.requests) == 2
    
    @pytest.mark.asyncio
    async def test_end_session(self):
        """Test ending a session"""
        desk = FrontDesk()
        
        await desk.receive_request("user_001", "Test")
        result = desk.end_session("user_001")
        
        assert result is True
        session = desk.get_session("user_001")
        assert session.is_active is False
    
    @pytest.mark.asyncio
    async def test_list_active_sessions(self):
        """Test listing active sessions"""
        desk = FrontDesk()
        
        await desk.receive_request("user_001", "Test")
        await desk.receive_request("user_002", "Test")
        desk.end_session("user_001")
        
        active = desk.list_active_sessions()
        assert len(active) == 1
        assert active[0].user_id == "user_002"


class TestBatchOperations:
    """Test batch operations"""
    
    @pytest.mark.asyncio
    async def test_receive_batch(self):
        """Test receiving batch requests"""
        desk = FrontDesk()
        
        requests = await desk.receive_batch([
            {"user_id": "user_001", "content": "Request 1"},
            {"user_id": "user_001", "content": "Request 2"},
            {"user_id": "user_002", "content": "Request 3"},
        ])
        
        assert len(requests) == 3
        assert all(r.status == RequestStatus.QUEUED for r in requests)
    
    @pytest.mark.asyncio
    async def test_get_batch_results(self):
        """Test getting batch results"""
        desk = FrontDesk()
        
        req1 = await desk.receive_request("user_001", "Test 1")
        req2 = await desk.receive_request("user_001", "Test 2")
        
        # Complete one
        await desk.complete_request(req1.id, {"result": "done"}, success=True)
        
        results = await desk.get_batch_results(
            [req1.id, req2.id],
            timeout_seconds=0.5,
        )
        
        assert results[req1.id]["success"] is True
        assert results[req2.id]["error"] == "Timeout"  # Not completed


class TestStatistics:
    """Test statistics"""
    
    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test getting statistics"""
        desk = FrontDesk()
        
        await desk.receive_request("user_001", "Test 1")
        await desk.receive_request("user_002", "Test 2")
        
        stats = desk.get_stats()
        
        assert stats["requests"]["total"] == 2
        assert stats["sessions"]["total"] == 2
        assert stats["requests"]["by_status"]["queued"] == 2


class TestCallbacks:
    """Test callbacks"""
    
    @pytest.mark.asyncio
    async def test_on_request_received(self):
        """Test request received callback"""
        desk = FrontDesk()
        
        received = []
        desk.on_request_received(lambda r: received.append(r.id))
        
        await desk.receive_request("user_001", "Test")
        
        assert len(received) == 1
    
    @pytest.mark.asyncio
    async def test_on_request_completed(self):
        """Test request completed callback"""
        keeper = Keeper()
        keeper.register_agent("agent_001", "Worker", "worker")
        
        desk = FrontDesk(keeper=keeper)
        
        completed = []
        desk.on_request_completed(lambda r: completed.append(r.id))
        
        request = await desk.receive_request("user_001", "Test")
        await desk.dispatch_request(request.id)
        await desk.complete_request(request.id, {}, success=True)
        
        assert request.id in completed
