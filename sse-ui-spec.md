# SPEC.md — Phase 3 Item 2: Web UI SSE 实时流

## 背景

Gateway 已具备 SSE 基础设施：
- `GET /jobs/{job_id}/stream` — 单个 Job 的实时事件流
- `GET /coordinator/events` — 全局 Coordinator 事件流
- `GET /workflows/{workflow_id}/stream` — Workflow 实时事件流

React UI 当前使用轮询（`useEffect` 每 5 秒调用 `/jobs`），体验不实时。

## 目标

用 SSE 替代轮询，实现真正的实时推送：
- Job 列表：监听 `/coordinator/events`，有新 Job 或状态变化时实时更新
- Job 详情：监听 `/jobs/{job_id}/stream`，实时显示执行进度

## 改动范围

### 1. `ui/operator-ui/src/App.tsx` — 顶层

- `useEffect` 启动时订阅 `/coordinator/events` SSE
- 收到事件后更新对应的 Job 状态（无需重新拉列表）
- 保留 fallback 轮询（断线重连兜底）

### 2. `ui/operator-ui/src/components/JobDetail.tsx`（新建）

- 接收 `jobId` prop
- 组件 mount 时订阅 `/jobs/{jobId}/stream` SSE
- 收到事件后更新 Job 状态/输出
- 组件 unmount 时关闭 SSE 连接
- Job 完成后显示最终状态

### 3. `ui/operator-ui/src/api.ts` — SSE 辅助函数

- `streamEvents(url, onMessage, onError)` — 通用 SSE 连接管理
- 包含：EventSource 创建、自动重连（指数退避，最多 5 次）、连接关闭

### 4. `runtimes/gateway.py` — 可选改进

- `/jobs` GET 端点返回时带上 `events_url` 字段（客户端直接用）
- CoordinatorEventBus 发射事件时 `_publish_event(job_id, event)` 也同步调用（避免遗漏）
- 确认 `_publish_event` 在 `complete_task()` 和 `workflow_completed` 时被调用

## SSE 事件格式（Gateway → Client）

```json
// Job 状态更新
{"type": "job_status_changed", "job_id": "job-xxx", "status": "running", "timestamp": "..."}

// Job 输出/进度
{"type": "job_output", "job_id": "job-xxx", "phase": "harness", "data": {...}}

// Job 完成
{"type": "job_completed", "job_id": "job-xxx", "status": "completed", "result": {...}}

// Job 失败
{"type": "job_failed", "job_id": "job-xxx", "status": "failed", "error": "..."}

// 新 Job 创建（来自 Coordinator）
{"type": "job_created", "job_id": "job-xxx", "profile": "rl_controller", "status": "pending"}

// Workflow 事件
{"type": "workflow_started", "workflow_id": "wf-xxx"}
{"type": "workflow_completed", "workflow_id": "wf-xxx", "status": "completed"}
```

## 验收标准

1. 创建 Job 后，Jobs 列表立即出现新 Job（无需等待下次轮询）
2. Job 执行中，Job 详情实时显示 phase 变化
3. Job 完成后，状态立即更新为 completed/failed
4. SSE 断开时自动重连（最多 5 次）
5. 全量测试持续通过
