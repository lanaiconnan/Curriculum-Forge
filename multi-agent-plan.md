# Phase 2 Implementation Plan

## Item 1: Runtime ↔ Coordinator 桥接

### Step 1: adaptive_runtime.py
- 添加 `coordinator: Optional[Coordinator] = None` 属性
- `_execute_provider()` 完成后，若 coordinator 存在，发送 Message（type="provider_done"）
- 添加 `notify_agents(phase, output)` 方法

### Step 2: gateway.py
- 添加端点：
  - `GET /agents` — 列出注册的 agents
  - `GET /workflows` — 列出 workflows
  - `GET /workflows/{id}` — 查询单个 workflow 状态
  - `POST /workflows` — 创建并启动 workflow
- 添加 `setup_coordinator_routes(app, coordinator)` 函数
- 在 app startup 时初始化 Coordinator

### Step 3: pipeline_factory.py
- `create_pipeline()` 返回值增加 coordinator
- 新增 `create_coordinator()` 函数：创建 Coordinator、注册默认 Agent（teacher/learner/reviewer）、注册 handler（按 task_type 路由到 Provider）
- `run_job()` 传入 coordinator

### Step 4: 测试
- test_coordinator_bridge.py: 验证 Runtime ↔ Coordinator 通知
- test_gateway_agents.py: 验证新端点

## Item 2: RoleRuntime 接入真实 Provider

### Step 1: role_runtime.py
- RoleRuntime 基类添加 `provider: Optional[TaskProvider] = None`
- RoleRuntime 基类添加 `service_container: Any = None`
- TeacherRole.work() → 调用 CurriculumProvider.execute()
- LearnerRole.work() → 调用 HarnessProvider.execute() + MemoryProvider.execute()
- ReviewerRole.work() → 调用 ReviewProvider.execute()
- 每个角色实现 `to_agent_info() → AgentInfo` 方法

### Step 2: coordinator.py
- _try_assign_task(): 支持 RoleRuntime 路由
  - 如果 agent 有 RoleRuntime，直接调用 role.work()
  - 否则使用 handler
- 新增 `register_role(role: RoleRuntime)` 方法

### Step 3: 测试
- test_role_runtime.py: 验证角色调用 Provider
- test_coordinator_role.py: 验证角色路由

## Item 3: DAG Workflow

### Step 1: coordinator.py Workflow 改造
- Workflow: 移除 `stages` 线性列表，改为 `dag_nodes: Dict[str, DAGNode]`
- 新增 `DAGNode` dataclass: id, name, task_ids, dependencies (node-level)
- 保留 `add_task(task, stage=...)` 向后兼容（自动创建 DAGNode）
- 新增 `add_dag_node(node: DAGNode)` 方法
- `get_ready_tasks()` 改为基于 DAG 拓扑
- `run_workflow_async()` 支持同一 node 内并行

### Step 2: 测试
- test_dag_workflow.py: DAG 执行顺序、并行、依赖阻塞

## 执行顺序
1. Item 1 (Runtime ↔ Coordinator 桥接) — 最高 ROI，打通关键链路
2. Item 2 (RoleRuntime 接入 Provider) — 让角色真正干活
3. Item 3 (DAG Workflow) — 更高级的执行模型

## 预估时间
- Item 1: ~30 min
- Item 2: ~20 min  
- Item 3: ~20 min
