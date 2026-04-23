# ToolRL 集成指南

> 将 ToolRL 论文的奖励设计和课程学习策略集成到 dual-agent-tool-rl 项目

---

## 一、改进总结

### 1.1 RewardCalculator（rl/trainer.py）

**改进前**：粗粒度奖励，只有 4 个配置项

**改进后**：ToolRL 风格的细粒度奖励分解

```python
# 格式奖励 Rformat ∈ {0, 1}
r_format = calculate_format_reward(trajectory)

# 正确性奖励 Rcorrect ∈ [-3, 3]
r_name = calculate_tool_name_match(predicted, ground_truth)
r_param = calculate_param_name_match(predicted, ground_truth)
r_value = calculate_param_value_match(predicted, ground_truth)

# 总奖励 Rfinal = Rformat + Rcorrect ∈ [-3, 4]
r_final = r_format + (r_name + r_param + r_value) * scale
```

### 1.2 RLTrainer（rl/trainer.py）

**改进前**：标准 GAE 优势计算

**改进后**：GRPO 组归一化优势计算

```python
# GRPO 组归一化
Ai(si|Q) = (ri - μQ) / (σQ + η)

# 优点：
# - 减少奖励方差
# - 更稳定的训练
# - 更快的收敛
```

### 1.3 AgentA（agent_a/generator.py）

**改进前**：固定难度和奖励配置

**改进后**：动态课程学习

```python
# 三个学习阶段
- beginner (keep_rate < 0.3): 难度 0.3, 奖励尺度 1.0
- intermediate (0.3 ≤ keep_rate < 0.6): 难度 0.5, 奖励尺度 0.7
- advanced (keep_rate ≥ 0.6): 难度 0.7, 奖励尺度 0.5

# 任务复杂度随阶段增加
- beginner: 2 个简单任务
- intermediate: 3 个中等任务
- advanced: 4 个复杂任务
```

---

## 二、使用示例

### 2.1 基本训练流程

```python
from rl.trainer import RLTrainer, RLConfig
from agent_a.generator import AgentA

# 初始化
trainer = RLTrainer(RLConfig(learning_rate=3e-4))
agent_a = AgentA()

# 分析 Agent B 的进度
progress = agent_a.analyze_progress("results.tsv")

# 生成环境（自动调整难度和奖励）
env = agent_a.generate_environment(progress)

# 训练
results = [...]  # Agent B 的实验结果
stats = trainer.train_step(results, use_grpo=True)

print(f"Avg Reward: {stats['avg_reward']:.3f}")
print(f"Method: {stats['method']}")
```

### 2.2 轨迹构建

```python
trajectory = {
    'predicted_tools': ['git', 'moon'],
    'ground_truth_tools': ['git', 'moon'],
    'predicted_params': {
        'branch': 'feature-x',
        'message': 'optimize performance'
    },
    'ground_truth_params': {
        'branch': 'feature-x',
        'message': 'optimize performance'
    },
    'think_idx': 0,
    'tool_call_idx': 1,
    'response_idx': 2,
}

reward = trainer.reward_calc.calculate(trajectory)
```

### 2.3 监控学习阶段

```python
stage = agent_a.get_learning_stage(progress)
reward_scale = agent_a.get_dynamic_reward_scale(stage)

print(f"Stage: {stage}")
print(f"Reward Scale: {reward_scale}")
print(f"Keep Rate: {progress.keep_rate:.2%}")
```

---

## 三、关键参数

### 3.1 奖励尺度

| 参数 | 值 | 说明 |
|------|-----|------|
| `r_format_scale` | 1.0 | 格式奖励最大值 |
| `r_correct_scale` | 3.0 | 正确性奖励最大值 |
| `r_name_weight` | 1.0 | 工具名称匹配权重 |
| `r_param_weight` | 1.0 | 参数名称匹配权重 |
| `r_value_weight` | 1.0 | 参数值匹配权重 |

### 3.2 学习阶段

| 阶段 | keep_rate | 难度 | 奖励尺度 | 任务数 | 工具调用限制 |
|------|-----------|------|---------|-------|------------|
| beginner | < 0.3 | 0.3 | 1.0 | 2 | 10 |
| intermediate | 0.3-0.6 | 0.5 | 0.7 | 3 | 15 |
| advanced | ≥ 0.6 | 0.7 | 0.5 | 4 | 20 |

### 3.3 GRPO 参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `eta` | 1e-8 | 避免除以零的常数 |
| `gamma` | 0.99 | 折扣因子 |
| `epsilon` | 0.2 | PPO 裁剪范围 |

---

## 四、性能对比

### 4.1 论文结果（ToolRL）

| 模型 | 基线 | SFT | GRPO Cold Start | 提升 |
|------|------|-----|-----------------|------|
| Qwen2.5-7B | 42.0% | 36.5% | **58.4%** | +17% |

### 4.2 预期改进

在 dual-agent-tool-rl 中应用 ToolRL 设计后：

- **奖励信号质量**：从 4 维 → 5 维（加入细粒度分解）
- **训练稳定性**：GAE → GRPO（减少方差）
- **学习效率**：固定难度 → 动态课程（加快收敛）

---

## 五、调试建议

### 5.1 检查奖励分布

```python
# 在 train_step 中添加
rewards = [trainer.reward_calc.calculate(traj) for traj in trajectories]
print(f"Reward range: [{min(rewards):.2f}, {max(rewards):.2f}]")
print(f"Reward mean: {sum(rewards)/len(rewards):.2f}")
```

### 5.2 监控学习阶段转换

```python
# 在每个 epoch 后检查
stage = agent_a.get_learning_stage(progress)
if stage != prev_stage:
    print(f"Stage transition: {prev_stage} → {stage}")
    print(f"New reward scale: {agent_a.get_dynamic_reward_scale(stage)}")
```

### 5.3 验证 GRPO 优势

```python
# 对比 GAE vs GRPO
stats_gae = trainer.train_step(results, use_grpo=False)
stats_grpo = trainer.train_step(results, use_grpo=True)

print(f"GAE avg advantage: {stats_gae['avg_advantage']:.3f}")
print(f"GRPO avg advantage: {stats_grpo['avg_advantage']:.3f}")
```

---

## 六、后续优化

### 6.1 短期（1-2 周）

- [ ] 在 main.py 中集成 ToolRL 奖励计算
- [ ] 添加奖励可视化（TensorBoard）
- [ ] 对比 Cold Start vs SFT+RL

### 6.2 中期（1 个月）

- [ ] 实现完整的 GRPO 算法（包括 KL 惩罚选项）
- [ ] 添加多任务学习支持
- [ ] 优化超参数

### 6.3 长期（2-3 个月）

- [ ] 集成 R1 风格的深度思考
- [ ] 实现自适应奖励尺度
- [ ] 支持多模型并行训练

---

## 七、参考资源

- **论文**：ToolRL: Reward is All Tool Learning Needs
- **代码**：`rl/trainer.py`, `agent_a/generator.py`
- **笔记**：`memory/ToolRL-paper-notes.md`

---

## 八、常见问题

### Q: 为什么 GRPO 比 PPO 更好？

A: GRPO 使用组归一化来减少奖励方差，使训练更稳定。特别是在奖励信号不一致的情况下。

### Q: 什么时候应该增加难度？

A: 当 keep_rate 达到 0.6 时，自动从 intermediate 升级到 advanced。

### Q: 奖励尺度如何影响学习？

A: 高尺度（1.0）鼓励探索，低尺度（0.5）提供细粒度反馈。动态调整可以平衡两者。

### Q: 如何处理奖励为负的情况？

A: 这是正常的。负奖励表示模型的输出与预期不符。GRPO 的组归一化会自动处理。