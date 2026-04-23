# 性能对比和超参数优化指南

> **文件**：benchmark.py, compare.py  
> **功能**：完整的性能对比和超参数优化框架  
> **日期**：2026-03-28

---

## 一、快速开始

### 1.1 对比 GRPO vs GAE

```bash
cd ~/.qclaw/workspace/dual-agent-tool-rl

# 运行对比
python3 compare.py --algorithm
```

**输出示例**：
```
======================================================================
Algorithm Comparison: GRPO vs GAE
======================================================================

[Running] grpo_cold_start
  ✓ Keep rate: 62.0%
  ✓ Avg reward: 0.85
  ✓ Training time: 45.3s

[Running] gae_cold_start
  ✓ Keep rate: 58.0%
  ✓ Avg reward: 0.72
  ✓ Training time: 42.1s

======================================================================
Benchmark Comparison Summary
======================================================================

By Algorithm:
  GRPO:
    • Count: 1
    • Avg Keep Rate: 62.0%
    • Avg Training Time: 45.3s
  GAE:
    • Count: 1
    • Avg Keep Rate: 58.0%
    • Avg Training Time: 42.1s

Best Results:
  • Best Keep Rate: grpo_cold_start (62.0%)
  • Best Speed: gae_cold_start (42.1s)
```

### 1.2 对比 Cold Start vs SFT+RL

```bash
python3 compare.py --mode
```

### 1.3 超参数优化

```bash
python3 compare.py --hyperparameter
```

### 1.4 运行所有对比

```bash
python3 compare.py --all
```

---

## 二、框架详解

### 2.1 BenchmarkRunner

```python
from benchmark import BenchmarkRunner, BenchmarkConfig

runner = BenchmarkRunner("benchmarks")

config = BenchmarkConfig(
    name="test_grpo",
    mode="cold_start",
    algorithm="grpo",
    reward_scale=1.0,
    learning_stage_thresholds=(0.3, 0.6),
    iterations=10,
)

result = runner.run_benchmark(config)
print(f"Keep rate: {result.keep_rate:.1%}")
print(f"Training time: {result.training_time:.1f}s")
```

### 2.2 HyperparameterOptimizer

```python
from benchmark import HyperparameterOptimizer

optimizer = HyperparameterOptimizer("benchmarks")

# 优化奖励尺度
reward_results = optimizer.optimize_reward_scales(
    scales=[0.5, 0.7, 1.0, 1.3, 1.5],
    iterations=5
)

# 优化学习阶段阈值
threshold_results = optimizer.optimize_stage_thresholds(
    thresholds=[(0.2, 0.5), (0.3, 0.6), (0.4, 0.7)],
    iterations=5
)
```

---

## 三、性能指标

### 3.1 关键指标

| 指标 | 说明 | 范围 |
|------|------|------|
| **Keep Rate** | 保留的实验比例 | 0-100% |
| **Avg Reward** | 平均奖励 | [-3, 4] |
| **Training Time** | 训练耗时 | 秒 |
| **Stage Transitions** | 学习阶段转换次数 | 1-3 |

### 3.2 对比维度

#### GRPO vs GAE
- **稳定性**：GRPO 通过组归一化减少方差
- **速度**：GAE 可能更快但不稳定
- **收敛**：GRPO 收敛更平稳

#### Cold Start vs SFT+RL
- **Cold Start**：从零开始，无预训练偏差
- **SFT+RL**：基于 SFT 预训练，可能更快收敛
- **泛化**：Cold Start 泛化能力可能更强

---

## 四、超参数优化

### 4.1 奖励尺度优化

```bash
python3 compare.py --hyperparameter
```

**测试范围**：0.5, 0.7, 1.0, 1.3, 1.5

**优化目标**：最大化 keep_rate

**预期结果**：
- 低尺度（0.5）：细粒度反馈，但可能学习缓慢
- 中等尺度（1.0）：平衡探索和利用
- 高尺度（1.5）：鼓励探索，但可能不稳定

### 4.2 学习阶段阈值优化

**测试范围**：
- (0.2, 0.5)：快速升级
- (0.3, 0.6)：标准升级
- (0.4, 0.7)：缓慢升级

**优化目标**：最大化 keep_rate 和 stage_transitions

**预期结果**：
- 快速升级：可能跳过学习
- 标准升级：平衡学习和难度
- 缓慢升级：充分学习但可能缓慢

---

## 五、结果分析

### 5.1 查看结果

```bash
# 查看对比结果
cat benchmarks/algorithm_comparison/benchmark_results.json

# 查看超参数优化结果
cat benchmarks/hyperparameter_optimization/benchmark_results.json
```

### 5.2 结果格式

```json
{
  "timestamp": "2026-03-28T23:50:00",
  "total_benchmarks": 2,
  "benchmarks": [
    {
      "config": {
        "name": "grpo_cold_start",
        "mode": "cold_start",
        "algorithm": "grpo",
        "reward_scale": 1.0,
        "iterations": 5
      },
      "keep_rate": 0.62,
      "avg_reward": 0.85,
      "training_time": 45.3,
      "stage_transitions": 2,
      "final_stage": "intermediate"
    }
  ],
  "summary": {
    "by_algorithm": {
      "grpo": {
        "avg_keep_rate": 0.62,
        "avg_training_time": 45.3
      }
    }
  }
}
```

---

## 六、常见问题

### Q1: 如何自定义对比配置？

A: 编辑 `compare.py` 中的 `configs` 列表：

```python
configs = [
    BenchmarkConfig(
        name="my_config",
        mode="cold_start",
        algorithm="grpo",
        reward_scale=1.2,
        iterations=10,
    ),
]
```

### Q2: 如何添加新的超参数？

A: 在 `BenchmarkConfig` 中添加字段，然后在 `BenchmarkRunner.run_benchmark()` 中使用。

### Q3: 对比结果如何解读？

A: 
- **Keep Rate 高**：模型学习效果好
- **Training Time 短**：算法效率高
- **Stage Transitions 多**：学习阶段转换频繁

### Q4: 如何找到最优超参数？

A: 运行 `python3 compare.py --hyperparameter`，查看结果中的 "Best Results" 部分。

---

## 七、最佳实践

### 7.1 对比流程

1. **基准测试**：运行 `--algorithm` 对比 GRPO vs GAE
2. **模式对比**：运行 `--mode` 对比 Cold Start vs SFT+RL
3. **超参数优化**：运行 `--hyperparameter` 找最优参数
4. **结果分析**：查看 JSON 结果文件

### 7.2 优化策略

1. **粗粒度搜索**：先测试大范围的参数
2. **细粒度搜索**：在最优区域进行细致搜索
3. **验证**：用最优参数运行多次验证稳定性

### 7.3 性能指标权衡

- **追求准确性**：优化 keep_rate
- **追求速度**：优化 training_time
- **平衡**：同时考虑两者

---

## 八、集成到 CI/CD

### 8.1 GitHub Actions

```yaml
name: Performance Benchmarks
on: [push]
jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - run: python3 compare.py --all
      - uses: actions/upload-artifact@v2
        with:
          name: benchmark-results
          path: benchmarks/
```

### 8.2 定期运行

```bash
# 每周运行一次
0 0 * * 0 cd /path/to/project && python3 compare.py --all
```

---

## 九、参考资源

- **论文**：ToolRL: Reward is All Tool Learning Needs
- **代码**：benchmark.py, compare.py
- **文档**：TRAINING_GUIDE.md, TOOLRL_INTEGRATION.md

---

**最后更新**：2026-03-28 23:55 GMT+8