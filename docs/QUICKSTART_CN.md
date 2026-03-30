# 🚀 快速开始指南

本文档帮助你 **5 分钟内** 运行 Curriculum-Forge！

---

## 1. 环境准备

### 1.1 检查 Python 版本

```bash
python3 --version
# 需要 Python 3.7+
```

### 1.2 （可选）安装 Ollama

如果你想使用本地 LLM：

```bash
# macOS
brew install ollama

# 启动服务
ollama serve

# 下载模型（新终端）
ollama pull llama3.2
```

---

## 2. 基本运行

### 2.1 运行基础训练

```bash
cd ~/.qclaw/workspace/dual-agent-tool-rl

python3 main.py --mode dual --iterations 5
```

**输出示例：**

```
======================================================================
Epoch 1/5 [00:00]
======================================================================

[Agent A] Progress Analysis
  • Total experiments: 0
  • Keep rate: 0.0%
  • Best score: 0.00
  • Learning stage: beginner

[Agent B] Running Experiments
  • Max iterations: 5

[RL Trainer] Computing Rewards (ToolRL)
  • Method: GRPO
  • Total reward: 3.50
  • Avg reward: 0.70
```

### 2.2 查看系统状态

```bash
python3 cli.py status
```

### 2.3 查看日志

```bash
# 列出所有日志
python3 cli.py log list

# 查看最新日志
python3 cli.py log show
```

---

## 3. 进阶功能

### 3.1 启用验证机制

```bash
python3 main.py --mode dual --iterations 5 --enable-verification
```

### 3.2 配置时间预算

```bash
# 每个实验 5 分钟，每次迭代 30 分钟
python3 main.py --mode dual --iterations 5 \
    --exp-time 300 --iter-time 1800
```

### 3.3 离线模式

```bash
# 无需 LLM，使用模拟响应
python3 main.py --mode dual --offline
```

### 3.4 查看 LLM 状态

```bash
python3 cli.py llm
```

---

## 4. 代码集成

### 4.1 在代码中使用

```python
import sys
sys.path.insert(0, '/path/to/curriculum-forge')

from agent_a.generator import AgentA
from agent_b.learner import AgentB
from rl.trainer import RLTrainer
from agent_a.analyst import AnalystAgent
from shared.human_feedback import HumanFeedbackManager

# 创建组件
agent_a = AgentA(workspace='.', enable_analyst=True, enable_human_feedback=True)
agent_b = AgentB(workspace='.', tools=[])
trainer = RLTrainer(enable_evolution=True)

# 分析进度
progress = agent_a.analyze_progress('results.tsv')

# 生成环境
env = agent_a.generate_environment(progress)

# 运行实验
results = agent_b.autoresearch_loop(env)

# 训练
stats = trainer.train_step(results)
```

### 4.2 自定义奖励计算

```python
from rl.enhanced_reward_calculator import EnhancedRewardCalculator

calc = EnhancedRewardCalculator()
reward = calc.calculate(trajectory)

print(f"Total: {reward.total:.3f}")
print(f"Confidence: {reward.verification.confidence:.1%}")
print(calc.get_feedback(reward))
```

### 4.3 使用进化算法

```python
from rl.evolution import EvolutionOptimizer, SelectionMethod

optimizer = EvolutionOptimizer(
    population_size=10,
    mutation_rate=0.1,
)

def fitness_func(genotype):
    return evaluate(genotype)

history = optimizer.evolve(generations=10, fitness_func=fitness_func)
best = optimizer.get_best_genotype()
```

---

## 5. 常见问题

### Q1: 报错 "Ollama not running"

**解决方案：**
```bash
# 启动 Ollama
ollama serve

# 或使用离线模式
python3 main.py --offline
```

### Q2: 训练速度慢

**解决方案：**
```bash
# 减少迭代次数
python3 main.py --iterations 3

# 减少实验数量
# 修改 agent_b/learner.py 中的 max_iterations
```

### Q3: 内存不足

**解决方案：**
```bash
# 限制并发
python3 main.py --max-concurrent 2

# 清理日志
rm -rf .scratchpad/*.jsonl
```

---

## 6. 下一步

| 资源 | 说明 |
|------|------|
| [API 文档](API.md) | 完整 API 参考 |
| [使用示例](EXAMPLES.md) | 更多示例代码 |
| [架构设计](ARCHITECTURE.md) | 系统设计详解 |

---

**准备好开始了吗？运行第一个训练：**

```bash
cd ~/.qclaw/workspace/dual-agent-tool-rl
python3 main.py --mode dual --iterations 5 --offline
```
