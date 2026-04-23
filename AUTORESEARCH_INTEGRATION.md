# 🎉 Curriculum-Forge - autoresearch 灵感集成完成

> **日期**：2026-03-29  
> **来源**：autoresearch by Karpathy  
> **实现**：4 个核心灵感

---

## 📋 完成概览

### 四个灵感的完整实现

| # | 灵感 | 状态 | 文件 | 大小 |
|---|------|------|------|------|
| 1 | program.md 设计 | ✅ | agent_a/program.md, agent_b/program.md, shared/program.md | ~20KB |
| 2 | 固定时间预算 | ✅ | shared/time_budget.py | 3.3KB |
| 3 | 简洁性准则 | ✅ | shared/complexity_checker.py | 9.1KB |
| 4 | Git 版本控制 | ✅ | shared/git_manager.py | 9.8KB |

---

## 🔥 灵感 1：program.md 设计

### 实现内容

**Agent A 工作手册**（agent_a/program.md）
- 任务：分析进度、生成环境
- 约束：不能修改 Agent B
- 指标：keep_rate、stage_transitions
- 三阶段学习定义

**Agent B 工作手册**（agent_b/program.md）
- 任务：运行实验、收集结果
- 约束：不能修改 Agent A
- 指标：keep_rate、avg_reward
- 简洁性准则

**共享工作手册**（shared/program.md）
- Agent A/B 协作规范
- 时间预算定义
- 完整训练循环

### 核心设计

```markdown
## 约束
✅ 能做什么
❌ 不能做什么
⏱ 边界条件

## 指标
- keep_rate >= 0.5：优秀
- keep_rate >= 0.3：良好
- keep_rate < 0.3：需改进

## 简洁性准则
"A small improvement that adds ugly complexity is not worth it."
```

---

## ⏱ 灵感 2：固定时间预算

### 实现内容

**TimeBudget**（时间预算配置）
```python
@dataclass
class TimeBudget:
    experiment: int = 300  # 5 分钟/实验
    iteration: int = 1800  # 30 分钟/迭代
    evaluation: int = 60   # 1 分钟/评估
    overhead: int = 60     # 1 分钟/开销
```

**TimeBudgetManager**（时间预算管理器）
- start_training()：开始训练计时
- start_experiment()：开始实验计时
- check_experiment_timeout()：检查实验超时
- check_iteration_timeout()：检查迭代超时

### 使用方式

```bash
# 默认时间预算
python3 main.py --mode dual --iterations 10

# 自定义时间预算
python3 main.py --mode dual --iterations 10 --exp-time 600 --iter-time 3600

# 禁用时间预算
python3 main.py --mode dual --iterations 10 --no-time-budget
```

---

## 🎯 灵感 3：简洁性准则

### 实现内容

**ComplexityChecker**（复杂度检查器）
```python
class ComplexityChecker:
    def evaluate_code_complexity(self, code: str) -> ComplexityScore
    def evaluate_improvement(self, **gains) -> ImprovementScore
    def evaluate(self, improvement, complexity) -> SimplicityEvaluation
```

**评估维度**

| 复杂度维度 | 权重 |
|-----------|------|
| code_lines | 0.2 |
| dependencies | 0.3 |
| abstractions | 0.2 |
| special_cases | 0.3 |

| 改进维度 | 权重 |
|---------|------|
| performance | 0.4 |
| readability | 0.2 |
| maintainability | 0.2 |
| functionality | 0.2 |

### 判断标准

```
改进 > 复杂度 * 1.5 → ✅ 值得
否则 → ❌ 不值得
```

### 使用方式

```python
from shared.complexity_checker import ComplexityChecker, is_worth_it

checker = ComplexityChecker()

# 评估代码
complexity = checker.evaluate_code_complexity(code)

# 评估改进
improvement = checker.evaluate_improvement(
    performance_gain=0.8,
    readability_gain=0.3
)

# 综合评估
result = checker.evaluate(improvement, complexity)
print(f"Worth it: {result.is_worth_it}")
```

---

## 📚 灵感 4：Git 版本控制

### 实现内容

**GitManager**（Git 管理器）
```python
class GitManager:
    def init(self) -> bool
    def create_experiment_branch(self, run_tag: str) -> str
    def commit_improvement(self, message: str, ...) -> str
    def discard_result(self) -> bool
    def get_experiment_history(self, limit: int) -> List[GitCommit]
    def print_status(self)
```

### Git 工作流

```bash
# 1. 创建实验分支
manager.create_experiment_branch('mar29')
# → autoresearch/mar29

# 2. 运行实验
results = agent_b.autoresearch_loop(env)

# 3. 判断结果
if keep_rate > baseline:
    manager.commit_improvement(
        f'Improved: {baseline:.1%} -> {keep_rate:.1%}',
        keep_rate=keep_rate,
        avg_reward=avg_reward
    )
else:
    manager.discard_result()
```

### 特点

- **可选功能**：Git 不可用时自动禁用
- **轻量级**：不依赖 GitPython
- **优雅降级**：不影响主流程

---

## 📊 文件清单

### 新增文件

```
shared/
├── time_budget.py          # 时间预算管理（3.3KB）
├── complexity_checker.py   # 简洁性检查器（9.1KB）
├── git_manager.py          # Git 版本控制（9.8KB）
├── program.md              # 共享工作手册（6.6KB）
│
agent_a/
└── program.md              # Agent A 工作手册（7.8KB）
│
agent_b/
└── program.md              # Agent B 工作手册（5.9KB）
```

### 更新文件

```
main.py                     # 添加时间预算支持
```

### 新增文档

```
AUTORESEARCH_INTEGRATION.md  # 集成指南（本文件）
```

---

## 🚀 快速开始

### 1. 查看工作手册

```bash
cat agent_a/program.md
cat agent_b/program.md
cat shared/program.md
```

### 2. 运行训练

```bash
# 默认配置
python3 main.py --mode dual --iterations 10

# 自定义时间预算
python3 main.py --mode dual --iterations 10 --exp-time 600

# 禁用时间预算
python3 main.py --mode dual --iterations 10 --no-time-budget
```

### 3. 使用简洁性检查

```python
from shared.complexity_checker import ComplexityChecker

checker = ComplexityChecker()
result = checker.check_feature(
    code=new_code,
    performance_gain=0.7,
    readability_gain=0.5
)
print(f"Worth it: {result.is_worth_it}")
```

### 4. 使用 Git 管理

```python
from shared.git_manager import GitManager

manager = GitManager('.')
manager.init()
manager.create_experiment_branch('mar29')
manager.commit_improvement('Improved keep_rate', keep_rate=0.65)
```

---

## 📖 核心参考

### Karpathy 的名言

> **"A small improvement that adds ugly complexity is not worth it."**

### autoresearch 的核心设计

1. **固定时间预算**：所有实验 5 分钟
2. **Git 版本控制**：每次改进 commit
3. **简洁性准则**：小改进 + 大复杂度 = 不值得
4. **program.md**：Markdown 格式的 Agent 手册

### Curriculum-Forge 的实现

1. **program.md**：分层的工作手册
2. **TimeBudget**：可配置的时间预算
3. **ComplexityChecker**：量化评估复杂度
4. **GitManager**：可选的版本控制

---

## 🎯 与 Curriculum-Forge 的融合

### 完整工作流

```
autoresearch 风格：
Agent 读取 program.md
  → 修改 train.py
  → 训练 5 分钟
  → 对比 val_bpb
  → 变好？git commit ✅
  → 变差？git reset ❌
  → 循环

Curriculum-Forge 实现：
Agent A 读取 program.md
  → 分析进度 → 生成环境
  → Agent B 读取 program.md
  → 运行实验（固定时间预算）
  → 计算奖励（简洁性评估）
  → 更新模型（GRPO）
  → 记录结果（Git commit）
  → 循环
```

---

## 📊 项目统计

| 指标 | 数值 |
|------|------|
| 新增文件 | 6 个 |
| 新增代码 | ~35KB |
| program.md | 3 个（~20KB）|
| 工具类 | 3 个（~22KB）|
| 命令行参数 | 3 个（--exp-time, --iter-time, --no-time-budget）|

---

## 🎓 学习收获

### 从 autoresearch 学到的

1. **简洁性优于复杂性**
   - 简单设计可以走得更远
   - 避免过度工程

2. **固定预算确保公平**
   - 所有实验在相同条件下对比
   - 避免某些配置"作弊"

3. **Git 是最好的实验记录**
   - 完整的历史
   - 轻松回溯

4. **Markdown 是最好的文档**
   - 人类可读
   - AI 可理解

---

## ⏭️ 下一步

### 可选集成

1. **main.py 集成 Git**
   - 添加 --git 参数启用
   - 自动 commit 好的结果

2. **Agent B 集成简洁性检查**
   - 在添加新功能前评估
   - 记录复杂度-改进比

3. **性能对比集成时间预算**
   - 确保对比公平
   - 记录超时情况

---

## 📚 参考资源

- **autoresearch**：https://github.com/karpathy/autoresearch
- **awesome-autoresearch**：https://github.com/WecoAI/awesome-autoresearch
- **Karpathy's Blog**：https://karpathy.ai

---

**最后更新**：2026-03-29 10:30 GMT+8

**项目状态**：🟢 **autoresearch 灵感集成完成** ✅
