# ACP 使用指南

Agent Control Protocol (ACP) 是 Curriculum Forge 的外部 Agent 控制协议，允许外部 Agent（运行在其他进程或机器上）注册到 Gateway、接收任务分配、上报进度和结果。

---

## 目录

1. [架构概览](#架构概览)
2. [快速开始](#快速开始)
3. [API 参考](#api-参考)
4. [事件流 (SSE)](#事件流-sse)
5. [Python 客户端示例](#python-客户端示例)
6. [任务生命周期](#任务生命周期)
7. [故障排查](#故障排查)

---

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        Gateway (端口 8765)                       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  ACP Registry   │  │  ACPSession     │  │  Coordinator    │  │
│  │  (内存存储)      │  │  (SSE 队列)      │  │  (任务分配)      │  │
│  └────────┬────────┘  └────────┬────────┘  └─────────────────┘  │
│           │                    │                                 │
│  ┌────────▼────────────────────▼────────┐                        │
│  │         ACP REST API (8 端点)         │                        │
│  │  /acp/register, /acp/{id}/stream...  │                        │
│  └──────────────────┬───────────────────┘                        │
└─────────────────────┼─────────────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
┌──────────────┐ ┌──────────┐ ┌──────────────┐
│  OpenClaw    │ │  Claude  │ │  自定义脚本   │
│   Instance   │ │   CLI    │ │  (Python/JS) │
└──────────────┘ └──────────┘ └──────────────┘
      External Agents (ACP Clients)
```

### 核心概念

| 概念 | 说明 | 状态 |
|------|------|------|
| **ACPAgent** | 注册的外部 Agent | `idle` / `busy` / `offline` |
| **ACPTask** | 分配给 Agent 的任务 | `pending` / `in_progress` / `done` / `cancelled` |
| **ACPSessionRegistry** | 内存中的 Agent 和任务注册表 | - |
| **SSE Stream** | 服务端推送事件流，用于实时通知 | - |

---

## 快速开始

### 1. 注册 Agent

```bash
curl -X POST http://localhost:8765/acp/register \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my-agent-001",
    "name": "代码生成助手",
    "role": "learner",
    "capabilities": ["code_generation", "python", "javascript"]
  }'
```

**返回：**
```json
{
  "session_id": "my-agent-001",
  "agent_id": "my-agent-001",
  "gateway_url": "http://localhost:8765"
}
```

### 2. 连接 SSE 事件流

```bash
curl -N http://localhost:8765/acp/my-agent-001/stream
```

**事件示例：**
```
data: {"type": "task_assigned", "task_id": "acp-task-abc123", "task_type": "code_review", "payload": {...}}

data: {"type": "task_aborted", "task_id": "acp-task-abc123"}
```

### 3. 认领任务

```bash
curl -X POST http://localhost:8765/acp/my-agent-001/tasks/acp-task-abc123/claim
```

### 4. 上报进度

```bash
curl -X POST http://localhost:8765/acp/my-agent-001/heartbeat \
  -H "Content-Type: application/json" \
  -d '{
    "progress_pct": 50,
    "message": "正在分析代码结构..."
  }'
```

### 5. 完成任务

```bash
curl -X POST http://localhost:8765/acp/my-agent-001/tasks/acp-task-abc123/complete \
  -H "Content-Type: application/json" \
  -d '{
    "result": {
      "summary": "代码审查完成",
      "issues_found": 3,
      "suggestions": ["建议1", "建议2"]
    }
  }'
```

---

## API 参考

### Agent 管理

#### POST /acp/register
注册外部 Agent。

**请求体：**
```json
{
  "agent_id": "唯一标识符",
  "name": "显示名称",
  "role": "teacher|learner|reviewer|general",
  "capabilities": ["code_generation", "reasoning", "web_search"]
}
```

**响应：**
```json
{
  "session_id": "session-id",
  "agent_id": "agent-id",
  "gateway_url": "http://localhost:8765"
}
```

#### DELETE /acp/{agent_id}
注销 Agent。

#### GET /acp/{agent_id}
获取 Agent 信息。

**响应：**
```json
{
  "agent_id": "my-agent",
  "name": "My Agent",
  "role": "learner",
  "capabilities": ["code"],
  "status": "busy",
  "current_task_id": "acp-task-xxx",
  "registered_at": 1713987600.0,
  "last_seen": 1713988200.0
}
```

#### GET /acp
列出所有 Agent。

**响应：**
```json
{
  "agents": [...],
  "total": 5,
  "stats": {
    "total_agents": 5,
    "total_tasks": 12,
    "pending_tasks": 3,
    "done_tasks": 8,
    "idle_agents": 2,
    "busy_agents": 3
  }
}
```

### 心跳与进度

#### POST /acp/{agent_id}/heartbeat
保持连接活跃，可选上报任务进度。

**请求体：**
```json
{
  "progress_pct": 75,
  "message": "当前进度描述"
}
```

### 任务管理

#### GET /acp/{agent_id}/tasks
获取 Agent 的任务列表。

**查询参数：**
- `status` - 可选过滤：`pending`, `in_progress`, `done`, `cancelled`

**响应：**
```json
{
  "tasks": [
    {
      "task_id": "acp-task-xxx",
      "agent_id": "my-agent",
      "task_type": "code_review",
      "payload": {...},
      "status": "in_progress",
      "progress_pct": 50,
      "message": "分析中...",
      "assigned_at": 1713987600.0
    }
  ],
  "total": 1
}
```

#### POST /acp/{agent_id}/tasks/{task_id}/claim
认领待处理任务。

#### POST /acp/{agent_id}/tasks/{task_id}/complete
标记任务完成并提交结果。

**请求体：**
```json
{
  "result": {
    "任意": "结果数据"
  }
}
```

### SSE 事件流

#### GET /acp/{agent_id}/stream
建立 SSE 连接，接收实时事件。

**事件类型：**

| 类型 | 说明 | 数据 |
|------|------|------|
| `task_assigned` | 新任务分配 | `task_id`, `task_type`, `payload` |
| `task_completed` | 任务完成确认 | `task_id`, `result` |
| `task_aborted` | 任务被取消 | `task_id` |

---

## 事件流 (SSE)

SSE (Server-Sent Events) 是 ACP 的核心机制，用于 Gateway 向 Agent 推送实时事件。

### 连接方式

```javascript
const eventSource = new EventSource('http://localhost:8765/acp/my-agent/stream');

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('收到事件:', data.type, data);
  
  switch (data.type) {
    case 'task_assigned':
      handleTaskAssigned(data);
      break;
    case 'task_aborted':
      handleTaskAborted(data);
      break;
  }
};

eventSource.onerror = (err) => {
  console.error('SSE 错误:', err);
  // 自动重连逻辑
};
```

### Python 客户端

```python
import httpx

def stream_events(agent_id: str, gateway_url: str = "http://localhost:8765"):
    """SSE 事件流生成器"""
    with httpx.stream("GET", f"{gateway_url}/acp/{agent_id}/stream") as response:
        for line in response.iter_lines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                yield data
```

### 心跳机制

- SSE 连接每 60 秒发送一次 keepalive（以 `:` 开头的注释行）
- Agent 应定期发送 `POST /acp/{agent_id}/heartbeat` 保持活跃
- 超过 `heartbeat_ttl`（默认 60 秒）未心跳的 Agent 会被标记为 `offline`

---

## Python 客户端示例

### 完整 Agent 实现

```python
import asyncio
import json
import httpx
from typing import Dict, Any, Optional

class ACPAgentClient:
    """ACP Agent 客户端"""
    
    def __init__(
        self,
        agent_id: str,
        name: str,
        role: str = "general",
        capabilities: list = None,
        gateway_url: str = "http://localhost:8765"
    ):
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.capabilities = capabilities or []
        self.gateway_url = gateway_url
        self.client = httpx.AsyncClient()
        self.current_task: Optional[Dict] = None
        self.running = False
    
    async def register(self) -> Dict:
        """注册到 Gateway"""
        resp = await self.client.post(
            f"{self.gateway_url}/acp/register",
            json={
                "agent_id": self.agent_id,
                "name": self.name,
                "role": self.role,
                "capabilities": self.capabilities
            }
        )
        resp.raise_for_status()
        return resp.json()
    
    async def unregister(self):
        """注销"""
        await self.client.delete(f"{self.gateway_url}/acp/{self.agent_id}")
    
    async def heartbeat(self, progress_pct: int = None, message: str = ""):
        """发送心跳"""
        payload = {}
        if progress_pct is not None:
            payload["progress_pct"] = progress_pct
        if message:
            payload["message"] = message
        
        await self.client.post(
            f"{self.gateway_url}/acp/{self.agent_id}/heartbeat",
            json=payload
        )
    
    async def claim_task(self, task_id: str) -> Dict:
        """认领任务"""
        resp = await self.client.post(
            f"{self.gateway_url}/acp/{self.agent_id}/tasks/{task_id}/claim"
        )
        resp.raise_for_status()
        self.current_task = resp.json()["task"]
        return self.current_task
    
    async def complete_task(self, result: Dict):
        """完成任务"""
        if not self.current_task:
            raise RuntimeError("没有正在执行的任务")
        
        task_id = self.current_task["task_id"]
        resp = await self.client.post(
            f"{self.gateway_url}/acp/{self.agent_id}/tasks/{task_id}/complete",
            json={"result": result}
        )
        resp.raise_for_status()
        self.current_task = None
        return resp.json()
    
    async def run(self):
        """主循环：监听事件并处理任务"""
        self.running = True
        
        # 注册
        await self.register()
        print(f"Agent {self.agent_id} 已注册")
        
        # 启动 SSE 监听
        while self.running:
            try:
                async with httpx.AsyncClient() as client:
                    async with client.stream(
                        "GET",
                        f"{self.gateway_url}/acp/{self.agent_id}/stream"
                    ) as response:
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                event = json.loads(line[6:])
                                await self._handle_event(event)
            except Exception as e:
                print(f"SSE 连接错误: {e}, 5秒后重连...")
                await asyncio.sleep(5)
    
    async def _handle_event(self, event: Dict):
        """处理事件"""
        event_type = event.get("type")
        
        if event_type == "task_assigned":
            task_id = event["task_id"]
            print(f"收到任务: {task_id}")
            
            # 认领任务
            task = await self.claim_task(task_id)
            
            # 执行任务
            await self._execute_task(task)
        
        elif event_type == "task_aborted":
            print(f"任务被取消: {event['task_id']}")
            self.current_task = None
    
    async def _execute_task(self, task: Dict):
        """执行任务（子类可重写）"""
        task_type = task["task_type"]
        payload = task["payload"]
        
        print(f"执行任务: {task_type}")
        
        # 模拟进度更新
        for i in range(0, 101, 25):
            await self.heartbeat(progress_pct=i, message=f"进度 {i}%")
            await asyncio.sleep(1)
        
        # 提交结果
        result = {
            "task_type": task_type,
            "status": "completed",
            "output": f"任务 {task_type} 执行完成"
        }
        await self.complete_task(result)
        print(f"任务完成: {task['task_id']}")
    
    async def stop(self):
        """停止 Agent"""
        self.running = False
        await self.unregister()
        await self.client.aclose()


# 使用示例
async def main():
    agent = ACPAgentClient(
        agent_id="code-agent-001",
        name="代码助手",
        role="learner",
        capabilities=["code_generation", "python"]
    )
    
    try:
        await agent.run()
    except KeyboardInterrupt:
        await agent.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 任务生命周期

```
┌─────────┐    assign      ┌──────────┐    claim      ┌─────────────┐
│ 创建任务 │ ─────────────→ │  pending │ ────────────→ │ in_progress │
│         │                │ (待认领)  │               │  (执行中)    │
└─────────┘                └──────────┘               └──────┬──────┘
                                                             │
                              ┌─────────────────────────────┼──────┐
                              │                             │      │
                              ▼                             ▼      │
                         ┌─────────┐                  ┌────────┐  │
                         │cancelled│                  │  done  │◄─┘
                         │(已取消)  │                  │(已完成)│
                         └─────────┘                  └────────┘
                              ▲                            │
                              └────────── abort ───────────┘
```

### 状态说明

| 状态 | 说明 | 转换条件 |
|------|------|----------|
| `pending` | 任务已创建，等待 Agent 认领 | 自动分配或手动创建 |
| `in_progress` | Agent 已认领，正在执行 | 调用 `claim` |
| `done` | 任务完成，结果已提交 | 调用 `complete` |
| `cancelled` | 任务被取消 | 调用 `abort` 或 Agent 离线 |

---

## 故障排查

### Agent 注册失败

**现象：** 返回 400 错误

**排查：**
```bash
# 检查 agent_id 是否已存在
curl http://localhost:8765/acp/my-agent-id

# 检查请求格式
curl -X POST http://localhost:8765/acp/register \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "test", "name": "Test"}'
```

### SSE 连接断开

**现象：** 事件流频繁断开

**解决：**
```python
# 添加自动重连逻辑
async def connect_with_retry(agent_id: str, max_retries: int = 10):
    for attempt in range(max_retries):
        try:
            async with httpx.stream("GET", f"{gateway}/acp/{agent_id}/stream") as resp:
                async for line in resp.aiter_lines():
                    yield line
        except Exception as e:
            wait = min(2 ** attempt, 60)  # 指数退避
            print(f"重连 {attempt+1}/{max_retries}, 等待 {wait}s...")
            await asyncio.sleep(wait)
```

### 任务认领失败

**现象：** 返回 404

**原因：**
1. 任务已被其他 Agent 认领
2. 任务状态不是 `pending`
3. 任务 ID 不存在

**排查：**
```bash
# 检查任务状态
curl "http://localhost:8765/acp/my-agent/tasks?status=pending"
```

### Agent 被标记为 offline

**现象：** Agent 状态变为 `offline`

**解决：**
```python
# 增加心跳频率（默认 60 秒）
async def heartbeat_loop(agent: ACPAgentClient):
    while True:
        await agent.heartbeat()
        await asyncio.sleep(30)  # 每 30 秒心跳一次
```

### 查看 Agent 统计

```bash
curl http://localhost:8765/acp
```

---

## 参考

- [ACP 协议规范](./acp-spec.md)
- [Gateway API 文档](./GATEWAY_API_CN.md)

---

*文档版本: 1.0*
*最后更新: 2026-04-24*
