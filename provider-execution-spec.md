# SPEC: Provider 真正执行 — Phase 1 核心改进

## 背景

当前 `providers/` 的 `execute()` 方法返回硬编码 mock 数据，真正干活的是 `services/` 层（harness.py 680行、environment.py 600行、learner.py 700行、dual_agent.py 800行）。AdaptiveRuntime 调 Provider 链实际走不通，导致：

- Gateway POST /jobs 只创建 JSON，不触发真实执行
- Channel 收到消息不知道怎么处理（没有真实逻辑可调）
- 整个 Pipeline 是空转

## 目标

让 Provider 层真正调用 services/ 的核心逻辑，打通 Pipeline 执行闭环。

## 架构设计

### 关键原则
1. **不改动 services/ 原有实现**（它们已通过多年测试）
2. **Provider 作为 Facade 模式**：接收 TaskOutput → 调用 Service → 返回格式化结果
3. **AdaptiveRuntime 持有 ServiceContainer**：providers 通过 `runtime.service_container` 访问服务
4. **Async/Sync 适配**：services 同步，Provider async，用 `asyncio.get_event_loop().run_in_executor()` 包装

### 新增文件
- `runtimes/pipeline_factory.py` — 创建 `PipelineConfig` + 初始化 `ServiceContainer`

### 修改文件
- `runtimes/adaptive_runtime.py` — 添加 `service_container` 属性
- `providers/curriculum_provider.py` — 调用 `EnvironmentService`
- `providers/harness_provider.py` — 调用 `HarnessRunner`
- `providers/memory_provider.py` — 调用 `RLTrainerService` 经验 buffer
- `providers/review_provider.py` — 调用 `DualAgentCoordinator` 评审逻辑
- `runtimes/gateway.py` — 修复 `_run_job_background()` 使用 pipeline_factory

### 边界约束
- 不做 Phase 2/3 的改动（Agent Registry、DAG Workflow、ACP 等）
- 不改变 providers/base.py 的接口
- 不修改 services/ 的内部实现
- Python 3.7 兼容（AsyncMock 不可用，使用 `asyncio.coroutine` + `run_in_executor`）

## 各 Provider 改造详情

### 1. CurriculumProvider
**现状：** `_generate_modules()` 硬编码生成课程结构
**改造：** 调用 `EnvironmentService.generate_environment(progress, override_stage)`
**输入：** `topic`, `difficulty`, `stage_override`
**输出：** `TrainingEnvironment` → 转为 `TaskOutput.data`

### 2. HarnessProvider
**现状：** `_run_mock()` 随机 80% pass rate
**改造：** 调用 `HarnessRunner.run(query_engine, harness_cases)` + `HarnessScorer`
**输入：** `harness_cases`（来自 config）或从 curriculum 生成的 cases
**输出：** `HarnessReport` → 转为 `TaskOutput.data`

### 3. MemoryProvider
**现状：** 内存 dict，静态统计
**改造：** 调用 `RLTrainerService._experiences` buffer + `DualAgentCoordinator._experiment_records`
**输入：** 前序 Provider 的执行结果
**输出：** 经验存储统计 → `TaskOutput.data`

### 4. ReviewProvider
**现状：** 静态阈值 `pass_threshold=0.7`, `hit_threshold=0.5`
**改造：** 调用 `DualAgentCoordinator._handle_review_task()` 的评审逻辑（keep/revise/reject with 0.3/0.6 thresholds）
**输入：** `HarnessReport` + `ProgressMetrics`
**输出：** 评审 verdict → `TaskOutput.data`

## 技术路径

### ServiceContainer 访问方式
```python
# AdaptiveRuntime 持有 container
class AdaptiveRuntime:
    def __init__(self, config: PipelineConfig, service_container: ServiceContainer, ...):
        self.service_container = service_container

# Provider 通过 runtime 访问
class CurriculumProvider(TaskProvider):
    async def execute(self, config, runtime):
        env_service = runtime.service_container.get(EnvironmentService)
        env = await asyncio.get_event_loop().run_in_executor(
            None, env_service.generate_environment, progress, override
        )
```

### PipelineFactory
```python
# pipeline_factory.py
def create_pipeline(config_path: str) -> Tuple[PipelineConfig, ServiceContainer]:
    # 1. 加载 profile JSON
    # 2. 初始化 ServiceContainer（拓扑排序注册）
    # 3. 创建 PipelineConfig（providers 列表 + container）
    # 4. 返回 (config, container)
```

## 验收标准

1. ✅ `pytest tests/` 全通过（无新增失败）
2. ✅ 4 个 Provider 的 execute() 不再返回硬编码 mock
3. ✅ Gateway 的 `_run_job_background()` 能真实触发 Provider 链执行
4. ✅ 每个 Provider 有对应的单元测试（验证调用了正确的 service 方法）

## 实施顺序

1. `runtimes/pipeline_factory.py`（基础设施）
2. `runtimes/adaptive_runtime.py`（添加 service_container）
3. `providers/curriculum_provider.py`（最简单，先走通）
4. `providers/harness_provider.py`
5. `providers/memory_provider.py`
6. `providers/review_provider.py`
7. `runtimes/gateway.py`（修复 background runner）
8. 单元测试（每个 Provider 一个测试文件）

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| services/ 依赖复杂（ServiceProvider/ServiceContainer 链） | 先做 CurriculumProvider（依赖最简单的） |
| 同步/async 混用性能 | 使用 `run_in_executor`，不阻塞事件循环 |
| 破坏现有测试 | 先跑全量测试记录基线，过程中持续验证 |