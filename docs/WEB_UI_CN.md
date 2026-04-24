# Web UI 使用指南

Operator UI 是 Curriculum-Forge 的图形化管理界面，支持 Job 管理、插件配置、审计日志、Profile 管理、任务对比等功能。

---

## 1. 访问 UI

启动 Gateway 后，打开浏览器访问：

```
http://localhost:8765/
```

或直接访问 UI 独立端口（若已配置）：

```
http://localhost:5173/
```

### 前端源码

```
ui/operator-ui/src/App.tsx     # 主组件
ui/operator-ui/src/api.ts      # API 调用封装
ui/operator-ui/src/StatsCard.tsx  # 统计卡片
```

---

## 2. 界面布局

UI 采用顶部 Tab 导航结构，共 5 个标签页：

```
┌─────────────────────────────────────────────────────────────┐
│  Jobs | Plugins | Audit | Config | Compare                 │
├─────────────────────────────────────────────────────────────┤
│  [内容区]                                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Jobs Tab — 任务管理

### 3.1 顶部统计卡片

页面顶部显示 4 个统计概览卡片，**自动实时刷新**（每分钟 + 每次 SSE 事件触发）：

| 卡片 | 说明 | 示例 |
|------|------|------|
| **Total Jobs** | 历史累计任务数 | 42 |
| **Success Rate** | 成功任务占比 | 85.7% |
| **Avg Duration** | 平均运行时长 | 12m 34s |
| **Jobs / Hour** | 近 24h 每小时平均任务数 | 1.7 |

每个卡片下方有 **Sparkline 趋势图**（纯 SVG 折线图），展示近 24 小时趋势。

### 3.2 创建新 Job

页面底部「Create Job」表单：

| 字段 | 说明 |
|------|------|
| **Profile** | 下拉选择：`rl_controller` / `pure_harness` / `progressive_disclosure` |
| **Topic** | 训练主题（可覆盖 Profile 默认值） |
| **Max Iterations** | 最大迭代次数 |
| **Pass Threshold** | 通过阈值（0.0–1.0） |
| **Difficulty** | 难度：beginner / intermediate / advanced |

填写后点击 **Create**，Gateway 返回 `job_id`，Job 立即进入执行队列。

> **提示**：`config_overrides` 会与 Profile defaults 合并，表单字段即 API 中的 `config_overrides` 参数。

### 3.3 任务列表

Job 列表展示所有历史任务，按创建时间倒序：

| 列 | 说明 |
|----|------|
| **ID** | Job 唯一标识（`run_xxx`） |
| **Profile** | 使用的 Profile |
| **Topic** | 任务主题 |
| **State** | 状态：PENDING / RUNNING / COMPLETED / FAILED / ABORTED |
| **Created** | 创建时间，相对时间展示（"5m ago"） |
| **Actions** | 查看详情 / 中止 / Resume / 对比 |

**SSE 实时更新**：无需刷新页面，任务状态变化（如 PENDING→RUNNING→COMPLETED）自动推送更新。

### 3.4 Job 详情 & Metrics

点击任务行展开详情，或点击 **Metrics** 按钮查看详细指标：

#### 概览指标卡

- **Total Duration**：总运行时长
- **Providers OK**：成功执行的 Provider 数（如 4/4）
- **Retries**：重试次数
- **Tokens Used**：Token 总消耗

#### Phase Duration Breakdown

阶段耗时表格，含比例进度条：

| Phase | Duration | % |
|-------|----------|---|
| curriculum | 1m 23s | ████████████░░░░ 45% |
| harness | 45s | ██████░░░░░░░░░░░ 23% |
| memory | 32s | ████░░░░░░░░░░░░ 16% |
| review | 24s | ███░░░░░░░░░░░░░ 12% |

#### Token Usage 详情

| 类型 | Count |
|------|-------|
| **Prompt Tokens** | 12,450 |
| **Completion Tokens** | 3,820 |
| **Total** | 16,270 |

#### Error

如 Job 失败，显示错误信息。

---

## 4. Plugins Tab — 插件管理

### 4.1 插件列表

展示所有已注册的插件：

| 列 | 说明 |
|----|------|
| **Name** | 插件名（如 `reward-logger`） |
| **Enabled** | 启用状态开关（Toggle） |
| **Description** | 插件描述 |
| **Hooks** | 插件挂载的钩子点列表 |

### 4.2 启用/禁用插件

点击插件行右侧 Toggle 开关，即时生效。Gateway 将 `enabled` 状态写入内存，无需重启。

### 4.3 配置插件

点击插件行的 **Config** 按钮，弹出配置面板，显示当前 `plugin.config` JSON，可编辑并保存。

### 4.4 内置插件

Curriculum-Forge 自带 3 个插件：

| 插件 | 说明 | 钩子 |
|------|------|------|
| `reward-logger` | 记录 Reward 值到文件 | harness_complete, review_complete |
| `experiment-filter` | 按实验标签过滤记录 | job_created, job_finished |
| `stage-tracker` | 追踪阶段状态变化 | job_created, phase_complete, job_finished |

---

## 5. Audit Tab — 审计日志

### 5.1 日志列表

展示最近 200 条审计事件，按时间倒序：

| 列 | 说明 |
|----|------|
| **Timestamp** | 精确时间（ISO 8601） |
| **Category** | 分类：job / plugin / system 等 |
| **Event** | 事件类型（如 `job_created`） |
| **Actor** | 操作者（user / system / plugin_name） |
| **Target** | 操作对象（如 job_id） |
| **Details** | 展开查看 metadata |

**metadata** 字段包含事件详细上下文（不同事件类型内容不同）。

### 5.2 统计概览

页面顶部统计：

- **Total Events**：总事件数
- **Unique Jobs**：涉及的唯一 Job 数
- **Unique Users**：活跃用户数
- **Last Event**：最近事件时间

### 5.3 过滤

日志支持按 `category` 和 `actor` 过滤。可在下拉菜单中选择。

---

## 6. Config Tab — Profile 管理

### 6.1 Profile 列表

展示所有已注册的 Profile（含系统内置和自定义）：

| 列 | 说明 |
|----|------|
| **Name** | Profile 名 |
| **File** | JSON 文件名 |
| **Description** | 描述 |
| **Valid** | 状态：✅ / ❌ |

### 6.2 查看 Profile Schema

点击 **Schema** 查看完整 Profile JSON 结构说明。

### 6.3 验证 Profile

点击 **Validate** 按钮，Gateway 调用 `profile_validator.validate_profile_file()` 并返回错误列表。

### 6.4 查看单个 Profile

点击 Profile 行，查看完整 JSON 内容（包含 defaults / providers / metadata）。

---

## 7. Compare Tab — 任务对比

### 7.1 选择要对比的 Job

在 Jobs Tab 列表中勾选 2–10 个 Job，点击底部 **Compare** 按钮跳转 Compare Tab。

### 7.2 汇总统计卡

顶部 4 个汇总卡片：

| 卡片 | 说明 |
|------|------|
| **Jobs Count** | 对比的任务数 |
| **Avg Duration** | 平均运行时长 |
| **Providers OK** | 平均 Provider 成功率 |
| **Total Retries** | 所有 Job 重试次数之和 |

### 7.3 对比表格

按 Job 分列对比以下指标：

| 列 | 说明 |
|----|------|
| **Job ID** | 任务 ID |
| **Profile** | Profile 名 |
| **Duration** | 运行时长 |
| **Providers OK** | Provider 成功数 |
| **Retries** | 重试次数 |
| **Tokens** | Token 总消耗 |
| **State** | 最终状态（COMPLETED / FAILED 等） |

---

## 8. 实时更新机制

UI 所有数据均通过 **SSE（Server-Sent Events）** 实时推送：

| SSE 流 | 内容 |
|--------|------|
| `/jobs/{id}/stream` | 单个 Job 的状态变化和日志行 |
| `/coordinator/events` | 全局 Coordinator 事件（所有 Job 状态变化） |

**自动重连**：浏览器端 SSE 支持自动重连，断线后自动恢复。

**刷新触发**：收到 SSE 事件时自动刷新相关数据，无需手动刷新页面。

---

## 9. 快捷操作

| 操作 | 说明 |
|------|------|
| **中止 Job** | Jobs Tab 行右侧 Abort 按钮（仅 RUNNING 状态有效） |
| **Resume Job** | Jobs Tab 行右侧 Resume 按钮（仅 FAILED/PENDING 状态有效） |
| **查看 Metrics** | 点击 Job 行 Metrics 按钮 |
| **对比 Job** | 勾选多个 Job → Compare |
| **刷新列表** | 点击 Jobs Tab 标题区域 |
| **展开详情** | 点击 Job 行展开内联详情 |

---

## 10. 常见问题

| 问题 | 解决 |
|------|------|
| UI 加载空白 | 确认 Gateway 已启动：`python main.py --gateway` |
| SSE 不更新 | 检查浏览器控制台是否有 CORS 错误；确认端口 8765 可访问 |
| Job 状态不变 | 查看 Metrics 页 error 字段；检查 Coordinator 日志 |
| Plugin Toggle 无效 | 确认插件代码无语法错误；查看 Audit Tab 日志 |
| 创建 Job 失败 | 检查 Profile 是否有效；查看 Config Tab Validate |
| Stats 数据为空 | 确认 CheckpointStore 有历史记录；新 Job 运行后才有数据 |
| Sparkline 全零 | 等待至少 1 小时数据积累；查看 /stats/timeseries 端点返回 |
