# Gateway + Operator UI 规格文档

## 1. 目标与背景

**目标**：为 dual-agent-tool-rl 项目增加 HTTP Gateway 服务和可视化 Web UI，使外部系统可以远程管理任务、查看状态、接收实时进度。

**背景**：
- 当前项目只有 CLI 界面（forge run/list/status/log）
- 缺少远程 API 和可视化能力
- 用户需要通过 Web 界面管理任务

---

## 2. 功能需求

### 2.1 Gateway API 服务

| 端点 | 方法 | 功能 |
|------|------|------|
| `/health` | GET | 健康检查，返回服务状态 |
| `/jobs` | GET | 列出所有 checkpoint 记录 |
| `/jobs/{id}` | GET | 获取单个 checkpoint 详情 |
| `/jobs` | POST | 创建新任务（提交 proposal） |
| `/jobs/{id}/resume` | POST | 恢复指定 checkpoint |
| `/jobs/{id}/abort` | POST | 中止正在运行的任务 |
| `/jobs/{id}/stream` | GET | SSE 实时推送任务进度 |

### 2.2 Operator Web UI

| 功能 | 描述 |
|------|------|
| Jobs 面板 | 列出所有任务，支持搜索、筛选、排序 |
| 任务详情 | 显示单个任务的完整状态、阶段、输出 |
| 创建任务 | 表单提交新任务 |
| 实时进度 | SSE 接收任务进度更新 |

### 2.3 部署方式

- 集成到 main.py，添加 `--gateway` 标志
- 默认端口：8765
- 前端静态文件：`ui/operator-ui/dist/`
- 单进程部署（Gateway + API + UI 同一进程）

---

## 3. 技术架构

### 3.1 技术栈

| 组件 | 技术选型 |
|------|---------|
| Gateway 框架 | FastAPI |
| API 文档 | 自动 OpenAPI (Swagger UI) |
| 实时推送 | Server-Sent Events (SSE) |
| 前端框架 | React + Vite |
| UI 样式 | Tailwind CSS |

### 3.2 模块结构

```
dual-agent-tool-rl/
├── runtimes/
│   └── gateway.py          # FastAPI 应用
├── ui/
│   └── operator-ui/        # React+Vite 项目
│       ├── src/
│       │   ├── App.tsx
│       │   ├── components/
│       │   └── api.ts
│       ├── index.html
│       ├── package.json
│       └── vite.config.ts
├── main.py                 # 集成 --gateway 标志
└── requirements.txt        # 添加 fastapi, uvicorn
```

### 3.3 关键依赖

**Python 端：**
- `fastapi` — HTTP 框架
- `uvicorn[standard]` — ASGI 服务器
- `sse-starlette` — SSE 支持

**Node 端（UI）：**
- `react`, `react-dom` — UI 框架
- `vite` — 构建工具
- `tailwindcss` — 样式

---

## 4. API 详细规格

### 4.1 GET /health

**响应：**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": "2026-04-23T13:00:00Z"
}
```

### 4.2 GET /jobs

**响应：**
```json
{
  "jobs": [
    {
      "id": "abc123",
      "profile": "rl_controller",
      "status": "running",
      "current_phase": "harness",
      "created_at": "2026-04-23T12:00:00Z",
      "updated_at": "2026-04-23T13:00:00Z"
    }
  ]
}
```

### 4.3 GET /jobs/{id}

**响应：**
```json
{
  "id": "abc123",
  "profile": "rl_controller",
  "status": "running",
  "current_phase": "harness",
  "phases": {
    "curriculum": {"status": "completed", "output": {...}},
    "harness": {"status": "running", "output": null},
    "memory": {"status": "pending", "output": null},
    "review": {"status": "pending", "output": null}
  },
  "created_at": "2026-04-23T12:00:00Z",
  "updated_at": "2026-04-23T13:00:00Z"
}
```

### 4.4 POST /jobs

**请求体：**
```json
{
  "profile": "rl_controller",
  "config": {
    "max_iterations": 100,
    "timeout": 3600
  }
}
```

**响应：** 返回 201 Created + job 详情

### 4.5 GET /jobs/{id}/stream (SSE)

**事件格式：**
```
event: phase_change
data: {"phase": "harness", "status": "running"}

event: output
data: {"phase": "harness", "output": {...}}

event: complete
data: {"phase": "review", "status": "completed"}
```

---

## 5. 验收标准

### 5.1 Gateway API

- [ ] `GET /health` 返回 200 和健康状态
- [ ] `GET /jobs` 返回所有 checkpoint 列表
- [ ] `GET /jobs/{id}` 返回任务详情
- [ ] `POST /jobs` 能创建新任务
- [ ] `POST /jobs/{id}/resume` 能恢复 checkpoint
- [ ] `GET /jobs/{id}/stream` 能接收 SSE 事件
- [ ] OpenAPI 文档在 `/docs` 可访问

### 5.2 Operator UI

- [ ] Jobs 列表页面正常显示
- [ ] 能查看任务详情
- [ ] 能创建新任务
- [ ] 实时进度更新正常

### 5.3 部署

- [ ] `python -m runtimes.gateway` 能启动服务
- [ ] `python main.py --gateway` 能启动服务
- [ ] 端口 8765 可访问
- [ ] 前端静态文件正确加载

---

## 6. 边界与约束

1. **单进程部署**：Gateway 和 CLI 共享同一进程，避免状态同步问题
2. **本地优先**：目标用户是本地工具场景，不考虑多实例部署
3. **SSE 而非 WebSocket**：简化实现，满足实时需求
4. **静态前端**：UI 打包为静态文件由 Gateway 服务，减少复杂度

---

*规格版本：0.1.0 | 最后更新：2026-04-23*