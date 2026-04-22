# Curriculum-Forge Phase 1+3 升级规格说明

> 版本：v1.0 | 日期：2026-04-22 | 基于 MoonClaw Provider 架构

---

## 1. 背景与目标

### 1.1 为什么升级

MoonClaw 的 Provider 系统将任务执行边界清晰化：
- **TaskProvider** 定义"做什么"（任务规范）
- **TaskRuntime** 定义"怎么做"（执行引擎）
- **CheckpointRecord** 持久化执行状态，支持断点恢复

Curriculum-Forge 当前架构的问题：
- 任务直接在 `services/` 里硬编码，切换执行模式要改代码
- 训练状态在内存，进程重启丢失
- 无外部提案机制（External Proposal）

### 1.2 升级目标

| 目标 | 描述 |
|------|------|
| Provider 抽象层 | 将 RL 训练流程抽象为插拔式 Provider |
| Checkpoint 持久化 | JSON 文件持久化训练状态 |
| External Proposal | CLI 导入外部 `.proposal.json` 任务 |
| 角色运行时 | RoleRuntimeContract 定义任务角色 |

---

## 2. 架构设计

### 2.1 核心组件

```
┌─────────────────────────────────────────────────┐
│                  FORGE CLI (cli.py)             │
│            run / proposal / checkpoint           │
└─────────────────┬───────────────────────────────┘
                  │
      ┌───────────┴───────────┐
      │     TaskRuntime       │
      │  (forge/runtime.py)   │
      └───────┬───────────────┘
              │
    ┌─────────┼──────────┐
    │         │          │
  Provider  Provider  Provider  ← TaskProvider 接口
  (curriculum)(harness) (memory)  (review)
```

### 2.2 Provider 阶段（Phase 1）

对应 RL 训练 Pipeline 的 4 个阶段：

| Provider | 输入 | 输出 | 现有对应 |
|----------|------|------|----------|
| `CurriculumProvider` | topic, difficulty, goal | modules, lessons | `services/curriculum.py` |
| `HarnessProvider` | module, difficulty | test suite | `services/harness.py` |
| `MemoryProvider` | experience | buffer stats | `services/learner.py` |
| `ReviewProvider` | results, metrics | feedback, verdict | `services/trainer.py` |

### 2.3 Checkpoint 系统（Phase 3）

每个 Pipeline 运行产生 CheckpointRecord（JSON）：

```json
{
  "id": "run_20260422_143000",
  "created_at": "2026-04-22T14:30:00+08:00",
  "profile": "rl_controller",
  "phase": "running",
  "config": { ... },
  "state": { ... },
  "metrics": { ... },
  "finished_at": null
}
```

CheckpointStore（`runtimes/checkpoint_store.py`）管理：
- 列表/查询运行历史
- 恢复中断的 Pipeline
- 清理旧 Checkpoint

### 2.4 External Proposal

`proposal import <file>` CLI 命令：
1. 解析 `.proposal.json`
2. 验证 Schema
3. 创建 CheckpointRecord
4. 触发 Provider 链执行

提案类型：
- `curriculum_proposal` — 新课程定义
- `rerun_proposal` — 重新运行指定 Checkpoint

---

## 3. 文件结构

```
dual-agent-tool-rl/
├── SPEC.md                        ← 本规格说明
├── providers/                     ← Phase 1：Provider 抽象层
│   ├── __init__.py
│   ├── base.py                   # TaskProvider 基类 + Phase 枚举
│   ├── curriculum_provider.py     # 课程任务分解
│   ├── harness_provider.py        # 测试执行
│   ├── memory_provider.py         # 经验存储
│   └── review_provider.py         # 评审反馈
├── runtimes/                      ← Phase 3：执行引擎
│   ├── __init__.py
│   ├── checkpoint_store.py         # Checkpoint JSON 持久化
│   ├── adaptive_runtime.py         # 支持 WaitingForInput
│   └── proposal_cli.py            # External Proposal CLI
├── profiles/                      ← 任务配置（JSON）
│   ├── rl_controller.json         # 完整 RL 训练
│   ├── pure_harness.json          # 仅 Harness 测试
│   └── progressive_disclosure.json # 渐进式披露
├── roles/                         ← 角色定义
│   ├── __init__.py
│   └── role_runtime.py            # RoleRuntimeContract
└── (现有 services/ agent_a/ agent_b/ 全部保留，不修改)
```

---

## 4. API 设计

### 4.1 TaskProvider 接口

```python
class TaskPhase(Enum):
    CURRICULUM = "curriculum"
    HARNESS   = "harness"
    MEMORY    = "memory"
    REVIEW    = "review"

class TaskOutput(NamedTuple):
    phase: TaskPhase
    data: Dict[str, Any]
    metadata: Dict[str, Any]

class TaskProvider(ABC):
    @abstractmethod
    def phase(self) -> TaskPhase: ...

    @abstractmethod
    async def execute(self, config: Dict, runtime: 'TaskRuntime') -> TaskOutput: ...

    def can_handle(self, config: Dict) -> bool:
        """检查此 Provider 是否能处理此任务"""
        return True
```

### 4.2 CheckpointStore API

```python
class CheckpointStore:
    def save(self, record: CheckpointRecord) -> Path: ...
    def list(self, profile: Optional[str] = None) -> List[CheckpointRecord]: ...
    def load(self, run_id: str) -> Optional[CheckpointRecord]: ...
    def delete(self, run_id: str) -> bool: ...
    def latest(self, profile: Optional[str] = None) -> Optional[CheckpointRecord]: ...
```

### 4.3 CLI 命令

```
forge run [--profile <name>] [--resume <run_id>]
forge checkpoint list [--profile <name>]
forge checkpoint show <run_id>
forge checkpoint delete <run_id>
forge proposal import <file.json>
```

---

## 5. 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 不改动现有 services/ | 全部保留 | 最小侵入，新代码通过 Provider 调用现有模块 |
| JSON 存储 Checkpoint | 不用 SQLite | 无额外依赖，可直接查看/编辑 |
| Python asyncio | 异步执行 | 支持 WaitingForInput 等暂停状态 |
| profiles/ JSON 配置 | 非 YAML | 与 MoonClaw 的 `.moonclaw/jobs/{id}/` 一致 |

---

## 6. 不包含在本版本

- Web Dashboard（后续 Pipeline-003）
- 多 Provider 并行执行
- Provider 注册中心（Registry）
- Git-based Checkpoint（只存 JSON）

---

**状态**：✅ SPEC 锁定，进入 BUILD
