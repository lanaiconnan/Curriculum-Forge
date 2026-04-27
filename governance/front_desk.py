"""
Front Desk - 用户前台服务

负责：
- 用户请求接收与分发
- 任务队列管理
- 结果聚合与返回
- 用户会话管理
"""

import uuid
import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
from datetime import datetime
import logging

from governance.metrics import (
    track_request_received,
    track_request_completed,
    track_session_created,
    track_session_ended,
    FRONTDESK_REQUESTS_IN_QUEUE,
    FRONTDESK_BATCH_OPERATIONS,
)

logger = logging.getLogger(__name__)


class RequestStatus(Enum):
    """请求状态"""
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """任务优先级"""
    LOW = 1
    NORMAL = 5
    HIGH = 10
    URGENT = 20


@dataclass
class UserRequest:
    """用户请求"""
    id: str
    user_id: str
    content: str
    priority: TaskPriority = TaskPriority.NORMAL
    
    # 元数据
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # 状态
    status: RequestStatus = RequestStatus.PENDING
    assigned_agent: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    
    # 上下文
    context: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "content": self.content,
            "priority": self.priority.value,
            "status": self.status.value,
            "assigned_agent": self.assigned_agent,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class UserSession:
    """用户会话"""
    id: str
    user_id: str
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    
    # 请求历史
    requests: List[str] = field(default_factory=list)
    
    # 状态
    is_active: bool = True
    
    # 偏好
    preferences: Dict[str, Any] = field(default_factory=dict)
    
    def touch(self):
        """更新活动时间"""
        self.last_active = datetime.now()


class FrontDesk:
    """
    用户前台服务
    
    处理用户请求、任务分发、结果聚合
    """
    
    def __init__(self, keeper=None, mayor=None, coordinator=None):
        self.keeper = keeper
        self.mayor = mayor
        self.coordinator = coordinator
        
        # 请求管理
        self._requests: Dict[str, UserRequest] = {}
        self._pending_queue: asyncio.Queue = None  # Lazy init
        self._processing: Dict[str, str] = {}  # request_id -> agent_id
        
        # 会话管理
        self._sessions: Dict[str, UserSession] = {}
        
        # 回调
        self._on_request_received: Optional[Callable] = None
        self._on_request_completed: Optional[Callable] = None
        self._on_request_failed: Optional[Callable] = None
    
    async def _get_queue(self) -> asyncio.Queue:
        """获取队列（懒加载）"""
        if self._pending_queue is None:
            self._pending_queue = asyncio.Queue()
        return self._pending_queue
    
    # ════════════════════════════════════════════════════════════════════════
    # 请求管理
    # ════════════════════════════════════════════════════════════════════════
    
    async def receive_request(
        self,
        user_id: str,
        content: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        context: Optional[Dict[str, Any]] = None,
    ) -> UserRequest:
        """
        接收用户请求
        
        Args:
            user_id: 用户 ID
            content: 请求内容
            priority: 优先级
            context: 上下文信息
            
        Returns:
            UserRequest
        """
        request_id = f"req_{uuid.uuid4().hex[:8]}"
        
        request = UserRequest(
            id=request_id,
            user_id=user_id,
            content=content,
            priority=priority,
            context=context or {},
        )
        
        self._requests[request_id] = request
        
        # 更新会话
        session = self._get_or_create_session(user_id)
        session.requests.append(request_id)
        session.touch()
        
        # Metrics
        track_request_received(priority.name)
        FRONTDESK_REQUESTS_IN_QUEUE.labels(priority=priority.name).inc()
        
        logger.info(f"Received request {request_id} from user {user_id}")
        
        # 回调
        if self._on_request_received:
            if asyncio.iscoroutinefunction(self._on_request_received):
                await self._on_request_received(request)
            else:
                self._on_request_received(request)
        
        # 入队
        queue = await self._get_queue()
        await queue.put(request_id)
        request.status = RequestStatus.QUEUED
        
        return request
    
    def get_request(self, request_id: str) -> Optional[UserRequest]:
        """获取请求"""
        return self._requests.get(request_id)
    
    def list_requests(
        self,
        user_id: Optional[str] = None,
        status: Optional[RequestStatus] = None,
        limit: int = 100,
    ) -> List[UserRequest]:
        """列出请求"""
        requests = list(self._requests.values())
        
        if user_id:
            requests = [r for r in requests if r.user_id == user_id]
        if status:
            requests = [r for r in requests if r.status == status]
        
        # 按创建时间排序（最新的在前）
        requests.sort(key=lambda r: r.created_at, reverse=True)
        
        return requests[:limit]
    
    async def cancel_request(self, request_id: str) -> bool:
        """取消请求"""
        request = self._requests.get(request_id)
        if not request:
            return False
        
        if request.status in (RequestStatus.COMPLETED, RequestStatus.FAILED):
            return False
        
        request.status = RequestStatus.CANCELLED
        request.updated_at = datetime.now()
        
        logger.info(f"Cancelled request {request_id}")
        return True
    
    # ════════════════════════════════════════════════════════════════════════
    # 任务分发
    # ════════════════════════════════════════════════════════════════════════
    
    async def dispatch_request(self, request_id: str) -> Optional[str]:
        """
        分发请求给 Agent
        
        Args:
            request_id: 请求 ID
            
        Returns:
            分配的 agent_id，或 None
        """
        request = self._requests.get(request_id)
        if not request:
            return None
        
        if not self.keeper:
            logger.warning("No keeper available for dispatch")
            return None
        
        # 检查用户声誉
        if self.mayor and not self.mayor.is_agent_trusted(request.user_id):
            logger.warning(f"User {request.user_id} is not trusted")
            request.status = RequestStatus.FAILED
            request.error = "User reputation too low"
            return None
        
        # 分配 agent
        agent_id = self.keeper.assign_task(
            task_id=request_id,
            requirements=request.context.get("requirements"),
            role=request.context.get("role"),
        )
        
        if not agent_id:
            logger.warning(f"No available agent for request {request_id}")
            return None
        
        request.assigned_agent = agent_id
        request.status = RequestStatus.PROCESSING
        request.updated_at = datetime.now()
        
        self._processing[request_id] = agent_id
        
        logger.info(f"Dispatched request {request_id} to agent {agent_id}")
        
        return agent_id
    
    async def complete_request(
        self,
        request_id: str,
        result: Any,
        success: bool = True,
    ) -> Optional[UserRequest]:
        """
        完成请求
        
        Args:
            request_id: 请求 ID
            result: 结果
            success: 是否成功
            
        Returns:
            更新后的请求
        """
        request = self._requests.get(request_id)
        if not request:
            return None
        
        request.status = RequestStatus.COMPLETED if success else RequestStatus.FAILED
        request.result = result if success else None
        request.error = None if success else str(result)
        request.updated_at = datetime.now()
        
        # 释放 agent
        if request.assigned_agent and self.keeper:
            self.keeper.release_task(
                request.assigned_agent,
                request_id,
                success=success,
            )
        
        # 从处理中移除
        self._processing.pop(request_id, None)
        
        # Metrics
        duration = (request.updated_at - request.created_at).total_seconds()
        track_request_completed(request.priority.name, request.status.value, duration)
        FRONTDESK_REQUESTS_IN_QUEUE.labels(priority=request.priority.name).dec()
        
        # 更新声誉
        if self.mayor and request.user_id:
            if success:
                self.mayor.reward_agent(request.user_id, 1, "Successful request")
            else:
                self.mayor.penalize_agent(request.user_id, 2, "Failed request")
        
        logger.info(f"Completed request {request_id}: {'success' if success else 'failed'}")
        
        # 回调
        callback = self._on_request_completed if success else self._on_request_failed
        if callback:
            if asyncio.iscoroutinefunction(callback):
                await callback(request)
            else:
                callback(request)
        
        return request
    
    # ════════════════════════════════════════════════════════════════════════
    # 会话管理
    # ════════════════════════════════════════════════════════════════════════
    
    def _get_or_create_session(self, user_id: str) -> UserSession:
        """获取或创建会话"""
        if user_id not in self._sessions:
            self._sessions[user_id] = UserSession(
                id=f"session_{uuid.uuid4().hex[:8]}",
                user_id=user_id,
            )
        return self._sessions[user_id]
    
    def get_session(self, user_id: str) -> Optional[UserSession]:
        """获取会话"""
        return self._sessions.get(user_id)
    
    def list_active_sessions(self) -> List[UserSession]:
        """列出活跃会话"""
        return [s for s in self._sessions.values() if s.is_active]
    
    def end_session(self, user_id: str) -> bool:
        """结束会话"""
        session = self._sessions.get(user_id)
        if session:
            session.is_active = False
            return True
        return False
    
    # ════════════════════════════════════════════════════════════════════════
    # 批量操作
    # ════════════════════════════════════════════════════════════════════════
    
    async def receive_batch(
        self,
        requests: List[Dict[str, Any]],
    ) -> List[UserRequest]:
        """
        批量接收请求
        
        Args:
            requests: 请求列表，每个包含 user_id, content, priority(可选)
            
        Returns:
            UserRequest 列表
        """
        results = []
        
        for req_data in requests:
            request = await self.receive_request(
                user_id=req_data["user_id"],
                content=req_data["content"],
                priority=req_data.get("priority", TaskPriority.NORMAL),
                context=req_data.get("context"),
            )
            results.append(request)
        
        logger.info(f"Received batch of {len(results)} requests")
        return results
    
    async def get_batch_results(
        self,
        request_ids: List[str],
        timeout_seconds: float = 60.0,
    ) -> Dict[str, Any]:
        """
        批量获取结果
        
        Args:
            request_ids: 请求 ID 列表
            timeout_seconds: 超时时间
            
        Returns:
            request_id -> result 的字典
        """
        results = {}
        start_time = datetime.now()
        
        while len(results) < len(request_ids):
            for req_id in request_ids:
                if req_id in results:
                    continue
                
                request = self._requests.get(req_id)
                if not request:
                    results[req_id] = {"error": "Request not found"}
                    continue
                
                if request.status == RequestStatus.COMPLETED:
                    results[req_id] = {"success": True, "result": request.result}
                elif request.status == RequestStatus.FAILED:
                    results[req_id] = {"success": False, "error": request.error}
                elif request.status == RequestStatus.CANCELLED:
                    results[req_id] = {"error": "Request cancelled"}
            
            # 检查超时
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed >= timeout_seconds:
                for req_id in request_ids:
                    if req_id not in results:
                        results[req_id] = {"error": "Timeout"}
                break
            
            # 等待
            await asyncio.sleep(0.1)
        
        return results
    
    # ════════════════════════════════════════════════════════════════════════
    # 统计与监控
    # ════════════════════════════════════════════════════════════════════════
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        requests = list(self._requests.values())
        
        return {
            "requests": {
                "total": len(requests),
                "by_status": {
                    status.value: len([r for r in requests if r.status == status])
                    for status in RequestStatus
                },
                "processing": len(self._processing),
            },
            "sessions": {
                "total": len(self._sessions),
                "active": len([s for s in self._sessions.values() if s.is_active]),
            },
            "queue": {
                "pending": self._pending_queue.qsize() if self._pending_queue else 0,
            },
        }
    
    async def process_queue(self):
        """
        处理队列中的请求
        
        从队列中取出请求并分发
        """
        queue = await self._get_queue()
        
        while True:
            try:
                request_id = await asyncio.wait_for(queue.get(), timeout=1.0)
                await self.dispatch_request(request_id)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing queue: {e}")
    
    # ════════════════════════════════════════════════════════════════════════
    # 回调设置
    # ════════════════════════════════════════════════════════════════════════
    
    def on_request_received(self, callback: Callable):
        """设置请求接收回调"""
        self._on_request_received = callback
    
    def on_request_completed(self, callback: Callable):
        """设置请求完成回调"""
        self._on_request_completed = callback
    
    def on_request_failed(self, callback: Callable):
        """设置请求失败回调"""
        self._on_request_failed = callback
