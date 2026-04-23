# 完整训练循环使用指南

> **文件**：main.py  
> **功能**：ToolRL 完整训练循环集成  
> **日期**：2026-03-28

---

## 一、快速开始

### 1.1 单 Agent 模式（测试）

```bash
cd ~/.qclaw/workspace/dual-agent-tool-rl

# 运行 5 次迭代
python3 main.py --mode single --iterations 5
```

**输出示例**：
```
======================================================================
Single Agent Mode (with ToolRL Rewards)
======================================================================

[Environment] Single Agent Test
  • Difficulty: 0.5
  • Tasks: 1

[Agent B] Running experiments...

[RL Trainer] Computing Rewards
  • Method: GAE
  • Total reward: 2.45
  • Avg reward: 0.49

[Results]
  • Total: 5
  • Kept: 2/5
  • Avg reward: 0.49
```

### 1.2 双 Agent 协作模式（完整训练）

```bash
# 运行 10 个 epoch，使用 GRPO
python3 main.py --mode dual --iterations 10

# 或使用 GAE（不用 GRPO）
python3 main.py --mode dual --iterations 10 --no-grpo
```

**输出示例**：
```
======================================================================
Dual-Agent ToolRL Mode (with ToolRL Training Loop)
======================================================================

======================================================================
Epoch 1/10
======================================================================

[Agent A] Progress Analysis
  • Total experiments: 0
  • Keep rate: 0.0%
  • Best score: 0.00
  • Learning stage: beginner
  • Reward scale: 1.0

[Agent A] Environment Generated
  • Name: Environment #1 (beginner)
  • Difficulty: 0.3
  • Tasks: 2
  • Tool constraints: {'max_tool_calls': 10, 'timeout': 300}

[Agent B] Running Experiments
  • Max iterations: 5

[RL Trainer] Computing Rewards (ToolRL)
  • Method: GRPO
  • Total reward: 3.50
  • Avg reward: 0.70
  • Avg advantage: 0.15
  • Experiences: 5

[Results] Recording Experiments
  • Experiments: 5
  • Kept: 3/5 (60%)
  • Cumulative: 3/5 (60%)

...

======================================================================
Final Statistics
======================================================================
  • Total experiments: 50
  • Keep rate: 62.0%
  • Stage transitions: 2
  • Final stage: intermediate
  • Training method: GRPO
  • Total experiences: 50
```

---

## 二、训练循环详解

### 2.1 完整流程

```
Epoch Loop:
  ├─ [Agent A] 分析进度
  │  ├─ 读取 results.tsv
  │  ├─ 计算 keep_rate
  │  └─ 判断学习阶段
  │
  ├─ [Agent A] 生成环境
  │  ├─ 根据阶段设置难度
  │  ├─ 生成任务列表
  │  └─ 配置奖励尺度
  │
  ├─ [Agent B] 运行实验
  │  ├─ 执行 autoresearch 循环
  │  ├─ 使用工具（git, moon）
  │  └─ 收集结果
  │
  ├─ [RL Trainer] 计算奖励
  │  ├─ 转换为 ToolRL 轨迹格式
  │  ├─ 计算 Rformat + Rcorrect
  │  └─ 计算 GRPO 优势
  │
  └─ [Results] 记录结果
     ├─ 写入 results.tsv
     ├─ 更新统计信息
     └─ 进入下一 epoch
```

### 2.2 关键变量

| 变量 | 类型 | 说明 |
|------|------|------|
| `progress` | AgentBProgress | Agent B 的学习进度 |
| `stage` | str | 学习阶段（beginner/intermediate/advanced） |
| `env` | TrainingEnvironment | 训练环境 |
| `results` | List[Dict] | Agent B 的实验结果 |
| `trajectories` | List[Dict] | ToolRL 格式的轨迹 |
| `rewards` | List[float] | 每个轨迹的奖励 |
| `stats` | Dict | 训练统计信息 |

---

## 三、参数说明

### 3.1 命令行参数

```bash
python3 main.py [OPTIONS]

OPTIONS:
  --mode {single,dual}      运行模式（默认：dual）
  --workspace PATH          工作区路径（默认：workspace）
  --iterations N            迭代次数（默认：10）
  --no-grpo                 使用 GAE 而非 GRPO
  -h, --help               显示帮助信息
```

### 3.2 环境变量

```bash
# 设置工作区
export WORKSPACE=~/my_workspace

# 运行
python3 main.py --workspace $WORKSPACE --iterations 20
```

---

## 四、监控和调试

### 4.1 查看实时进度

```bash
# 监控 results.tsv
tail -f workspace/results.tsv

# 统计信息
wc -l workspace/results.tsv
```

### 4.2 检查学习阶段转换

```bash
# 在输出中查找
grep "Stage transition" output.log

# 或手动检查
python3 -c "
from agent_a.generator import AgentA
agent_a = AgentA()
progress = agent_a.analyze_progress('workspace/results.tsv')
print(f'Stage: {agent_a.get_learning_stage(progress)}')
print(f'Keep rate: {progress.keep_rate:.1%}')
"
```

### 4.3 奖励分布

```bash
# 查看奖励统计
python3 -c "
import csv
rewards = []
with open('workspace/results.tsv') as f:
    reader = csv.DictReader(f, delimiter='\t')
    for row in reader:
        try:
            rewards.append(float(row['bpb_score']))
        except:
            pass

if rewards:
    print(f'Min: {min(rewards):.2f}')
    print(f'Max: {max(rewards):.2f}')
    print(f'Avg: {sum(rewards)/len(rewards):.2f}')
"
```

---

## 五、常见问题

### Q1: 如何中断训练？

A: 按 `Ctrl+C`。已完成的 epoch 会被保存到 results.tsv。

### Q2: 如何恢复训练？

A: 直接运行相同的命令。程序会读取 results.tsv 并继续。

### Q3: GRPO vs GAE 有什么区别？

A: 
- **GRPO**：组归一化，减少方差，更稳定（推荐）
- **GAE**：标准优势计算，更快但可能不稳定

### Q4: 如何修改学习阶段阈值？

A: 编辑 `agent_a/generator.py` 中的 `get_learning_stage()` 方法。

### Q5: 如何自定义奖励尺度？

A: 编辑 `agent_a/generator.py` 中的 `reward_scales` 字典。

---

## 六、性能优化

### 6.1 加速训练

```bash
# 减少迭代次数
python3 main.py --mode dual --iterations 5

# 或减少每个 epoch 的实验数
# 编辑 main.py 中的 max_iterations=5 → max_iterations=2
```

### 6.2 节省内存

```bash
# 定期清理工作区
rm -rf workspace/
python3 main.py --workspace workspace --iterations 10
```

### 6.3 并行训练

```bash
# 在不同工作区运行多个实例
python3 main.py --workspace workspace1 --iterations 10 &
python3 main.py --workspace workspace2 --iterations 10 &
wait
```

---

## 七、输出文件

### 7.1 results.tsv

```
commit	timestamp	bpb_score	memory_mb	status	description
exp0	2026-03-28T23:50:00	1.50	256	keep	Optimize performance
exp1	2026-03-28T23:50:05	0.80	512	discard	Clean code
...
```

### 7.2 日志

```bash
# 保存输出到文件
python3 main.py --mode dual --iterations 10 > training.log 2>&1

# 查看日志
tail -100 training.log
```

---

## 八、下一步

### 8.1 集成到 CI/CD

```bash
# GitHub Actions 示例
name: ToolRL Training
on: [push]
jobs:
  train:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - run: python3 main.py --mode dual --iterations 5
```

### 8.2 添加可视化

```bash
# 使用 TensorBoard
pip install tensorboard
# 在 main.py 中添加 TensorBoard 日志
```

### 8.3 分布式训练

```bash
# 使用 Ray 进行分布式训练
pip install ray
# 修改 main.py 使用 Ray
```

---

## 九、参考资源

- **论文**：ToolRL: Reward is All Tool Learning Needs
- **代码**：`rl/trainer.py`, `agent_a/generator.py`
- **文档**：TOOLRL_INTEGRATION.md, GSTACK_REPORT.md

---

**最后更新**：2026-03-28 23:50 GMT+8