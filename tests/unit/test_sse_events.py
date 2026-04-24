"""
Test SSE event flow for UI real-time updates.
"""
import asyncio
import json
import pytest

from services.coordinator import CoordinatorEventBus


class TestSSEEventFlow:
    """Test the SSE event subscription and broadcast flow."""

    @pytest.mark.asyncio
    async def test_event_bus_subscribe_emit(self):
        """EventBus should deliver events to subscribers."""
        bus = CoordinatorEventBus()
        
        # Subscribe
        sub_id = bus.subscribe()
        queue = bus.get_queue(sub_id)
        
        # Emit sync (what gateway uses)
        bus.emit_sync("job_created", {"job_id": "test-123", "profile": "rl_controller"})
        
        # Check event was received
        event = queue.get_nowait()
        assert event["type"] == "job_created"
        assert event["payload"]["job_id"] == "test-123"
        
        # Cleanup
        bus.unsubscribe(sub_id)

    @pytest.mark.asyncio
    async def test_event_bus_multiple_subscribers(self):
        """Multiple subscribers should all receive events."""
        bus = CoordinatorEventBus()
        
        sub1 = bus.subscribe()
        sub2 = bus.subscribe()
        q1 = bus.get_queue(sub1)
        q2 = bus.get_queue(sub2)
        
        bus.emit_sync("job_status_changed", {"job_id": "job-1", "status": "running"})
        
        e1 = q1.get_nowait()
        e2 = q2.get_nowait()
        
        assert e1["type"] == "job_status_changed"
        assert e2["type"] == "job_status_changed"
        
        bus.unsubscribe(sub1)
        bus.unsubscribe(sub2)

    @pytest.mark.asyncio
    async def test_event_bus_async_emit(self):
        """Async emit should also deliver events."""
        bus = CoordinatorEventBus()
        
        sub_id = bus.subscribe()
        queue = bus.get_queue(sub_id)
        
        await bus.emit("job_completed", {"job_id": "job-2", "status": "completed"})
        
        event = queue.get_nowait()
        assert event["type"] == "job_completed"
        
        bus.unsubscribe(sub_id)

    @pytest.mark.asyncio
    async def test_event_format_has_timestamp(self):
        """Events should include timestamp."""
        bus = CoordinatorEventBus()
        
        sub_id = bus.subscribe()
        queue = bus.get_queue(sub_id)
        
        bus.emit_sync("test_event", {"foo": "bar"})
        
        event = queue.get_nowait()
        assert "timestamp" in event
        assert "type" in event
        assert "payload" in event
        
        bus.unsubscribe(sub_id)
