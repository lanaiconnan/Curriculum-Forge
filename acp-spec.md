# ACP — Agent Control Protocol Specification

## Context

Phase 3 Item 1: ACP 远程 Agent 控制

The Gateway needs a protocol for **external agents** (running in separate processes or machines) to:
1. Register with the Gateway
2. Receive task assignments
3. Report progress and results
4. Stream logs/events back to the Gateway

This mirrors how OpenClaw's ACP works — agents are first-class citizens with sessions, not just function calls.

## Architecture

```
External Agent (ACP Client)
    │  POST /acp/register
    │  GET  /acp/{agent_id}/tasks
    │  POST /acp/{agent_id}/tasks/{task_id}/complete
    │  GET  /acp/{agent_id}/stream  (SSE)
    ▼
Gateway (runtimes/gateway.py + acp/)
    │
    ├── ACP session registry (in-memory)
    └── Coordinator (already exists)
```

## ACP Session Lifecycle

```
1. Agent starts → POST /acp/register {agent_id, name, role, capabilities}
                  ← { session_id, gateway_url }

2. Gateway assigns task → GET /acp/{agent_id}/tasks
                          ← [{ task_id, type, payload, assigned_at }]

3. Agent reports progress → POST /acp/{agent_id}/tasks/{task_id}/heartbeat
                            { progress_pct, message }
                            ← { acknowledged: true }

4. Agent completes → POST /acp/{agent_id}/tasks/{task_id}/complete
                      { result, output }
                      ← { task_id, status: "done" }

5. Agent streams events → GET /acp/{agent_id}/stream (SSE)
                          data: { type: "task_assigned", ... }
                          data: { type: "abort", task_id: "..." }
```

## Data Model

### ACPAgent
```python
@dataclass
class ACPAgent:
    agent_id: str          # stable unique ID (e.g. "openclaw-1", "claude-1")
    name: str              # human-readable name
    role: str              # "teacher" | "learner" | "reviewer" | "general"
    capabilities: List[str]  # ["code_generation", "reasoning", "web_search"]
    status: str            # "idle" | "busy" | "offline"
    current_task_id: Optional[str]
    registered_at: datetime
    last_seen: datetime
```

### ACPTask
```python
@dataclass
class ACPTask:
    task_id: str
    agent_id: str
    task_type: str         # "research" | "code" | "review" | "general"
    payload: Dict[str, Any]  # task-specific data
    assigned_at: datetime
    status: str            # "pending" | "in_progress" | "done" | "cancelled"
    progress_pct: int      # 0-100
    result: Optional[Dict[str, Any]]
```

## Gateway Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/acp/register` | Register an external agent |
| DELETE | `/acp/{agent_id}` | Unregister / disconnect an agent |
| GET | `/acp/{agent_id}` | Get agent info and status |
| POST | `/acp/{agent_id}/heartbeat` | Keep-alive + progress update |
| GET | `/acp/{agent_id}/tasks` | List pending tasks for this agent |
| POST | `/acp/{agent_id}/tasks/{task_id}/claim` | Agent claims a task |
| POST | `/acp/{agent_id}/tasks/{task_id}/complete` | Agent reports completion |
| GET | `/acp/{agent_id}/stream` | SSE: real-time task assignments + aborts |

## Implementation Notes

- ACP session registry is **in-memory** (no persistence needed for v1)
- SSE stream uses the same pattern as `/jobs/{id}/stream`
- Coordinator assigns tasks to agents via the existing `assign_task()` mechanism
- External agents can be: OpenClaw instances, Claude CLI, custom scripts, etc.

## File Changes

1. `acp/__init__.py` — module init
2. `acp/protocol.py` — ACPAgent, ACPTask, ACPSessionRegistry
3. `acp/client.py` — ACPAgentClient for external agents to use
4. `runtimes/gateway.py` — ACP endpoints
5. `tests/unit/test_acp.py` — ACP protocol tests
