# Config 管理指南

Curriculum-Forge 采用多层配置合并机制，支持 Profile 文件、环境变量、API 参数三种配置来源。

---

## 1. 概览：4 层配置优先级

```
优先级从低到高：

  Service 层默认
  → Profile defaults
  → Profile runtime
  → 环境变量（CF_*）
  → API config_overrides（最高）
```

创建 Job 时，Gateway 调用 `merge_config(profile_data, api_overrides)` 将所有来源的配置合并，API 层参数覆盖一切。

---

## 2. Profile 文件

Profile 是 `profiles/*.json`，定义任务模板。

### 目录

```
dual-agent-tool-rl/
└── profiles/
    ├── rl_controller.json        # 完整 RL 训练 Pipeline
    ├── pure_harness.json         # 仅 Harness 测试
    └── progressive_disclosure.json
```

### Profile JSON 结构

```json
{
  "name": "rl_controller",          // 唯一标识，文件名需一致
  "description": "完整 RL 训练 Pipeline",  // 人类可读描述
  "version": "1.0",                 // 语义版本（必填）
  "providers": [                    // 启用的 Provider 列表
    "CurriculumProvider",
    "HarnessProvider",
    "MemoryProvider",
    "ReviewProvider"
  ],
  "defaults": {                      // 默认配置（见下节）
    "topic": "Python Coding Agent",
    "difficulty": "intermediate",
    "goal": "Build an autonomous code reviewer",
    "pass_threshold": 0.7,
    "max_iterations": 10
  },
  "metadata": {                      // 自定义元数据
    "created": "2026-04-22",
    "phase": "1+3"
  }
}
```

### defaults 可用字段

| 字段 | 类型 | 说明 | 默认值 |
|------|------|------|--------|
| `topic` | str | 训练主题 | — |
| `difficulty` | str | 难度：beginner / intermediate / advanced | intermediate |
| `goal` | str | 目标描述 | — |
| `pass_threshold` | float | 通过阈值，0.0–1.0 | 0.65 |
| `max_iterations` | int | 最大迭代次数 | 5 |
| `disclosure_mode` | bool | 渐进式披露模式 | false |
| `wait_for_input` | bool | 等待人工输入 | false |
| `interactive` | bool | 交互式模式 | false |
| `waiting_behavior` | str | 等待时行为 | — |

### Provider 有效值

- `CurriculumProvider` — 课程编排 + 任务生成
- `HarnessProvider` — 工具调用测试
- `MemoryProvider` — 经验积累
- `ReviewProvider` — 评估与反馈

---

## 3. 内置 Profile 详解

### 3.1 rl_controller.json（推荐）

完整 RL 训练 Pipeline，4 Provider 全流程：

```json
{
  "name": "rl_controller",
  "description": "完整 RL 训练 Pipeline（4 Provider 全流程）",
  "version": "1.0",
  "providers": [
    "CurriculumProvider",
    "HarnessProvider",
    "MemoryProvider",
    "ReviewProvider"
  ],
  "defaults": {
    "topic": "Python Coding Agent",
    "difficulty": "intermediate",
    "goal": "Build an autonomous code reviewer",
    "pass_threshold": 0.7,
    "max_iterations": 10
  }
}
```

### 3.2 pure_harness.json

仅 Harness 测试阶段，用于快速验证：

```json
{
  "name": "pure_harness",
  "description": "仅 Harness 测试阶段（用于快速验证）",
  "version": "1.0",
  "providers": ["HarnessProvider"],
  "defaults": {
    "modules": [],
    "harness_cases": []
  }
}
```

### 3.3 progressive_disclosure.json

渐进式披露模式，适合教学场景。

---

## 4. 创建自定义 Profile

### 步骤 1：新建 JSON 文件

在 `profiles/` 目录创建，例如 `my_task.json`：

```json
{
  "name": "my_task",
  "description": "我的自定义任务",
  "version": "1.0",
  "providers": [
    "CurriculumProvider",
    "HarnessProvider"
  ],
  "defaults": {
    "topic": "REST API Design",
    "difficulty": "beginner",
    "goal": "Build a REST API with authentication",
    "pass_threshold": 0.75,
    "max_iterations": 5
  }
}
```

### 步骤 2：验证 Profile

**方式 A：API**

```bash
# 验证所有 Profile
curl http://localhost:8765/profiles/schema

# 获取单个 Profile
curl http://localhost:8765/profiles/my_task
```

**方式 B：Python 代码**

```python
from runtimes.profile_validator import validate_profile_file

is_valid, errors = validate_profile_file("profiles/my_task.json")
print(f"Valid: {is_valid}, Errors: {errors}")
```

**方式 C：自动发现**

```bash
curl http://localhost:8765/profiles/
# 返回所有 Profile 列表，包含 valid 状态
```

### 步骤 3：使用自定义 Profile

```bash
# 创建 Job
curl -X POST http://localhost:8765/jobs \
  -H "Content-Type: application/json" \
  -d '{"profile": "my_task"}'
```

---

## 5. 环境变量

环境变量优先级高于 Profile defaults，低于 API config_overrides。

| 环境变量 | 对应字段 | 类型 | 示例 |
|----------|----------|------|------|
| `CF_TOPIC` | topic | str | `CF_TOPIC=Web Security` |
| `CF_MAX_ITERATIONS` | max_iterations | int | `CF_MAX_ITERATIONS=20` |
| `CF_PASS_THRESHOLD` | pass_threshold | float | `CF_PASS_THRESHOLD=0.8` |
| `CF_DIFFICULTY` | difficulty | str | `CF_DIFFICULTY=advanced` |
| `CF_GOAL` | goal | str | `CF_GOAL=Build a firewall` |

### 示例：命令行设置

```bash
CF_TOPIC="Web Security" \
CF_MAX_ITERATIONS=20 \
CF_PASS_THRESHOLD=0.8 \
python main.py --gateway
```

### 生效优先级验证

```bash
# Profile defaults: max_iterations=10
# Env var: CF_MAX_ITERATIONS=20
# API config_overrides: {"max_iterations": 30}

# 结果：API 最高，最终 max_iterations=30
```

---

## 6. API config_overrides

创建 Job 时，通过 `config_overrides` 在请求体中传入，优先级最高。

### 创建 Job 时传入

```bash
curl -X POST http://localhost:8765/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "profile": "rl_controller",
    "config_overrides": {
      "topic": "Microservices",
      "max_iterations": 15,
      "pass_threshold": 0.8
    }
  }'
```

### 合并规则

`merge_config()` 按优先级依次覆盖：

```python
# 1. Service 层默认（最低）
result = {}

# 2. Profile defaults（若有）
result.update(profile["defaults"])

# 3. Profile runtime（若有，覆盖 defaults）
result.update(profile.get("runtime", {}))

# 4. 环境变量（若有，覆盖 runtime）
result = _apply_env_overrides(result)

# 5. API config_overrides（最高）
if api_overrides:
    result.update(api_overrides)
```

---

## 7. 运行时查看有效配置

### 方式 A：Profile API

```bash
# 查看某个 Profile 的解析后默认值
curl http://localhost:8765/profiles/my_task | python -m json.tool
```

### 方式 B：Job 创建响应

创建 Job 时，Gateway 返回的 `config` 字段即为合并后的最终配置：

```json
{
  "job_id": "run_xxx",
  "profile": "rl_controller",
  "config": {
    "topic": "Microservices",
    "difficulty": "intermediate",
    "max_iterations": 15,
    "pass_threshold": 0.8,
    "goal": "Build a REST API with authentication"
  }
}
```

### 方式 C：查看 Job Metrics

```bash
curl http://localhost:8765/jobs/{job_id}/metrics
```

---

## 8. Profile Schema 验证规则

| 规则 | 说明 |
|------|------|
| `name` 必填 | 唯一标识 |
| `version` 必填 | 语义版本 |
| `providers` 合法 | 仅限 4 种已知 Provider |
| `difficulty` 合法 | beginner / intermediate / advanced |
| `pass_threshold` 范围 | 必须在 0.0–1.0 |
| 类型检查 | 字段类型必须匹配 |

---

## 9. Service 层默认配置

以下为硬编码的 Service 默认值，可通过 Profile defaults 覆盖：

```python
SERVICE_DEFAULTS = {
    "environment": {
        "max_tasks_beginner": 2,
        "max_tasks_intermediate": 3,
        "max_tasks_advanced": 5,
    },
    "learner": {
        "max_iterations": 3,
        "llm_backend": "mock",
        "llm_model": "mock",
    },
}
```

---

## 10. Profile 调试技巧

### 查看所有 Profile 状态

```bash
curl http://localhost:8765/profiles/
```

返回示例：

```json
[
  {
    "name": "rl_controller",
    "file": "rl_controller.json",
    "description": "完整 RL 训练 Pipeline（4 Provider 全流程）",
    "valid": true,
    "errors": []
  },
  {
    "name": "my_task",
    "file": "my_task.json",
    "description": "我的自定义任务",
    "valid": false,
    "errors": ["Missing required field: 'version'"]
  }
]
```

### 快速测试配置合并

```python
from runtimes.profile_validator import merge_config
import json

with open("profiles/rl_controller.json") as f:
    profile = json.load(f)

# 无 API 覆盖
config = merge_config(profile)
print(config)

# 有 API 覆盖
config = merge_config(profile, {"max_iterations": 99})
print(config["max_iterations"])  # 99
```

---

## 11. 常见问题

| 问题 | 解决 |
|------|------|
| Profile 验证失败 | 检查必填字段 `name` 和 `version`，检查 `difficulty` 是否为有效枚举 |
| 配置优先级不生效 | 确认环境变量前缀是 `CF_`，API 参数是 `config_overrides` |
| Job 使用了错误的配置 | 查看创建响应中的 `config` 字段，确认合并结果 |
| Provider 类型无效 | `providers` 列表仅支持 4 种：`CurriculumProvider`/`HarnessProvider`/`MemoryProvider`/`ReviewProvider` |
| 环境变量不生效 | 确认在 `python main.py` 启动命令的同一 shell 会话中设置 |
