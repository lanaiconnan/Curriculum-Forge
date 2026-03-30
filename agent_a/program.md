# Agent A 工作手册

> 基于 autoresearch 的 program.md 设计理念
> 版本：v1.0
> 更新：2026-03-29

---

## 1. 概述

本手册定义了 Agent A（环境生成器）在 Curriculum-Forge 中的职责和工作流程。

Agent A 的核心任务是：
- 分析实验进度（results.tsv）
- 判断当前学习阶段
- 生成合适的训练环境
- 配置动态奖励尺度

---

## 2. 实验流程

### 2.1 初始化

```
1. 读取 results.tsv
2. 分析历史实验数据
3. 计算 keep_rate
4. 判断学习阶段
5. 配置奖励尺度
```

### 2.2 分析进度

```python
def analyze_progress(results_file: str) -> AgentBProgress:
    """
    分析实验进度
    
    Returns:
        AgentBProgress:
            - total_experiments: 总实验数
            - keep_rate: 保留率
            - best_score: 最佳分数
            - weak_areas: 薄弱领域
    """
    # 读取 results.tsv
    # 统计保留/丢弃
    # 计算 keep_rate
    # 识别薄弱领域
```

### 2.3 生成环境

```python
def generate_environment(progress: AgentBProgress) -> TrainingEnvironment:
    """
    根据进度生成环境
    
    Args:
        progress: Agent B 的学习进度
    
    Returns:
        TrainingEnvironment: 训练环境
    """
    # 判断学习阶段
    stage = get_learning_stage(progress)
    
    # 获取动态奖励尺度
    reward_scale = get_dynamic_reward_scale(stage)
    
    # 生成任务
    tasks = generate_tasks(stage)
    
    # 创建环境
    env = TrainingEnvironment(
        id=f"env_{stage}_{timestamp}",
        name=f"{stage.capitalize()} Environment",
        difficulty=STAGE_DIFFICULTY[stage],
        tasks=tasks,
        reward_config={'scale': reward_scale},
    )
    
    return env
```

---

## 3. 学习阶段

### 3.1 三阶段定义

```python
STAGE_DIFFICULTY = {
    'beginner': 0.3,
    'intermediate': 0.5,
    'advanced': 0.7,
}

STAGE_REWARD_SCALE = {
    'beginner': 1.0,
    'intermediate': 0.7,
    'advanced': 0.5,
}

STAGE_KEEP_RATE = {
    'beginner': (0.0, 0.3),
    'intermediate': (0.3, 0.6),
    'advanced': (0.6, 1.0),
}
```

### 3.2 阶段转换

```
Beginner (keep_rate < 0.3)
  ↓
Intermediate (0.3 <= keep_rate < 0.6)
  ↓
Advanced (keep_rate >= 0.6)
```

### 3.3 任务生成

```python
def generate_tasks(stage: str) -> List[Dict]:
    """
    根据阶段生成任务
    
    Args:
        stage: 学习阶段
    
    Returns:
        List[Dict]: 任务列表
    """
    TASK_TEMPLATES = {
        'beginner': [
            {
                'id': 't1',
                'type': 'optimize',
                'description': 'Simple optimization task',
                'target': 'score > 100',
                'tools_required': ['git'],
            },
            {
                'id': 't2',
                'type': 'refactor',
                'description': 'Simple refactoring task',
                'target': 'score > 80',
                'tools_required': ['git'],
            },
        ],
        'intermediate': [
            # 3 个中等难度任务
        ],
        'advanced': [
            # 5 个复杂任务
        ],
    }
    
    return TASK_TEMPLATES[stage]
```

---

## 4. 约束

### 4.1 能做什么

```
✅ 分析 results.tsv
✅ 修改 agent_a/generator.py
✅ 调整环境配置
✅ 配置奖励尺度
✅ 生成新任务
✅ 调整难度
```

### 4.2 不能做什么

```
❌ 不能修改 Agent B 的代码
❌ 不能直接运行实验
❌ 不能修改 rl/trainer.py
❌ 不能改变评估指标
❌ 不能直接访问结果
```

### 4.3 边界条件

```
📊 数据限制：
   - 至少需要 3 个实验才能判断阶段
   - keep_rate 计算使用滑动窗口

🔄 循环限制：
   - 最多连续 3 次同一阶段判定
   - 防止过度停留在某一阶段
```

---

## 5. 指标

### 5.1 核心指标

| 指标 | 说明 | 目标 |
|------|------|------|
| `total_experiments` | 总实验数 | 越多越好 |
| `keep_rate` | 保留率 | >= 0.5 |
| `best_score` | 最佳分数 | 越高越好 |
| `weak_areas` | 薄弱领域 | 越少越好 |

### 5.2 阶段指标

```python
def get_learning_stage(progress: AgentBProgress) -> str:
    """
    根据进度判断学习阶段
    
    原则：
    - Beginner：keep_rate < 0.3
    - Intermediate：0.3 <= keep_rate < 0.6
    - Advanced：keep_rate >= 0.6
    """
    if progress.keep_rate < 0.3:
        return 'beginner'
    elif progress.keep_rate < 0.6:
        return 'intermediate'
    else:
        return 'advanced'
```

---

## 6. 输出格式

### 6.1 环境输出

```
=== Environment Generated ===
Stage: {learning_stage}
Difficulty: {difficulty}
Reward Scale: {reward_scale}
Tasks: {task_count}
Available Tools: {tools}

Task List:
  1. {task1_description}
  2. {task2_description}
  ...
```

### 6.2 进度分析输出

```
=== Progress Analysis ===
Total experiments: {total}
Keep rate: {keep_rate:.1%}
Best score: {best_score:.2f}
Weak areas: {weak_areas}

Current stage: {stage}
Next stage: {next_stage}
```

---

## 7. 与 Agent B 的协作

### 7.1 数据传递

```
Agent A                          Agent B
   |                                |
   |--- Environment ------------->|
   |                                |
   |                                |--- Results --->
   |<-- Feedback (keep_rate) ------|
```

### 7.2 反馈机制

```python
class Feedback:
    """
    Agent B 的反馈
    
    Agent A 根据反馈调整环境
    """
    keep_rate: float      # 保留率
    avg_reward: float     # 平均奖励
    stage_transitions: int  # 阶段转换次数
    weak_areas: List[str]   # 薄弱领域
```

### 7.3 调整策略

```python
def adjust_environment(env: TrainingEnvironment, feedback: Feedback):
    """
    根据反馈调整环境
    
    原则：
    - keep_rate 下降 → 降低难度
    - keep_rate 上升 → 提高难度
    - 特定领域薄弱 → 增加相关任务
    """
    if feedback.keep_rate < 0.3:
        # 降低难度
        env.difficulty *= 0.8
        env.reward_config['scale'] *= 1.2
    elif feedback.keep_rate > 0.6:
        # 提高难度
        env.difficulty *= 1.2
        env.reward_config['scale'] *= 0.8
    
    # 针对薄弱领域
    for weak_area in feedback.weak_areas:
        env.tasks.append(GENERATE_WEAK_TASK[weak_area])
    
    return env
```

---

## 8. 简洁性准则

> **"A small improvement that adds ugly complexity is not worth it."**
> — Karpathy

### 8.1 环境设计原则

```
✅ 值得做：
- 简单任务 + 清晰目标
- 减少不必要的约束
- 明确的任务描述

❌ 不值得做：
- 过度复杂的环境
- 模糊的成功标准
- 过多可选工具
```

### 8.2 代码质量

```
✅ 值得做：
- 清晰的函数命名
- 简洁的配置结构
- 易于理解的逻辑

❌ 不值得做：
- 过度抽象
- 复杂的继承关系
- 隐藏的副作用
```

---

## 9. 快速参考

### 9.1 核心函数

```python
# 分析进度
agent_a.analyze_progress(results_file)

# 获取学习阶段
agent_a.get_learning_stage(progress)

# 获取奖励尺度
agent_a.get_dynamic_reward_scale(stage)

# 生成环境
agent_a.generate_environment(progress)
```

### 9.2 配置

```python
STAGE_DIFFICULTY = {
    'beginner': 0.3,
    'intermediate': 0.5,
    'advanced': 0.7,
}

STAGE_REWARD_SCALE = {
    'beginner': 1.0,
    'intermediate': 0.7,
    'advanced': 0.5,
}

STAGE_KEEP_RATE = {
    'beginner': (0.0, 0.3),
    'intermediate': (0.3, 0.6),
    'advanced': (0.6, 1.0),
}
```

---

## 10. 变更日志

### v1.0 (2026-03-29)
- 初始版本
- 基于 autoresearch program.md 设计
- 定义 Agent A 的职责和工作流程
- 定义三阶段学习系统
- 定义与 Agent B 的协作机制
- 添加简洁性准则

---

**最后更新**：2026-03-29 10:22 GMT+8
