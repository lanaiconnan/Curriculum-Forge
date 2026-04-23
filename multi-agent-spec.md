# Phase 2: Multi-Agent Collaboration Spec

## 目标

让 Curriculum-Forge 的多 Agent 真正协作。当前：
- Coordinator 有 AgentRegistry/MessageQueue/Workflow 但和 Runtime 层断开
- RoleRuntime 有 Teacher/Learner/Reviewer 三角色但 work() 是空壳
- AdaptiveRuntime 是线性 Provider 链，不涉及多 Agent
- Gateway 不知道 Coordinator 的存在

Phase 2 要打通这些，形成完整的 Agent 协作闭环。

## 核心改动（3 个 Item，ROI 排序）

### Item 1: Runtime ↔ Coordinator 桥接
**问题**: AdaptiveRuntime 只做线性 Provider 执行，Coordinator 孤立在外。
**方案**: 
- AdaptiveRuntime 新增 `coordinator` 属性（可选）
- 当 `coordinator` 存在时，Provider 执行结果通过 MessageQueue 通知其他 Agent
- Coordinator 的 Workflow 可以包含 Provider 任务（作为 Task handler）
- Gateway 暴露 Coordinator 状态（`/agents`, `/workflows`）

**新增/修改文件**:
- `runtimes/adaptive_runtime.py` — 添加 coordinator 属性 + 通知机制
- `runtimes/gateway.py` — 添加 `/agents`, `/workflows`, `/workflows/{id}` 端点
- `runtimes/pipeline_factory.py` — 创建 Coordinator 并注册 handlers

### Item 2: RoleRuntime 接入真实 Provider
**问题**: TeacherRole/LearnerRole/ReviewerRole 的 work() 返回硬编码数据。
**方案**:
- 每个角色持有对应 Provider 的引用
- work() 调用真实 Provider.execute()
- 角色结果转换为 RoleReport（供 Coordinator 的 MessageQueue 使用）
- Coordinator 的 AgentRole → RoleRuntime 映射

**修改文件**:
- `roles/role_runtime.py` — work() 接入 Provider + service_container
- `services/coordinator.py` — _try_assign_task 支持角色路由

### Item 3: DAG Workflow 替代线性 Stage
**问题**: Workflow 的 stages 是线性列表，不支持真正的并行+依赖。
**方案**:
- Workflow 支持 DAG 依赖（已有 Task.dependencies，但 stage 是线性的）
- 替换 stage 概念 → DAG 节点，按依赖拓扑排序并行执行
- Coordinator.run_workflow_async 已支持依赖检测，只需改 Workflow 数据模型
- 新增 `add_dag_node()` 方法替代 `add_task(task, stage=...)`

**修改文件**:
- `services/coordinator.py` — Workflow 改 DAG 模型
- `tests/unit/test_coordinator_async.py` — DAG 测试

## 不做的事（Phase 2 范围外）
- ACP 远程控制（Phase 3）
- Agent 自动发现/注册（硬编码注册即可）
- 跨进程 Agent（单进程内 asyncio 足够）
