# PLAN: Provider 真正执行

## 任务清单

按依赖顺序排列，共 8 个任务：

### Task 1 — `runtimes/pipeline_factory.py`（新建）
**目标：** 创建 `create_pipeline()` 函数，返回 `(PipelineConfig, ServiceContainer, CheckpointStore)`
**验收：**
- [ ] 函数存在且可导入
- [ ] 返回 3 项非 None
- [ ] 4 个 Provider 已注册（curriculum/harness/memory/review）
- [ ] ServiceContainer 已初始化（EnvironmentService + LearnerService）

### Task 2 — `runtimes/adaptive_runtime.py`（修改）
**目标：** 添加 `service_container` 属性到 `AdaptiveRuntime`
**验收：**
- [ ] `AdaptiveRuntime.__init__` 接受 `service_container` 参数
- [ ] `service_container` 属性可访问
- [ ] `PipelineConfig` 新增可选字段 `service_container`

### Task 3 — `providers/curriculum_provider.py`（修改）
**目标：** `execute()` 调用 `EnvironmentService.generate_environment()`
**验收：**
- [ ] 不再有硬编码 `_generate_modules()`
- [ ] 调用真实的 `EnvironmentService` 方法
- [ ] 返回的 `TaskOutput.data` 包含 `TrainingEnvironment.to_dict()`
- [ ] 单元测试通过

### Task 4 — `providers/harness_provider.py`（修改）
**目标：** `execute()` 调用 `HarnessRunner.run()`（通过 `LearnerService`）
**验收：**
- [ ] 不再有 `_run_mock()` 随机模拟
- [ ] 调用真实的 `HarnessRunner.run()` 或 `LearnerService.run_experiments()`
- [ ] 返回的 `TaskOutput.data` 包含 `HarnessReport.to_dict()`
- [ ] 单元测试通过

### Task 5 — `providers/memory_provider.py`（修改）
**目标：** `execute()` 调用经验 buffer 统计（来自 `LearnerService._results`）
**验收：**
- [ ] 不再是内存 dict 静态统计
- [ ] 从 `LearnerService` 获取真实经验记录
- [ ] `TaskOutput.data` 包含 `ProgressMetrics` 字段

### Task 6 — `providers/review_provider.py`（修改）
**目标：** `execute()` 调用评审逻辑（基于 keep_rate 阈值 0.3/0.6）
**验收：**
- [ ] 不再是静态阈值 `pass_threshold=0.7`
- [ ] 使用 `ProgressMetrics.keep_rate` 判断 stage
- [ ] verdict 逻辑与 `DualAgentCoordinator` 一致

### Task 7 — `runtimes/gateway.py`（修改）
**目标：** `_run_job_background()` 使用 `pipeline_factory.create_pipeline()`
**验收：**
- [ ] `PipelineConfig(profile_name=...)` 修复为 `profile=profile_name`
- [ ] `providers` 参数已传入
- [ ] `service_container` 已传入
- [ ] curl POST /jobs 不再 500

### Task 8 — `tests/unit/test_provider_execution.py`（新建）
**目标：** 单元测试覆盖 4 个 Provider 的真实服务调用
**验收：**
- [ ] CurriculumProvider 测试：验证调用 `generate_environment`
- [ ] HarnessProvider 测试：验证调用 HarnessRunner
- [ ] MemoryProvider 测试：验证从 buffer 读取
- [ ] ReviewProvider 测试：验证阈值判断
- [ ] `pytest tests/unit/test_provider_execution.py` 全通过

## 依赖关系

```
Task 1 (pipeline_factory) ← Task 2 (adaptive_runtime) ← Task 3-6 (providers) ← Task 7 (gateway) ← Task 8 (tests)
                              ↑
                              (Task 3-6 also depend on Task 1)
```

## 关键约束

- Python 3.7 兼容（无 AsyncMock，用 `run_in_executor`）
- 不修改 `services/` 内部实现
- 不修改 `providers/base.py` 接口
- 全量测试持续通过（772+ → 保持）