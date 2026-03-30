# 📖 使用示例

本文档提供 Curriculum-Forge 的常见使用场景示例。

---

## 1. 基础训练

### 1.1 基本训练流程

```python
"""基础训练示例"""
import sys
sys.path.insert(0, '/path/to/curriculum-forge')

from agent_a.generator import AgentA
from agent_b.learner import AgentB
from rl.trainer import RLTrainer

# 1. 创建组件
agent_a = AgentA(workspace='.')
agent_b = AgentB(workspace='.', tools=[])
trainer = RLTrainer()

# 2. 分析进度
progress = agent_a.analyze_progress('results.tsv')

# 3. 生成环境
env = agent_a.generate_environment(progress)

# 4. 运行实验
results = agent_b.autoresearch_loop(env, max_iterations=5)

# 5. 训练
stats = trainer.train_step(results)

print(f"Total reward: {stats['total_reward']:.2f}")
print(f"Method: {stats['method']}")
```

---

## 2. Analyst Agent

### 2.1 独立使用 Analyst

```python
"""Analyst Agent 使用示例"""
from agent_a.analyst import AnalystAgent

# 创建 Analyst
analyst = AnalystAgent()

# 准备实验结果
results = [
    {'id': '1', 'reward': 0.6, 'status': 'keep', 'tools_used': ['git', 'moon']},
    {'id': '2', 'reward': 0.7, 'status': 'keep', 'tools_used': ['git', 'moon']},
    {'id': '3', 'reward': 0.5, 'status': 'discard', 'tools_used': ['moon']},
    {'id': '4', 'reward': 0.75, 'status': 'keep', 'tools_used': ['git', 'moon']},
    {'id': '5', 'reward': 0.8, 'status': 'keep', 'tools_used': ['git', 'moon']},
]

# 执行分析
report = analyst.analyze(results)

# 打印报告
analyst.print_report(report)

# 访问分析结果
print(f"\n趋势: {report.trend_analysis['reward'].direction.value}")
print(f"模式数: {len(report.patterns)}")
print(f"异常数: {len(report.anomalies)}")
print(f"洞察数: {len(report.insights)}")
```

---

## 3. HumanFeedback

### 3.1 添加约束和偏好

```python
"""HumanFeedback 使用示例"""
from shared.human_feedback import HumanFeedbackManager, Priority

# 创建管理器
manager = HumanFeedbackManager(workspace='.')

# 添加约束
manager.add_preset_constraint(
    name='min_keep_rate',
    description='Keep rate must be > 0.5',
    rule_dict={'keep_rate': 0.5},
    priority=Priority.HIGH
)

# 记录偏好
manager.record_preference(
    key='preferred_stage',
    value='intermediate',
    weight=1.5
)

# 验证环境
env = {'keep_rate': 0.6, 'difficulty': 0.5}
valid, failures = manager.validate_environment(env)

if valid:
    print("环境验证通过！")
else:
    print(f"验证失败: {failures}")

# 应用约束
modified_env = manager.apply_constraints_to_environment(env)
print(f"修改后的环境: {modified_env}")

# 获取摘要
summary = manager.get_feedback_summary()
print(f"总反馈数: {summary['total_feedback']}")
```

### 3.2 请求人类指导

```python
"""请求人类指导示例"""
from shared.human_feedback import HumanFeedbackManager

manager = HumanFeedbackManager()

# 请求指导（交互式）
feedback = manager.request_guidance(
    context={
        'stage': 'beginner',
        'keep_rate': 0.3,
        'best_score': 0.65
    },
    question='Should we increase difficulty?',
    timeout=30
)

if feedback:
    print(f"收到反馈: {feedback.content}")
```

---

## 4. 进化算法

### 4.1 超参数优化

```python
"""进化算法使用示例"""
from rl.evolution import EvolutionOptimizer, SelectionMethod

# 创建优化器
optimizer = EvolutionOptimizer(
    population_size=10,
    mutation_rate=0.1,
    crossover_rate=0.8,
    selection_method=SelectionMethod.TOURNAMENT
)

# 定义适应度函数
def fitness_func(genotype):
    """
    模拟评估超参数组合
    实际使用时应运行真实训练
    """
    lr = genotype['learning_rate']
    rs = genotype['reward_scale']
    
    # 模拟：学习率和奖励尺度的组合效果
    fitness = (lr / 0.1) * (rs / 1.5)
    
    return fitness

# 运行进化
print("开始进化优化...")
history = optimizer.evolve(
    generations=10,
    fitness_func=fitness_func,
    elite_size=2
)

# 获取最优超参数
best_genotype = optimizer.get_best_genotype()
print(f"\n最优超参数:")
for param, value in best_genotype.items():
    print(f"  {param}: {value:.4f}")

# 打印进化历史
optimizer.print_history()

# 打印最终摘要
optimizer.print_summary()
```

---

## 5. 本地 LLM

### 5.1 自动检测和连接

```python
"""本地 LLM 使用示例"""
from shared.local_llm import LocalLLMManager, LLMMessage

# 创建管理器
manager = LocalLLMManager()

# 自动检测
success, msg = manager.auto_detect()

if success:
    print(f"检测成功: {msg}")
else:
    print(f"检测失败: {msg}")
    print("使用离线模式...")

# 检查健康状态
healthy, status = manager.check_health()
print(f"健康状态: {status}")

# 发送聊天请求
messages = [
    LLMMessage(role='system', content='You are a helpful assistant.'),
    LLMMessage(role='user', content='What is the best learning rate?')
]

response = manager.chat(messages)

if response.success:
    print(f"响应: {response.content}")
    print(f"延迟: {response.latency_ms:.2f}ms")
else:
    print(f"错误: {response.error}")
```

### 5.2 离线模式

```python
"""离线模式示例"""
from shared.local_llm import LocalLLMManager, OfflineSimulator

# 启用离线模式
manager = LocalLLMManager()
manager.enable_offline_mode()

# 模拟 LLM 响应
response = OfflineSimulator.simulate_llm_response("test prompt")
print(f"模拟响应: {response}")

# 获取模拟奖励
reward = OfflineSimulator.get_simulated_reward()
print(f"模拟奖励: {reward:.2f}")
```

---

## 6. Scratchpad 日志

### 6.1 记录和查看

```python
"""Scratchpad 使用示例"""
from shared.scratchpad import ScratchpadManager

# 创建管理器
manager = ScratchpadManager(base_dir='.scratchpad')

# 创建新会话
scratchpad = manager.create()

# 记录思考
scratchpad.log_thinking(
    "分析实验结果，keep_rate 偏低",
    confidence=0.85
)

# 记录工具调用
scratchpad.log_tool_call('git', {'command': 'commit', 'message': 'fix'})

# 记录奖励
scratchpad.log_reward(
    total=0.75,
    breakdown={'rformat': 1.0, 'rname': 0.8}
)

# 记录结果
scratchpad.log_result(
    status='keep',
    message='Experiment successful',
    metrics={'score': 0.85}
)

# 保存
filepath = manager.save_current()
print(f"保存到: {filepath}")

# 列出所有会话
sessions = manager.list_sessions()
print(f"所有会话: {sessions}")
```

---

## 7. 完整训练循环

### 7.1 带所有功能的训练

```python
"""完整训练循环示例"""
import sys
sys.path.insert(0, '/path/to/curriculum-forge')

from agent_a.generator import AgentA
from agent_b.learner import AgentB
from rl.trainer import RLTrainer
from agent_a.analyst import AnalystAgent
from shared.human_feedback import HumanFeedbackManager
from shared.scratchpad import ScratchpadManager
from shared.report_generator import ReportGenerator

# 初始化所有组件
scratchpad_manager = ScratchpadManager(base_dir='.scratchpad')
scratchpad = scratchpad_manager.create()

agent_a = AgentA(
    workspace='.',
    scratchpad=scratchpad,
    enable_analyst=True,
    enable_human_feedback=True
)
agent_b = AgentB(workspace='.', tools=[], scratchpad=scratchpad)
trainer = RLTrainer(enable_evolution=False)

all_results = []

# 训练循环
for epoch in range(5):
    print(f"\n=== Epoch {epoch + 1} ===")
    
    # 1. 分析进度
    progress = agent_a.analyze_progress('results.tsv')
    
    # 2. 生成环境
    env = agent_a.generate_environment(progress)
    print(f"Generated: {env.name} (difficulty={env.difficulty})")
    
    # 3. 运行实验
    results = agent_b.autoresearch_loop(env, max_iterations=3)
    all_results.extend(results)
    
    # 4. 训练
    stats = trainer.train_step(results)
    print(f"Reward: {stats['avg_reward']:.2f}")
    
    # 5. 分析（每 2 轮）
    if agent_a.last_analysis:
        print(f"Trend: {agent_a.last_analysis.trend_analysis.get('reward', {}).direction.value}")

# 生成报告
generator = ReportGenerator()
report = generator.generate(all_results, {})
generator.save(report, format='markdown')

# 保存 Scratchpad
scratchpad_manager.save_current()

print("\n训练完成！")
```

---

## 8. 自定义奖励计算

### 8.1 使用增强奖励计算器

```python
"""增强奖励计算器使用示例"""
from rl.enhanced_reward_calculator import EnhancedRewardCalculator

# 创建计算器
calc = EnhancedRewardCalculator()

# 准备轨迹
trajectory = {
    'predicted_tools': ['git', 'moon'],
    'ground_truth_tools': ['git', 'moon'],
    'predicted_params': {'repo': 'test'},
    'ground_truth_params': {'repo': 'test', 'msg': 'fix'},
}

# 计算奖励
reward = calc.calculate(trajectory)

# 获取判定
verdict = calc.get_verdict(reward)
print(f"判定: {verdict}")

# 获取反馈
print(calc.get_feedback(reward))

# 获取置信度摘要
summary = calc.get_confidence_summary()
if summary.get('available'):
    print(f"平均置信度: {summary['average']:.1%}")
    print(f"趋势: {summary['trend']}")
```

---

**更多问题？请查看 [API 文档](API_CN.md) 或提交 Issue！**
