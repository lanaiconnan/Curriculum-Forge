# Plugin 开发指南

本文档介绍如何为 Curriculum Forge 开发自定义插件，扩展系统功能而无需修改核心代码。

---

## 目录

1. [架构概览](#架构概览)
2. [快速开始](#快速开始)
3. [Hook 参考](#hook-参考)
4. [API 详解](#api-详解)
5. [完整示例](#完整示例)
6. [最佳实践](#最佳实践)
7. [故障排查](#故障排查)

---

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                     Curriculum Forge Core                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────┐ │
│  │ Environment │  │ Experiment  │  │    Reward   │  │  Stage  │ │
│  │   Service   │  │   Service   │  │   Service   │  │ Service │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └────┬────┘ │
│         │                │                │              │      │
│         └────────────────┴────────────────┴──────────────┘      │
│                                    │                            │
│                         dispatch_hook()                         │
│                                    │                            │
│  ┌─────────────────────────────────▼─────────────────────────┐  │
│  │                    PluginManager                           │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │  │
│  │  │  Plugin A   │  │  Plugin B   │  │  Plugin C   │       │  │
│  │  │ (priority)  │  │ (priority)  │  │ (priority)  │       │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘       │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   plugins/       │
                    │  ├── my-plugin/  │
                    │  │   ├── PLUGIN.md│
                    │  │   └── plugin.py│
                    │  └── ...         │
                    └─────────────────┘
```

### 核心概念

| 组件 | 说明 |
|------|------|
| **Plugin** | 插件基类，所有插件必须继承 |
| **PluginMeta** | 插件元数据（名称、版本、Hook 列表、优先级） |
| **PluginContext** | Hook 上下文对象，包含事件数据和存储 |
| **PluginManager** | 插件管理器，负责注册、分发、生命周期管理 |
| **PluginHook** | 标准 Hook 枚举，定义可拦截的生命周期点 |

---

## 快速开始

### 1. 创建插件目录

```bash
mkdir -p plugins/my-first-plugin
touch plugins/my-first-plugin/PLUGIN.md
touch plugins/my-first-plugin/plugin.py
```

### 2. 编写 PLUGIN.md（元数据）

```yaml
---
name: my-first-plugin
version: 1.0.0
description: 我的第一个插件
hooks:
  - exp:after_run
priority: 100
---

# my-first-plugin

这里是插件的详细说明文档。
```

### 3. 编写 plugin.py（实现）

```python
from services.plugin_system import Plugin, PluginMeta, PluginContext
from typing import Optional

class MyFirstPlugin(Plugin):
    """我的第一个插件"""
    
    meta = PluginMeta(
        name="my-first-plugin",
        version="1.0.0",
        description="我的第一个插件",
        hooks=["exp:after_run"],
        priority=100,
    )
    
    def initialize(self) -> None:
        """插件初始化"""
        print(f"{self.meta.name} 已初始化")
        self._initialized = True
    
    def cleanup(self) -> None:
        """插件清理"""
        print(f"{self.meta.name} 已清理")
        self._initialized = False
    
    def on_hook(self, ctx: PluginContext) -> Optional[PluginContext]:
        """处理 Hook 事件"""
        if ctx.hook_name == "exp:after_run":
            exp_id = ctx.get('exp_id', 'unknown')
            print(f"实验完成: {exp_id}")
        return ctx
```

### 4. 注册插件

```python
from services.plugin_system import PluginManager
from services.plugin_loader import load_plugins_into_manager

# 创建管理器
manager = PluginManager()

# 方式1：手动注册
from plugins.my_first_plugin.plugin import MyFirstPlugin
manager.register(MyFirstPlugin())

# 方式2：自动发现
load_plugins_into_manager(manager, plugins_dir="plugins")

# 初始化所有插件
manager.initialize_all()
```

### 5. 触发 Hook

```python
# 在核心代码中触发 Hook
ctx = manager.dispatch("exp:after_run", {
    "exp_id": "exp_001",
    "reward": 3.5,
    "duration": 45.2
})

# 检查插件是否修改了上下文
if ctx.get('modified'):
    print("数据已被插件修改")
```

---

## Hook 参考

### 环境生命周期

| Hook | 触发时机 | 可用数据 |
|------|----------|----------|
| `env:before_generate` | 生成环境前 | `difficulty`, `topic` |
| `env:after_generate` | 生成环境后 | `env`, `tasks`, `difficulty` |

### 实验生命周期

| Hook | 触发时机 | 可用数据 |
|------|----------|----------|
| `exp:before_run` | 运行实验前 | `env`, `config` |
| `exp:after_run` | 运行实验后 | `exp_id`, `reward`, `duration`, `keep_rate` |

### RL 训练生命周期

| Hook | 触发时机 | 可用数据 |
|------|----------|----------|
| `rl:before_train` | 开始训练前 | `model`, `dataset`, `epochs` |
| `rl:after_train` | 训练完成后 | `model`, `metrics`, `loss` |

### 奖励计算生命周期

| Hook | 触发时机 | 可用数据 |
|------|----------|----------|
| `reward:before_calc` | 计算奖励前 | `response`, `reference` |
| `reward:after_calc` | 计算奖励后 | `reward`, `rformat`, `rname`, `rparam`, `rvalue` |

### 结果保存生命周期

| Hook | 触发时机 | 可用数据 |
|------|----------|----------|
| `result:before_save` | 保存结果前 | `result`, `metadata` |
| `result:after_save` | 保存结果后 | `result_id`, `path` |

### 阶段转换生命周期

| Hook | 触发时机 | 可用数据 |
|------|----------|----------|
| `stage:before_transition` | 阶段转换前 | `from_stage`, `to_stage`, `keep_rate` |
| `stage:after_transition` | 阶段转换后 | `from_stage`, `to_stage`, `is_regression` |

---

## API 详解

### Plugin 基类

```python
class MyPlugin(Plugin):
    """插件必须继承 Plugin 基类"""
    
    # 必须：定义插件元数据
    meta = PluginMeta(
        name="my-plugin",           # 唯一标识符
        version="1.0.0",            # 版本号
        description="描述",          # 描述
        hooks=["exp:after_run"],    # 监听的 Hook 列表
        priority=100,               # 优先级（越小越先执行）
        depends_on=[],              # 依赖的其他插件
    )
    
    def __init__(self):
        super().__init__()
        # 自定义初始化代码
    
    def initialize(self) -> None:
        """
        插件初始化。
        在 register() 后调用，用于分配资源、建立连接等。
        """
        pass
    
    def cleanup(self) -> None:
        """
        插件清理。
        在 unregister() 或程序退出时调用，用于释放资源。
        """
        pass
    
    def on_hook(self, ctx: PluginContext) -> Optional[PluginContext]:
        """
        处理 Hook 事件。
        
        Args:
            ctx: 包含事件数据的上下文
            
        Returns:
            - 返回 ctx：继续传播到下一个插件
            - 返回 None：停止传播
        """
        return ctx
```

### PluginContext 上下文

```python
# 读取数据
exp_id = ctx.get('exp_id', 'unknown')      # 获取数据，提供默认值
reward = ctx.get('reward')                  # 获取数据，可能返回 None

# 写入数据
ctx.set('modified', True)                   # 设置数据，其他插件可见
ctx.set('my_plugin_data', {...})            # 插件间共享数据

# 停止传播
if should_stop:
    ctx.stop_propagation()                  # 阻止后续插件执行

# 检查状态
if ctx.is_stopped:                          # 检查是否已被停止
    return ctx

# 插件专属存储（持久化到当前请求）
storage = ctx.get_plugin_storage('my-plugin')
storage['counter'] = storage.get('counter', 0) + 1
```

### PluginManager 管理器

```python
# 创建管理器
manager = PluginManager()

# 注册插件
manager.register(MyPlugin())

# 注销插件
manager.unregister("my-plugin")

# 分发 Hook
ctx = manager.dispatch("exp:after_run", {"exp_id": "001"})

# 初始化/清理所有插件
manager.initialize_all()
manager.cleanup_all()

# 查询插件
plugin = manager.get_plugin("my-plugin")
exists = manager.has_plugin("my-plugin")
all_plugins = manager.list_plugins()

# 获取统计
stats = {
    "total": len(manager.list_plugins()),
    "initialized": sum(1 for p in manager.list_plugins() if p['initialized'])
}
```

---

## 完整示例

### 示例 1：奖励日志插件

```python
"""reward-logger/plugin.py"""
import os
import logging
from datetime import datetime
from typing import Optional

from services.plugin_system import Plugin, PluginMeta, PluginContext

logger = logging.getLogger(__name__)


class RewardLoggerPlugin(Plugin):
    """记录每次实验的奖励分解"""
    
    meta = PluginMeta(
        name="reward-logger",
        version="1.0.0",
        description="Logs reward breakdown after each experiment",
        hooks=["reward:after_calc", "exp:after_run"],
        priority=100,
    )
    
    def __init__(self):
        super().__init__()
        self._log_path: Optional[str] = None
        self._log_count = 0
    
    def initialize(self) -> None:
        """初始化日志文件路径"""
        workspace = os.environ.get('CURRICULUM_FORGE_WORKSPACE', '.')
        self._log_path = os.path.join(workspace, 'rewards.log')
        self._initialized = True
        logger.info(f"RewardLoggerPlugin: logging to {self._log_path}")
    
    def cleanup(self) -> None:
        self._initialized = False
    
    def on_hook(self, ctx: PluginContext) -> Optional[PluginContext]:
        """处理 Hook 事件"""
        if ctx.hook_name == "reward:after_calc":
            self._log_reward(ctx)
        elif ctx.hook_name == "exp:after_run":
            self._log_experiment(ctx)
        return ctx
    
    def _log_reward(self, ctx: PluginContext) -> None:
        """记录奖励分解"""
        reward = ctx.get('reward', {})
        exp_id = ctx.get('exp_id', 'unknown')
        
        line = (
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
            f"{exp_id} | "
            f"rformat={reward.get('rformat', 0):.1f} "
            f"rname={reward.get('rname', 0):.1f} | "
            f"rfinal={reward.get('rfinal', 0):.2f}\n"
        )
        
        self._write(line)
        self._log_count += 1
    
    def _log_experiment(self, ctx: PluginContext) -> None:
        """记录实验摘要"""
        exp_id = ctx.get('exp_id', 'unknown')
        keep_rate = ctx.get('keep_rate', 0.0)
        
        line = (
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
            f"SUMMARY {exp_id} | keep_rate={keep_rate:.1%}\n"
        )
        
        self._write(line)
    
    def _write(self, line: str) -> None:
        """写入日志文件"""
        if self._log_path:
            with open(self._log_path, 'a') as f:
                f.write(line)
        else:
            logger.info(line.strip())
    
    @property
    def log_count(self) -> int:
        return self._log_count
```

### 示例 2：实验过滤器插件

```python
"""experiment-filter/plugin.py"""
import logging
from typing import Optional

from services.plugin_system import Plugin, PluginMeta, PluginContext

logger = logging.getLogger(__name__)


class ExperimentFilterPlugin(Plugin):
    """过滤低质量实验"""
    
    meta = PluginMeta(
        name="experiment-filter",
        version="1.0.0",
        description="Filters low-quality experiments",
        hooks=["exp:before_run", "result:before_save"],
        priority=10,  # 高优先级，先执行
    )
    
    def __init__(self, min_reward: float = -2.0, max_duration: float = 60.0):
        super().__init__()
        self.min_reward = min_reward
        self.max_duration = max_duration
        self._filtered_count = 0
        self._passed_count = 0
    
    def initialize(self) -> None:
        self._initialized = True
        logger.info(f"Filter: min_reward={self.min_reward}")
    
    def on_hook(self, ctx: PluginContext) -> Optional[PluginContext]:
        if ctx.hook_name == "exp:before_run":
            return self._before_run(ctx)
        elif ctx.hook_name == "result:before_save":
            return self._before_save(ctx)
        return ctx
    
    def _before_run(self, ctx: PluginContext) -> Optional[PluginContext]:
        """运行前验证"""
        env = ctx.get('env')
        
        # 检查难度
        difficulty = getattr(env, 'difficulty', None)
        if difficulty is not None and not (0.0 <= difficulty <= 1.0):
            ctx.set('skip', True)
            ctx.set('skip_reason', f"invalid difficulty: {difficulty}")
            self._filtered_count += 1
            return ctx
        
        self._passed_count += 1
        return ctx
    
    def _before_save(self, ctx: PluginContext) -> Optional[PluginContext]:
        """保存前过滤"""
        reward = ctx.get('reward', 0.0)
        duration = ctx.get('duration', 0.0)
        
        if reward < self.min_reward:
            ctx.set('filtered', True)
            ctx.set('filter_reason', f"reward {reward} below threshold")
            self._filtered_count += 1
            return ctx
        
        if duration > self.max_duration:
            ctx.set('filtered', True)
            ctx.set('filter_reason', f"duration {duration}s exceeds max")
            self._filtered_count += 1
            return ctx
        
        self._passed_count += 1
        return ctx
    
    def get_stats(self):
        return {
            "filtered": self._filtered_count,
            "passed": self._passed_count,
            "filter_rate": self._filtered_count / (self._filtered_count + self._passed_count) if (self._filtered_count + self._passed_count) > 0 else 0,
        }
```

### 示例 3：阶段追踪插件

```python
"""stage-tracker/plugin.py"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from services.plugin_system import Plugin, PluginMeta, PluginContext

logger = logging.getLogger(__name__)

STAGE_ORDER = {"beginner": 0, "intermediate": 1, "advanced": 2}


class StageTrackerPlugin(Plugin):
    """追踪学习阶段转换"""
    
    meta = PluginMeta(
        name="stage-tracker",
        version="1.0.0",
        description="Tracks learning stage transitions",
        hooks=["stage:before_transition", "stage:after_transition"],
        priority=50,
    )
    
    def __init__(self):
        super().__init__()
        self._history: List[Dict[str, Any]] = []
        self._current_stage: Optional[str] = None
        self._regression_count = 0
    
    def initialize(self) -> None:
        self._initialized = True
    
    def on_hook(self, ctx: PluginContext) -> Optional[PluginContext]:
        if ctx.hook_name == "stage:before_transition":
            return self._before_transition(ctx)
        elif ctx.hook_name == "stage:after_transition":
            return self._after_transition(ctx)
        return ctx
    
    def _before_transition(self, ctx: PluginContext) -> Optional[PluginContext]:
        """转换前检测回退"""
        from_stage = ctx.get('from_stage')
        to_stage = ctx.get('to_stage')
        
        if not from_stage or not to_stage:
            return ctx
        
        from_order = STAGE_ORDER.get(from_stage, -1)
        to_order = STAGE_ORDER.get(to_stage, -1)
        
        # 检测回退
        if to_order < from_order:
            self._regression_count += 1
            logger.warning(f"REGRESSION: {from_stage} → {to_stage}")
            ctx.set('is_regression', True)
        
        return ctx
    
    def _after_transition(self, ctx: PluginContext) -> Optional[PluginContext]:
        """记录转换"""
        record = {
            "from": ctx.get('from_stage'),
            "to": ctx.get('to_stage'),
            "at": datetime.now().isoformat(),
            "is_regression": ctx.get('is_regression', False),
        }
        self._history.append(record)
        self._current_stage = ctx.get('to_stage')
        
        return ctx
    
    def get_summary(self) -> Dict[str, Any]:
        return {
            "total_transitions": len(self._history),
            "regressions": self._regression_count,
            "current_stage": self._current_stage,
            "history": self._history,
        }
```

---

## 最佳实践

### 1. 优先级设计

```python
# 高优先级（先执行）：过滤、验证类插件
meta = PluginMeta(priority=10)  # 先执行

# 中优先级（默认）：处理、转换类插件  
meta = PluginMeta(priority=50)  # 中间执行

# 低优先级（后执行）：记录、通知类插件
meta = PluginMeta(priority=100)  # 最后执行
```

### 2. 错误处理

```python
def on_hook(self, ctx: PluginContext) -> Optional[PluginContext]:
    try:
        # 插件逻辑
        result = self._process(ctx)
        ctx.set('result', result)
    except Exception as e:
        # 记录错误但不阻止其他插件
        logger.error(f"Plugin error: {e}")
        ctx.set('error', str(e))
    
    return ctx  # 始终返回 ctx，不阻断传播
```

### 3. 数据验证

```python
def on_hook(self, ctx: PluginContext) -> Optional[PluginContext]:
    # 验证必需数据
    exp_id = ctx.get('exp_id')
    if not exp_id:
        logger.warning("Missing exp_id in context")
        return ctx
    
    # 验证数据类型
    reward = ctx.get('reward', 0.0)
    if not isinstance(reward, (int, float)):
        logger.warning(f"Invalid reward type: {type(reward)}")
        return ctx
    
    # 处理逻辑
    ...
```

### 4. 资源管理

```python
def initialize(self) -> None:
    """延迟初始化，避免在构造函数中分配资源"""
    self._db_connection = create_connection()
    self._cache = {}
    self._initialized = True

def cleanup(self) -> None:
    """确保资源释放"""
    if hasattr(self, '_db_connection'):
        self._db_connection.close()
    self._cache.clear()
    self._initialized = False
```

### 5. 配置外部化

```python
def __init__(self):
    super().__init__()
    # 从环境变量读取配置
    self.min_reward = float(os.environ.get('PLUGIN_MIN_REWARD', '-2.0'))
    self.max_duration = float(os.environ.get('PLUGIN_MAX_DURATION', '60.0'))
```

---

## 故障排查

### 插件未加载

**现象：** 插件代码未执行

**排查：**
```bash
# 检查目录结构
ls -la plugins/my-plugin/
# 应有: PLUGIN.md, plugin.py

# 检查日志
tail -f logs/curriculum_forge.log | grep -i plugin

# 手动测试加载
python -c "
from services.plugin_loader import load_plugin_from_dir
result = load_plugin_from_dir('plugins/my-plugin')
print(f'Success: {result.success}')
print(f'Error: {result.error}')
"
```

### Hook 未触发

**现象：** `on_hook` 未被调用

**排查：**
```python
# 检查 meta.hooks 是否正确
print(self.meta.hooks)  # 应包含触发的 hook 名

# 检查插件是否已注册
print(manager.has_plugin('my-plugin'))

# 检查分发调用
ctx = manager.dispatch('exp:after_run', {'test': 'data'})
print(f'Context data: {ctx.data}')
```

### 数据未传递

**现象：** `ctx.get()` 返回 None

**排查：**
```python
# 检查数据是否在 dispatch 中传递
manager.dispatch('hook:name', {'key': 'value'})  # 正确
manager.dispatch('hook:name', key='value')       # 错误

# 检查键名拼写
ctx.get('exp_id')   # 正确
ctx.get('expID')    # 错误（大小写敏感）
```

### 优先级冲突

**现象：** 插件执行顺序不符合预期

**解决：**
```python
# 检查所有插件的优先级
for p in manager.list_plugins():
    print(f"{p['name']}: priority={p['priority']}")

# 调整优先级确保正确顺序
meta = PluginMeta(priority=5)   # 最高优先级
meta = PluginMeta(priority=200) # 最低优先级
```

---

## 参考

- [Plugin System 源码](../services/plugin_system.py)
- [Plugin Loader 源码](../services/plugin_loader.py)
- [示例插件](../plugins/)

---

*文档版本: 1.0*
*最后更新: 2026-04-24*
