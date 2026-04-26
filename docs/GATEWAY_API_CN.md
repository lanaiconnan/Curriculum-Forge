# � Gate Gateway API 文档

Curriculum-Forge Gateway 是系统的 HTTP API 入口，基于 FastAPI 构建，端口 **8765**。

---

## 基本信息

| 项目 | 值 |
|------|------|
| 基础地址 | `http://localhost:8765` |
| API 文档 | `http://localhost:8765/docs`（Swagger UI） |
| 健康检查 | `GET /health` |
| Web UI | `GET /ui/` → Operator 控制台 |
| 数据目录 | `~/.curriculum-forge/checkpoints/` |

### 请求格式

- `Content-Type: application/json`
- 所有请求体为 JSON
- 响应除非注明均为 JSON

### 状态码约定

| 状态码 | 含义 |
|--------|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 400 | 参数错误 |
| 404 | 资源不存在 |
| 409 | 冲突（如 job 已在运行） |
| 500 | 服务端错误 |

---

## 任务（Jobs）

### 列表 `GET /jobs`

查询所有 checkpoint 记录。

**参数（Query）：**

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `profile` | string | — | 按 profile 名称过滤 |
| `state` | string | — | 按状态过滤：`PENDING` / `RUNNING` / `COMPLETED` / `FAILED` |
| `limit` | int | 50 | 最大返回数量（1–500） |

**响应示例：**
```json
{
  "jobs": [
    {
      "id": "run_20260424_140000",
      "profile": "rl_controller",
      "status": "COMPLETED",
      "current_phase": "curriculum",
      "created_at": "2026-04-24T06:00:00+00:00",
      "finished_at": "2026-04-24T06:05:30+00:00",
      "retry_count": 0,
      "max_retries": 2,
      "metrics": {
        "providers_run": 3,
        "providers_succeeded": 3,
        "phase_durations": { "curriculum": 120000, "harness": 180000 }
      }
    }
  ],
  "total": 1
}
```

---

### 创建 `POST /jobs`

创建新任务，支持两种方式。

#### 方式一：指定 Profile（推荐）

```json
{
  "profile": "rl_controller",
  "description": "我的第一个训练",
  "config_overrides": {
    "max_iterations": 10,
    "topic": "custom topic"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `profile` | string | ✅ | Profile 名称（对应 `profiles/{name}.json`） |
| `description` | string | — | 任务描述 |
| `config_overrides` | object | — | 配置覆盖，优先级最高 |

**响应：**
```json
{
  "job": { "id": "run_20260424_140000", "status": "PENDING", ... },
  "created": true
}
```

#### 方式二：完整 Proposal

```json
{
  "proposal": {
    "profile": "rl_controller",
    "config": { "max_iterations": 5 },
    "description": "自定义任务"
  }
}
```

> `proposal` 优先于 `profile`。

---

### 详情 `GET /jobs/{job_id}`

获取单个任务的完整信息（包含 state_data）。

```bash
curl http://localhost:8765/jobs/run_20260424_140000
```

---

### 执行指标 `GET /jobs/{job_id}/metrics`

获取任务的执行指标和统计数据。

**响应：**
```json
{
  "job_id": "run_20260424_140000",
  "phase": "curriculum",
  "state": "COMPLETED",
  "duration_ms": 330000,
  "started_at": "2026-04-24T06:00:00+00:00",
  "finished_at": "2026-04-24T06:05:30+00:00",
  "providers_run": 3,
  "providers_succeeded": 3,
  "retry_count": 0,
  "max_retries": 2,
  "phase_durations": {
    "curriculum": 120000,
    "harness": 180000,
    "memory": 30000
  },
  "tokens_used": 45000,
  "tokens_prompt": 30000,
  "tokens_completion": 15000,
  "error": null
}
```

---

### 对比 `GET /jobs/compare`

并排对比多个任务的指标。

```bash
curl "http://localhost:8765/jobs/compare?ids=job1,job2,job3"
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `ids` | string | ✅ | 逗号分隔的 job ID（最多 10 个） |

**响应：**
```json
{
  "jobs": [ /* 各 job 的 metrics */ ],
  "summary": {
    "count": 3,
    "avg_duration_ms": 350000,
    "min_duration_ms": 200000,
    "max_duration_ms": 500000,
    "total_providers_run": 9,
    "total_retries": 1
  }
}
```

---

### 恢复 `POST /jobs/{job_id}/resume`

重新运行失败或待处理的任务。

```bash
curl -X POST http://localhost:8765/jobs/run_20260424_140000/resume
```

---

### 中止 `POST /jobs/{job_id}/abort`

中止正在运行的任务。

```bash
curl -X POST http://localhost:8765/jobs/run_20260424_140000/abort
```

---

### 实时流（ SSE） `GET /jobs/{job_id}/stream`

SSE 流，实时推送任务状态更新。

**Event 示例：**
```
data: {"event": "update", "job": {"id": "run_xxx", "status": "RUNNING"}}

data: {"event": "done", "state": "COMPLETED"}
```

---

### 删除 Workspace `DELETE /jobs/{job_id}/workspace`

删除任务的工作目录（释放磁盘空间）。

```bash
curl -X DELETE http://localhost:8765/jobs/run_20260424_140000/workspace
```

---

## Profile 管理

Profile 定义任务的默认配置，位于 `profiles/` 目录下的 JSON 文件。

### 列表 `GET /profiles`

```json
{
  "profiles": [
    { "name": "rl_controller", "file": "rl_controller.json", "description": "..." },
    { "name": "pure_harness", "file": "pure_harness.json", "description": "..." }
  ]
}
```

---

### 详情 `GET /profiles/{name}`

获取 Profile 及其解析后的有效默认值。

```bash
curl http://localhost:8765/profiles/rl_controller
```

**响应：**
```json
{
  "name": "rl_controller",
  "file": "rl_controller.json",
  "data": { /* 原始 JSON */ },
  "valid": true,
  "errors": [],
  "effective_defaults": { /* 合并了 defaults/service_defaults 后的配置 */ },
  "service_defaults": {
    "environment": { "topic": "..." },
    "learner": { "max_iterations": 5 }
  }
}
```

---

### 校验 `GET /profiles/{name}/validate`

校验 Profile JSON 的合法性。

```json
{
  "name": "rl_controller",
  "valid": true,
  "errors": []
}
```

---

### Schema `GET /profiles/schema`

返回 Profile JSON Schema 说明。

---

## 统计（Stats）

### 概览 `GET /stats`

返回任务总量、分状态统计、分 Profile 统计。

```json
{
  "total": 42,
  "success_rate": 0.76,
  "avg_duration_seconds": 285.3,
  "total_retries": 8,
  "by_state": { "COMPLETED": 32, "FAILED": 5, "PENDING": 3, "RUNNING": 2 },
  "by_profile": {
    "rl_controller": { "total": 30, "success_rate": 0.80, "avg_duration": 270 },
    "progressive_disclosure": { "total": 12, "success_rate": 0.67, "avg_duration": 320 }
  }
}
```

---

### 时序趋势 `GET /stats/timeseries`

返回按小时分桶的时间序列数据，用于绘制趋势图。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `hours` | int | 24 | 时间范围（小时） |

**响应：**
```json
{
  "hours": 24,
  "buckets": [
    {
      "timestamp": "2026-04-24T00:00:00Z",
      "total": 5,
      "completed": 4,
      "failed": 1,
      "avg_duration_ms": 300000,
      "retries": 1
    }
  ]
}
```

---

## 审计日志（Audit）

### 查询 `GET /audit`

| 参数 | 类型 | 说明 |
|------|------|------|
| `category` | string | 类别过滤：`job` / `acp` |
| `event` | string | 事件类型：`job_created` / `job_completed` 等 |
| `actor` | string | 操作者 |
| `target` | string | 目标资源 |
| `date` | string | 日期过滤（YYYY-MM-DD） |
| `limit` | int | 返回数量（默认 100） |
| `offset` | int | 偏移量 |

```bash
curl "http://localhost:8765/audit?category=job&limit=10"
```

---

### 统计 `GET /audit/stats`

返回指定日期的审计统计。

```json
{
  "total_events": 120,
  "by_category": { "job": 80, "acp": 40 },
  "by_event": { "job_created": 30, "job_completed": 25, "job_failed": 5 }
}
```

---

## 插件（Plugins）

### 列表 `GET /plugins`

```json
{
  "plugins": ["reward-logger", "experiment-filter", "stage-tracker"],
  "total": 3
}
```

---

### 详情 `GET /plugins/{name}`

```json
{
  "name": "reward-logger",
  "version": "1.0.0",
  "description": "记录奖励日志",
  "hooks": ["job:before_run", "job:after_completed", "job:after_failed"],
  "priority": 10,
  "initialized": true
}
```

---

### 启用 `POST /plugins/{name}/enable`

启用插件（如果之前被禁用）。

---

### 禁用 `POST /plugins/{name}/disable`

禁用插件，停止所有 Hook 触发。

---

### 更新配置 `PUT /plugins/{name}/config`

更新插件运行时配置（内存中）。

```json
{
  "log_file": "/tmp/reward.log",
  "verbose": true
}
```

---

## Agent 与 Workflow（Multi-Agent）

### Agent 列表 `GET /agents`

返回 Coordinator 注册的所有 Agent。

```json
{
  "agents": [
    {
      "id": "agent_001",
      "name": "Teacher",
      "role": "teacher",
      "status": "idle",
      "capabilities": ["generate_task", "evaluate"],
      "current_task": null
    }
  ],
  "total": 1
}
```

---

### Workflow 列表 `GET /workflows`

```json
{
  "workflows": [
    {
      "id": "wf_xxx",
      "name": "job_run_20260424_140000",
      "status": "running",
      "tasks": 3
    }
  ],
  "total": 1
}
```

---

### Workflow 详情 `GET /workflows/{workflow_id}`

返回单个 Workflow 的详细信息（含各 Task 状态）。

---

### 创建 Workflow `POST /workflows`

创建并启动新的 Workflow。

```json
{
  "name": "my_workflow",
  "description": "测试工作流",
  "tasks": [
    {
      "id": "task_1",
      "type": "curriculum",
      "stage": "default",
      "dependencies": []
    },
    {
      "id": "task_2",
      "type": "harness",
      "stage": "default",
      "dependencies": ["task_1"]
    }
  ]
}
```

---

### Workflow 实时流（ SSE） `GET /workflows/{workflow_id}/stream`

SSE 流，跟踪特定 Workflow 的实时状态。

---

## ACP（Agent Control Protocol）

ACP 是外部 Agent 向 Gateway 注册、心跳保活、领取任务、完成报告的协议。

### 注册 `POST /acp/register`

```json
{
  "agent_id": "my-agent-001",
  "name": "我的 Agent",
  "role": "evaluator",
  "capabilities": ["code_review", "test_evaluation"]
}
```

**响应：**
```json
{
  "session_id": "sess_xxx",
  "agent_id": "my-agent-001",
  "gateway_url": "http://localhost:8765"
}
```

---

### 心跳 `POST /acp/{agent_id}/heartbeat`

```json
{
  "progress_pct": 75,
  "message": "正在执行第 3 个 task"
}
```

---

### 任务列表 `GET /acp/{agent_id}/tasks`

| 参数 | 类型 | 说明 |
|------|------|------|
| `status` | string | 按状态过滤：`pending` / `claimed` / `completed` |

---

### 领取任务 `POST /acp/{agent_id}/tasks/{task_id}/claim`

Agent 认领一个待处理任务。

---

### 完成任务 `POST /acp/{agent_id}/tasks/{task_id}/complete`

```json
{
  "result": {
    "score": 0.85,
    "feedback": "测试全部通过"
  }
}
```

---

### Agent SSE 流（ SSE） `GET /acp/{agent_id}/stream`

SSE 流，实时接收任务分配和中止事件。

---

### Agent 列表 `GET /acp`

返回所有已注册的 ACP Agent 及其统计。

---

## 认证与安全（Authentication）

> 从 P6 版本开始，Gateway 支持完整的认证和权限控制体系。
> 开发模式默认关闭认证，生产环境必须启用。

### 启用认证

设置环境变量：

```bash
export CF_ENABLE_AUTH=1
```

### API Key 认证

API Key 适合服务间调用，支持 `X-API-Key` 或 `Bearer` 两种方式。

#### 创建 API Key `POST /auth/keys`

仅 admin 可创建。

```json
{
  "name": "production-key",
  "scope": "write",
  "rate_limit_per_hour": 1000
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | Key 名称 |
| `scope` | string | ✅ | 权限范围：`read` / `write` / `admin` |
| `rate_limit_per_hour` | int | — | 每小时请求限制（默认 1000） |

**响应（仅创建时返回完整 Key）：**

```json
{
  "id": "key_abc123",
  "name": "production-key",
  "api_key": "cf_live_xxxxxxxxxxxxxxxx",
  "scope": "write",
  "rate_limit_per_hour": 1000,
  "created_at": "2026-04-26T10:00:00Z"
}
```

> ⚠️ **重要**：`api_key` 仅创建时返回，请务必保存。

#### 列出 API Keys `GET /auth/keys`

返回脱敏后的 Key 列表（仅显示前 8 位）。

#### 删除 API Key `DELETE /auth/keys/{key_id}`

仅 admin 可删除。

#### 使用 API Key

**方式一：X-API-Key 请求头**

```bash
curl -H "X-API-Key: cf_live_xxxxxxxxxxxxxxxx" \
     http://localhost:8765/jobs
```

**方式二：Bearer Token**

```bash
curl -H "Authorization: Bearer cf_live_xxxxxxxxxxxxxxxx" \
     http://localhost:8765/jobs
```

### JWT 认证

JWT 适合用户会话管理，支持登录/刷新/登出流程。

#### 登录 `POST /auth/login`

```json
{
  "username": "admin",
  "password": "your-password"
}
```

**响应：**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 900
}
```

- Access Token：15 分钟有效期
- Refresh Token：7 天有效期

#### 刷新 Token `POST /auth/refresh`

```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

#### 登出 `POST /auth/logout`

需要携带有效的 Access Token。

#### 查看当前用户 `GET /auth/me`

返回当前登录用户的信息。

### 用户管理（仅 admin）

#### 创建用户 `POST /users`

```json
{
  "username": "zhangsan",
  "password": "secure-password",
  "email": "zhangsan@example.com",
  "full_name": "张三",
  "roles": ["operator"]
}
```

#### 列出用户 `GET /users`

#### 获取用户详情 `GET /users/{user_id}`

#### 更新用户 `PUT /users/{user_id}`

```json
{
  "email": "new@example.com",
  "roles": ["viewer"]
}
```

#### 修改密码 `POST /users/{user_id}/password`

```json
{
  "current_password": "old-password",
  "new_password": "new-secure-password"
}
```

#### 删除用户 `DELETE /users/{user_id}`

### RBAC 角色管理

系统预定义 3 个角色：

| 角色 | 权限 |
|------|------|
| `admin` | `*.*`（全部权限） |
| `operator` | `jobs.*`, `templates.*`, `schedules.*`, `acp.*` |
| `viewer` | `jobs.read`, `templates.read`, `schedules.read`, `profiles.read` |

#### 列出角色 `GET /roles`

#### 获取角色详情 `GET /roles/{name}`

#### 创建角色 `POST /roles`（仅 admin）

```json
{
  "name": "data-scientist",
  "display_name": "数据科学家",
  "description": "可创建任务，不可管理用户",
  "permissions": ["jobs.*", "templates.read"]
}
```

权限格式：`resource.action`，支持通配符 `*`。

---

## Channel Webhooks

Channel 是消息通道（飞书/微信）与 Job 的桥接层。Gateway 不直接暴露 Channel webhook 端点，它们由 Channel 适配器内部注册。

### 飞书 `POST /webhooks/feishu`

飞书事件接收（由 `setup_feishu_webhook()` 注册）。

### 微信 `POST /webhooks/weixin`

微信事件接收（由 `setup_weixin_webhook()` 注册）。

> Channel Webhook 配置详见 [CHANNEL_CN.md](CHANNEL_CN.md)（待编写）。

---

## SSE 事件类型

### Coordinator 全局事件 `GET /coordinator/events`

| Event 类型 | 触发时机 |
|-----------|---------|
| `job_created` | Job 创建 |
| `job_completed` | Job 成功完成 |
| `job_failed` | Job 失败 |
| `job_status_changed` | Job 状态变更（running/cancelled） |
| `task_assigned` | Task 分配给 Agent |
| `task_completed` | Task 完成 |
| `agent_status_changed` | Agent 状态变更 |

---

## 配置优先级

系统配置合并顺序（从低到高）：

1. `profiles/{name}.json` 中的 `defaults` 字段
2. `profiles/{name}.json` 中的 `service_defaults` 字段
3. 环境变量（如 `CF_TOPIC`、`CF_MAX_ITERATIONS`）
4. API 请求中的 `config_overrides`

---

## 环境变量

### 业务配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CF_TOPIC` | 训练主题 | `Curriculum-Forge` |
| `CF_MAX_ITERATIONS` | 最大迭代次数 | 5 |
| `CF_PASS_THRESHOLD` | 通过阈值 | 0.65 |
| `CF_DIFFICULTY` | 初始难度 | 0.5 |
| `CF_GOAL` | 目标描述 | — |

### 安全配置（P6 新增）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CF_ENABLE_AUTH` | 启用认证和权限控制 | `0`（关闭）|
| `CF_JWT_SECRET` | JWT 签名密钥（生产必须修改）| 随机生成 |
| `CF_ADMIN_PASSWORD` | 默认 admin 用户密码 | `admin` |

---

## 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `Profile 'xxx' not found` | Profile 文件不存在 | 检查 `profiles/` 目录 |
| `Job 'xxx' not found` | Job ID 不存在 | 用 `GET /jobs` 查看有效 ID |
| `Job is already running` | 重复 resume | 等待当前运行完成或先 abort |
| `Agent not found` | ACP Agent 未注册 | 先 `POST /acp/register` |
| 503 No coordinator configured | Coordinator 初始化失败 | 检查日志，确认 Agent 配置正确 |
| 401 Unauthorized | 未认证或 Token 过期 | 检查 `Authorization` 请求头或重新登录 |
| 403 Forbidden | 权限不足 | 检查用户角色是否包含所需权限 |
| 429 Too Many Requests | 超出 API Key 速率限制 | 等待一小时或申请更高限额 |
| Account locked | 5 次密码错误 | 等待 15 分钟后重试 |

---

**启动 Gateway：**
```bash
cd ~/.qclaw/workspace/dual-agent-tool-rl
python3 main.py --gateway --port 8765
```
