# Agent B 工作手册

> 基于 autoresearch 的 program.md 设计理念
> 版本：v1.0
> 更新：2026-03-29

---

## 1. 概述

本手册定义了 Agent B（学习者）在 Curriculum-Forge 中的职责和工作流程。

Agent B 的核心任务是：
- 根据 Agent A 生成的环境运行实验
- 收集训练结果
- 评估模型性能
- 决策是否保留实验结果

---

## 2. 实验流程

### 2.1 初始化

```
1. 读取 Agent A 生成的环境配置
2. 读取当前的 RL 训练器配置
3. 验证工具注册表可用
4. 初始化结果记录
```

### 2.2 执行实验

```
1. 运行 autoresearch_loop（最多 N 次迭代）
2. 收集实验结果
3. 计算奖励（使用 RewardCalculator）
4. 更新训练器（使用 GRPO）
5. 记录结果到 results.tsv
```

### 2.3 决策

```
实验结果判定：
- keep_rate >= 阈值 → 保留实验 ✅
- keep_rate < 阈值 → 丢弃实验 ❌

保留标准：
- keep_rate >= 0.5：优秀
- keep_rate >= 0.3：良好
- keep_rate < 0.3：需改进
```

---

## 3. 约束

### 3.1 能做什么

```
✅ 修改 rl/trainer.py
✅ 调整超参数
✅ 修改奖励计算逻辑
✅ 优化训练流程
✅ 添加日志记录
```

### 3.2 不能做什么

```
❌ 不能修改 agent_a/generator.py
❌ 不能修改 tools/base.py
❌ 不能修改 shared/results.py
❌ 不能安装新依赖
❌ 不能修改评估指标
```

### 3.3 边界条件

```
⏱ 时间预算：
   - 单次实验：最大 5 分钟
   - 整体迭代：最大 30 分钟

💾 资源限制：
   - 内存：最大 8GB
   - GPU：软约束，可以超出但需有理由
```

---

## 4. 指标

### 4.1 核心指标

| 指标 | 说明 | 目标 |
|------|------|------|
| `keep_rate` | 保留实验的比例 | >= 0.5 |
| `avg_reward` | 平均奖励 | >= 0.7 |
| `total_reward` | 总奖励 | 越高越好 |
| `stage_transitions` | 学习阶段转换次数 | 越多越好 |

### 4.2 奖励分解

```
Rfinal = Rformat + Rcorrect
       = {0,1} + [-3,3]
       = rname + rparam + rvalue

其中：
- Rformat ∈ {0, 1}：格式正确性
- Rcorrect ∈ [-3, 3]：正确性
  - rname：工具名称匹配
  - rparam：参数名称匹配
  - rvalue：参数值匹配
```

### 4.3 GRPO 训练

```
优势计算：
Ai = (ri - μQ) / (σQ + η)

其中：
- ri：第 i 个实验的奖励
- μQ：组内平均奖励
- σQ：组内标准差
- η：常数（0.01）
```

---

## 5. 输出格式

### 5.1 实验输出

```
=== Experiment Log ===
Environment: {env_name}
Difficulty: {difficulty}
Stage: {learning_stage}
Reward Scale: {reward_scale}
---

Iteration 1/{max_iterations}:
  [B] Running experiments...
  [RL] Computing Rewards
    • Total reward: {total_reward:.2f}
    • Avg reward: {avg_reward:.2f}
    • Experiences: {experiences}
  [Results]
    • Experiments: {total}
    • Kept: {kept}/{total} ({keep_rate:.0%})

=== Final Statistics ===
Total experiments: {total_experiments}
Keep rate: {keep_rate:.1%}
Final stage: {final_stage}
```

### 5.2 结果文件格式

```tsv
commit	timestamp	bpb_score	memory_mb	status	description
exp0	2026-03-29T10:30:00	1.50	256	keep	Optimize reward calculation
exp1	2026-03-29T10:30:05	0.80	512	discard	Clean code
```

---

## 6. 简洁性准则

> **"A small improvement that adds ugly complexity is not worth it."**
> — Karpathy

### 6.1 判断标准

```python
def is_worth_it(improvement, new_complexity):
    """
    判断一个改进是否值得
    
    Args:
        improvement: 性能提升（0-1）
        new_complexity: 新增复杂度（0-1）
    
    Returns:
        bool: 是否值得
    """
    COMPLEXITY_PENALTY = 1.5
    return improvement > new_complexity * COMPLEXITY_PENALTY
```

### 6.2 实践原则

```
✅ 值得做：
- 删除代码出效果
- 小改进 + 小复杂度
- 大改进 + 中等复杂度

❌ 不值得做：
- 小改进 + 大复杂度
- 删除有用的代码
- 添加过度工程
```

---

## 7. 学习阶段

### 7.1 三阶段动态调整

```
Beginner (keep_rate < 0.3)
  - 难度：0.3
  - 奖励尺度：1.0
  - 任务：2 个简单任务

Intermediate (0.3 <= keep_rate < 0.6)
  - 难度：0.5
  - 奖励尺度：0.7
  - 任务：3 个中等任务

Advanced (keep_rate >= 0.6)
  - 难度：0.7
  - 奖励尺度：0.5
  - 任务：5 个复杂任务
```

### 7.2 阶段转换

```
阶段转换条件：
- Beginner → Intermediate：keep_rate >= 0.3 持续 3 次
- Intermediate → Advanced：keep_rate >= 0.6 持续 3 次
- Advanced → Intermediate：keep_rate < 0.3
- Intermediate → Beginner：keep_rate < 0.2
```

---

## 8. 快速参考

### 8.1 命令

```bash
# 单 Agent 模式（测试）
python3 main.py --mode single --iterations 5

# 双 Agent 协作（完整训练）
python3 main.py --mode dual --iterations 10

# 性能对比
python3 compare.py --all
```

### 8.2 关键文件

```
rl/trainer.py        # 唯一能修改的核心文件
agent_a/generator.py # 环境生成（不能改）
tools/base.py        # 工具注册表（不能改）
shared/results.py    # 结果记录（不能改）
```

### 8.3 核心配置

```python
RLConfig(
    learning_rate=3e-4,
    gamma=0.99,
    epsilon=0.2,
    max_experiences=10000,
)

MAX_TRAINING_TIME = 300  # 5 分钟
MAX_MEMORY_GB = 8
```

---

## 9. 常见问题

### Q1: 如何判断实验是否成功？
A: keep_rate >= 0.5 表示成功，keep_rate < 0.3 表示失败。

### Q2: 时间超了怎么办？
A: 如果超过 5 分钟仍未完成，记录当前进度并终止实验。

### Q3: 内存超了怎么办？
A: 记录警告，但继续执行（软约束）。

### Q4: 如何添加新功能？
A: 先评估复杂度 penalty，确保 improvement > complexity * 1.5。

---

## 10. 变更日志

### v1.0 (2026-03-29)
- 初始版本
- 基于 autoresearch program.md 设计
- 定义 Agent B 的职责和工作流程
- 添加简洁性准则
- 定义三阶段学习

---

**最后更新**：2026-03-29 10:22 GMT+8
