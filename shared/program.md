# Curriculum-Forge 共享工作手册

> 基于 autoresearch 的 program.md 设计理念
> 版本：v1.1
> 更新：2026-03-31

---

## 1. 概述

本文档定义了 Curriculum-Forge 系统中两个 Agent 的协作工作流程。

### 1.1 系统架构

```
Agent A (环境生成器)
    ↓
分析进度 → 生成环境 → 反馈
    ↓
Agent B (学习者)
    ↓
运行实验 → 收集结果 → 反馈
    ↓
RL 训练器
    ↓
计算奖励 → 更新模型
```

### 1.2 核心理念

**autoresearch 的启发**：
- AI 自主做科研
- 固定时间预算
- Git 版本控制
- 简洁性准则

**Curriculum-Forge 的实现**：
- 双 Agent 协作
- GRPO 强化学习
- 三阶段课程学习
- 细粒度奖励设计
- **Producer-Reviewer 协议**（新增 v1.1）

### 1.3 Producer-Reviewer 协议（v1.1 新增）

参考 Harness 的架构模式，新增 Producer-Reviewer 协作协议：

```
Agent A (Producer/Reviewer)  ←→  Agent B (Learner)
         ↓                              ↓
    生成任务 + 评审质量          执行任务 + 接收反馈
         ↓                              ↓
    Accept/Revise/Reject         迭代改进
         ↓
    GRPO 奖励计算
```

**核心组件**：
- `protocols/producer_reviewer/protocol.py` — 核心协议定义
- `protocols/producer_reviewer/producer.py` — 任务生成 + 渐进披露
- `protocols/producer_reviewer/reviewer.py` — 质量评审（LLM/Heuristic）
- `protocols/producer_reviewer/feedback_loop.py` — 反馈追踪 + 模式分析
- `protocols/integration.py` — 与现有 AgentA/B/GRPO 集成

### 1.4 Expert Pool 协议（v1.2 新增）

基于 Harness 的 Expert Pool 架构，动态选择最合适的训练专家：

```
FeedbackLoop/Analyst → LearnerState
         ↓
    ExpertSelector.score(experts)
         ↓
    Selected Expert → Specialized TrainingEnvironment
         ↓
    Producer-Reviewer Loop
```

**核心组件**：
- `protocols/expert_pool/pool.py` — 专家注册表
- `protocols/expert_pool/selector.py` — 动态选择算法
- `protocols/expert_pool/experts.py` — 6 种专业化专家
- `protocols/expert_pool/integration.py` — 与 FeedbackLoop/Producer-Reviewer 集成

**选择策略**：
| 策略 | 说明 |
|------|------|
| `weak_area_first` | 优先匹配学习者薄弱领域 |
| `performance_based` | 基于历史成功率 |
| `exploration` | 探索未使用的专家 |
| `hybrid` | 综合以上因素（默认）|

**6 种训练专家**：
| 专家 | 专注领域 | 适合阶段 |
|------|---------|---------|
| ToolMasteryExpert | 单工具熟练度 | Beginner |
| ErrorRecoveryExpert | 错误处理与恢复 | Intermediate |
| OptimizationExpert | 性能优化 | Advanced |
| MultiToolExpert | 多工具协作 | Intermediate |
| EdgeCaseExpert | 边界情况处理 | Advanced |
| CodeReviewExpert | 代码审查与质量 | Intermediate |

### 1.5 Progressive Disclosure 协议（v1.3 新增）

细粒度难度控制，突破固定 3 阶段限制：

```
PerformanceSignal (score, time, errors, tool_calls)
         ↓
DifficultyController.adjust()
         ↓
DifficultyDimensions (complexity, constraints, context, tools, scope)
         ↓
ContextDiscloser.compute_disclosure()
         ↓
TaskConfig (hints, examples, scaffold, constraints)
```

**核心组件**：
- `protocols/progressive_disclosure/controller.py` — 多维难度控制器
- `protocols/progressive_disclosure/disclosure.py` — 渐进式上下文披露
- `protocols/progressive_disclosure/task_config.py` — 任务配置构建器
- `protocols/progressive_disclosure/integration.py` — 与 ExpertPool 集成

**难度维度**：
| 维度 | 说明 |
|------|------|
| complexity | 任务复杂度 |
| constraints | 时间/工具约束强度 |
| context | 上下文丰富度（低 = 更多 hints） |
| tools | 工具使用要求 |
| scope | 任务范围/广度 |

**渐进披露规则**：
- 低 context_difficulty（0.2）→ 大量 hints + examples
- 高 context_difficulty（0.8）→ 最小上下文
- 根据 round_num 和 score 动态调整

---

## 2. Agent A 职责

### 2.1 任务

```
1. 分析实验进度（results.tsv）
2. 计算 keep_rate
3. 判断学习阶段
4. 生成合适的训练环境
5. 配置奖励尺度
```

### 2.2 Producer-Reviewer 模式（扩展任务）

当启用 Producer-Reviewer 协议时，Agent A 额外承担评审职责：

```
1. Producer：生成任务 + 渐进式上下文披露
2. Reviewer：评审 Agent B 输出质量
3. 决策：Accept / Revise / Reject
4. 反馈：将评审结果转为 GRPO 奖励
```

**质量评审维度**：
| 维度 | 阈值 | 说明 |
|------|------|------|
| FORMAT | 0.8 | 输出格式正确 |
| COMPLETENESS | 0.7 | 所有需求满足 |
| ACCURACY | 0.75 | 技术正确性 |
| PERFORMANCE | 0.7 | 性能达标 |
| STYLE | 0.6 | 代码风格 |

### 2.3 约束

```
✅ 能做什么：
✅ 分析 results.tsv
✅ 修改 agent_a/generator.py
✅ 调整环境配置
✅ 配置奖励尺度
✅ 使用 Producer-Reviewer 协议

❌ 不能做什么：
❌ 不能修改 Agent B 的代码
❌ 不能直接修改 rl/trainer.py
❌ 不能改变评估指标
```

---

## 3. Agent B 职责

### 3.1 任务

```
1. 读取 Agent A 生成的环境
2. 运行实验（autoresearch_loop）
3. 收集训练结果
4. 计算奖励（RewardCalculator）
5. 更新模型（GRPO）
6. 记录结果到 results.tsv
```

### 3.2 约束

```
✅ 能做什么：
✅ 修改 rl/trainer.py
✅ 调整超参数
✅ 优化训练流程
✅ 添加日志

❌ 不能做什么：
❌ 不能修改 agent_a/generator.py
❌ 不能修改 tools/base.py
❌ 不能安装新依赖
❌ 不能改变评估指标
```

---

## 4. RL 训练器职责

### 4.1 任务

```
1. 计算细粒度奖励
   - Rformat ∈ {0, 1}
   - Rcorrect ∈ [-3, 3]
     - rname：工具名称匹配
     - rparam：参数名称匹配
     - rvalue：参数值匹配

2. 执行 GRPO 训练
   - 优势计算：Ai = (ri - μQ) / (σQ + η)
   - 策略更新

3. 返回训练统计
```

### 4.2 配置

```python
RLConfig(
    learning_rate=3e-4,
    gamma=0.99,
    epsilon=0.2,
    max_experiences=10000,
)
```

---

## 5. 共享资源

### 5.1 results.tsv

```tsv
commit	timestamp	bpb_score	memory_mb	status	description
exp0	2026-03-29T10:30:00	1.50	256	keep	Optimize reward calculation
exp1	2026-03-29T10:30:05	0.80	512	discard	Clean code
```

### 5.2 环境配置

```python
TrainingEnvironment(
    id="env_001",
    name="Beginner Environment",
    description="Simple tasks for initial training",
    tasks=[...],
    difficulty=0.3,
    available_tools=["git", "moon"],
    tool_constraints={...},
    reward_config={...},
)
```

---

## 6. 时间预算

### 6.1 固定预算

```python
MAX_TRAINING_TIME = 300  # 5 分钟
MAX_ITERATION_TIME = 1800  # 30 分钟
```

### 6.2 公平对比

所有实验使用相同的固定时间预算，确保公平对比。

---

## 7. 简洁性准则

> **"A small improvement that adds ugly complexity is not worth it."**
> — Karpathy

### 7.1 判断标准

```python
def is_worth_it(improvement, new_complexity):
    """
    判断一个改进是否值得
    
    原则：
    - 删除代码出效果 = 大力推广
    - 小改进 + 大复杂度 = 不值得
    """
    COMPLEXITY_PENALTY = 1.5
    return improvement > new_complexity * COMPLEXITY_PENALTY
```

### 7.2 实践

```
✅ 值得做：
- 删除 100 行无用代码
- 小改进 + 小改动
- 性能提升 + 简化代码

❌ 不值得做：
- 小改进 + 大重构
- 添加过度抽象
- 优化微性能但增加复杂度
```

---

## 8. 学习阶段

### 8.1 三阶段

```
Beginner (keep_rate < 0.3)
  - 难度：0.3
  - 奖励尺度：1.0
  - 任务数：2
  - 目标：建立基础

Intermediate (0.3 <= keep_rate < 0.6)
  - 难度：0.5
  - 奖励尺度：0.7
  - 任务数：3
  - 目标：提升能力

Advanced (keep_rate >= 0.6)
  - 难度：0.7
  - 奖励尺度：0.5
  - 任务数：5
  - 目标：精调性能
```

### 8.2 转换条件

```
升级条件：
- Beginner → Intermediate：keep_rate >= 0.3 持续 3 次
- Intermediate → Advanced：keep_rate >= 0.6 持续 3 次

降级条件：
- Advanced → Intermediate：keep_rate < 0.3
- Intermediate → Beginner：keep_rate < 0.2
```

---

## 9. 完整训练循环

```python
def run_dual_agent_with_toolrl(ws: str, iterations: int = 10):
    """
    完整的 ToolRL 训练循环
    
    基于 autoresearch 的理念：
    1. Agent A 分析进度 → 生成环境
    2. Agent B 运行实验 → 收集结果
    3. RL 训练器计算奖励 → 更新模型
    4. 记录结果 → 进入下一轮
    """
    # 初始化
    agent_a = AgentA(ws)
    agent_b = AgentB(ws, tools)
    trainer = RLTrainer(RLConfig())
    
    for epoch in range(iterations):
        # Agent A：分析并生成环境
        progress = agent_a.analyze_progress("results.tsv")
        stage = agent_a.get_learning_stage(progress)
        reward_scale = agent_a.get_dynamic_reward_scale(stage)
        env = agent_a.generate_environment(progress)
        
        # Agent B：运行实验
        results = agent_b.autoresearch_loop(env, max_iterations=5)
        
        # RL 训练：计算奖励并更新
        rewards = [trainer.reward_calc.calculate(traj) for traj in results]
        stats = trainer.train_step(results, use_grpo=True)
        
        # 记录结果
        for r in results:
            record = ExperimentRecord(...)
            results_log.append(record)
    
    return final_stats
```

---

## 10. 快速参考

### 10.1 命令

```bash
# 单 Agent 模式（测试）
python3 main.py --mode single --iterations 5

# 双 Agent 协作（完整训练）
python3 main.py --mode dual --iterations 10

# 性能对比
python3 compare.py --all
```

### 10.2 关键指标

| 指标 | 说明 | 目标 |
|------|------|------|
| `keep_rate` | 保留实验的比例 | >= 0.5 |
| `avg_reward` | 平均奖励 | >= 0.7 |
| `total_reward` | 总奖励 | 越高越好 |
| `stage_transitions` | 学习阶段转换 | 越多越好 |

### 10.3 核心文件

```
agent_a/program.md    # Agent A 的工作手册
agent_b/program.md    # Agent B 的工作手册
shared/program.md     # 共享资源和工作流
main.py               # 完整训练循环
```

---

## 11. 变更日志

### v1.3 (2026-03-31)
- 新增 Progressive Disclosure 协议（细粒度难度控制）
- 新增 protocols/progressive_disclosure/ 模块：
  - controller.py: 多维难度控制器（complexity/constraints/context/tools/scope）
  - disclosure.py: 渐进式上下文披露（hints/examples/scaffold/documentation）
  - task_config.py: 任务配置构建器 + TaskConfig
  - integration.py: 与 ExpertPool/DifficultyController 集成
- 核心功能：
  - 连续难度值（0.0-1.0，非固定 3 阶段）
  - 多维度独立调整（每个维度独立控制）
  - 基于实时性能信号动态调整
  - 渐进式上下文披露（低难度 = 更多 hints）
  - 支持 ε-greedy 探索 + 趋势分析
- 测试：19 个新单元测试，总测试 194 个通过

### v1.2 (2026-03-31)
- 新增 Expert Pool 协议（Harness 架构模式）
- 新增 protocols/expert_pool/ 模块：
  - pool.py: 专家注册表和管理
  - selector.py: 基于状态的动态选择算法
  - experts.py: 6 种专业化训练专家实现
  - integration.py: 与 FeedbackLoop/Producer-Reviewer 集成
- 核心功能：
  - 动态选择最合适的训练专家（基于 weak_areas）
  - 4 种选择策略：weak_area_first / performance_based / exploration / hybrid
  - ε-greedy 探索机制（避免局部最优）
  - 6 种专家类型：ToolMastery, ErrorRecovery, Optimization, MultiTool, EdgeCase, CodeReview
- 测试：18 个新单元测试，总测试 175 个通过

### v1.1 (2026-03-31)
- 新增 Producer-Reviewer 协作协议（参考 Harness 架构）
- 新增 protocols/producer_reviewer/ 模块（protocol/producer/reviewer/feedback_loop）
- 新增 protocols/integration.py 集成层
- Agent A 扩展评审职责（5 维度质量评估）
- 支持渐进式上下文披露（失败→更多 hints）
- 支持 Revise 迭代循环（最多 3 轮）
- 反馈模式分析（FeedbackLoop）
- 与 GRPO/ExperienceBuffer 无缝集成

### v1.0 (2026-03-29)
- 初始版本
- 基于 autoresearch program.md 设计
- 定义 Agent A/B 的职责和约束
- 定义 RL 训练器的任务
- 添加共享资源定义
- 定义时间预算和简洁性准则
- 定义三阶段学习流程

---

**最后更新**：2026-03-29 10:22 GMT+8
