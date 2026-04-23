# Coordinator Async 改造规格

## 问题诊断

**services/coordinator.py** 的 `run_workflow()` 使用同步轮询：
```python
# line ~470-480
while len(completed) < len(workflow.tasks):
    if time.time() - start > timeout:
        break
    # ... find ready tasks ...
    if not tasks_to_execute:
        time.sleep(0.01)  # 👈 问题所在：忙等轮询
        continue
```

**后果：**
- CPU 占用高（虽然 0.01s 间隔）
- 无法与 async Gateway 正确集成
- 不适合高并发场景

## 改造目标

1. **async 版本**：`async def run_workflow_async(workflow, timeout) -> Dict`
2. **事件驱动**：用 `asyncio.Condition` 替代 `time.sleep(0.01)`
3. **向后兼容**：保留原 `run_workflow()` 作为 sync wrapper
4. **.Complete_task 唤醒**：`complete_task()` 调用时通知等待者

## 设计方案

### 方案 A（推荐）：asyncio.Condition + async/await

```python
class Coordinator:
    def __init__(self):
        # ... existing code ...
        self._condition = asyncio.Condition()
    
    async def run_workflow_async(self, workflow: Workflow, timeout: float = 3600.0) -> Dict[str, Any]:
        """Async version of run_workflow"""
        workflow.started_at = datetime.now()
        completed = set()
        start = time.time()
        
        async with self._condition:
            while len(completed) < len(workflow.tasks):
                if time.time() - start > timeout:
                    break
                
                ready = workflow.get_ready_tasks(completed)
                # 立即执行 ready tasks（在 condition lock 外）
                
                if not ready and not self._has_running_tasks(workflow):
                    # 等待 complete_task 通知
                    await asyncio.wait_for(
                        self._condition.wait(),
                        timeout=timeout - (time.time() - start)
                    )
                else:
                    for task in ready:
                        await self._execute_task_async(task, workflow)
                        completed.add(task.id)
        
        return self._aggregate_results(workflow)
    
    def complete_task(self, task_id: str, result=None, error=None):
        """Called when task completes - wakes up waiter"""
        # ... existing logic ...
        
        # 通知等待的协程
        async def _notify():
            async with self._condition:
                self._condition.notify_all()
        
        # 如果在 async context，schedule notification
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_notify())
        except RuntimeError:
            pass  # 没有 running loop，忽略
```

### 方案 B：asyncio.Event per task

每个 task 创建 `asyncio.Event()`，`complete_task()` 时 set event。

缺点：task 数量多时 event 对象多。

## 实施计划

### Task 1：添加 asyncio.Condition
- 在 `Coordinator.__init__` 添加 `self._condition = asyncio.Condition()`
- 添加 `self._running_tasks: Set[str]` 追踪正在执行的任务

### Task 2：实现 run_workflow_async
- 复制 `run_workflow` 逻辑
- 改为 `async def`
- 替换 `time.sleep(0.01)` 为 `await self._condition.wait()`

### Task 3：实现 _execute_task_async
- 将 `_execute_task` 改为 async 版本
- 支持 async handler

### Task 4：修改 complete_task
- 添加 `notify_all()` 唤醒等待者

### Task 5：向后兼容
- 原 `run_workflow()` 改为：
  ```python
  def run_workflow(self, workflow, timeout=3600.0):
      try:
          loop = asyncio.get_running_loop()
          return asyncio.ensure_future(self.run_workflow_async(workflow, timeout))
      except RuntimeError:
          return asyncio.run(self.run_workflow_async(workflow, timeout))
  ```

### Task 6：测试
- 添加 `tests/unit/test_coordinator_async.py`
- 测试 async workflow 执行
- 测试 complete_task 唤醒

## 边界约束

- 不修改 `Task`/`Workflow`/`Message` 等 dataclass
- 不修改 `AgentRegistry` / `MessageQueue`
- 保持 `register_agent` / `register_handler` API 不变
- Python 3.7 兼容（asyncio.run() 可用）

## 风险评估

| 风险 | 影响 | 缓解 |
|------|------|------|
| asyncio.run() 嵌套调用 | RuntimeError | 检测 running loop，用 ensure_future |
| complete_task 在非 async 上下文调用 | notify 失败 | 用 try/except 静默处理 |
| handler 是同步函数 | 阻塞 event loop | 用 run_in_executor 包装 |

## 验收标准

1. `run_workflow_async()` 能正确执行 workflow
2. 无 `time.sleep()` 轮询
3. `complete_task()` 能唤醒等待者
4. 原 `run_workflow()` 仍可工作
5. 全 suite 测试通过（无回归）
