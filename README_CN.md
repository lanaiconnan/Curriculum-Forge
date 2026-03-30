# Curriculum-Forge - 自主工具学习训练框架

<p align="center">
<img src="https://img.shields.io/badge/Python-3.7+-blue.svg" alt="Python">
<img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
<img src="https://img.shields.io/badge/Stars-560-yellow.svg" alt="Stars">
</p>

> 🔥 **基于 ToolRL 的双 Agent 自主学习系统**
> 
> Curriculum-Forge 是一个使用强化学习训练 Agent 自主使用工具的框架，灵感来自 [Karpathy 的 autoresearch](https://github.com/karpatrick/autoresearch) 项目。

---

## 📖 项目简介

Curriculum-Forge 是一个**自主工具学习训练框架**，使用**双 Agent 架构**和**强化学习**来训练 Agent 掌握工具使用技能。

### 核心特性

| 特性 | 说明 |
|------|------|
| 🤖 **双 Agent 架构** | Agent A 生成环境，Agent B 学习任务 |
| 📊 **GRPO 算法** | 组相对策略优化，稳定高效 |
| 📈 **课程学习** | 三阶段难度渐进（beginner → advanced）|
| 🔍 **Analyst Agent** | 趋势分析、模式识别、异常检测 |
| 🤝 **HumanFeedback** | 人类指导，可选参与 |
| 🧬 **Evolution** | 进化算法，超参数自动搜索 |
| 🔒 **本地运行** | Ollama/LM Studio 支持，离线模式 |

### 灵感来源

本项目参考了以下优秀开源项目：

| 项目 | Stars | 特点 |
|------|-------|------|
| [gpt-researcher](https://github.com/assafelovic/gpt-researcher) | 26k | 结构化报告、反思机制 |
| [SWE-agent](https://github.com/SWE-agent/SWE-agent) | 18.8k | 多模型支持 |
| [AgenticSeek](https://github.com/Fosowl/agenticSeek) | 25.7k | 本地化、离线模式 |
| [AgentLaboratory](https://github.com/Samualzu/MINI_AGENTS) | 5.4k | 端到端工作流 |
| [AutoDidact](https://github.com/dCaples/AutoDidact) | 685 | 自验证机制 |
| [OpenAlpha_Evolve](https://github.com/shyamsaktawat/OpenAlpha_Evolve) | 992 | 进化算法 |

---

## 🚀 快速开始

### 安装

```bash
# 克隆项目
git clone https://github.com/your-repo/curriculum-forge.git
cd curriculum-forge

# 无需安装依赖（纯标准库）
```

### 运行训练

```bash
# 基本训练
python3 main.py --mode dual --iterations 10

# 带验证和报告
python3 main.py --mode dual --iterations 5 --enable-verification

# 离线模式（无需 LLM）
python3 main.py --mode dual --offline
```

---

## 📚 文档目录

| 文档 | 说明 |
|------|------|
| [快速开始](docs/QUICKSTART.md) | 5 分钟快速上手 |
| [API 文档](docs/API.md) | 核心模块 API |
| [使用示例](docs/EXAMPLES.md) | 常见场景示例 |
| [架构设计](docs/ARCHITECTURE.md) | 系统设计说明 |

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Curriculum-Forge                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐   │
│  │  Agent A     │────▶│   RL Loop   │◀────│  Agent B    │   │
│  │  环境生成器  │     │   (GRPO)    │     │   学习者    │   │
│  └─────────────┘     └─────────────┘     └─────────────┘   │
│         │                   │                   │          │
│         ▼                   ▼                   ▼          │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐   │
│  │  Analyst    │     │  Evolution  │     │ Scratchpad  │   │
│  │  智能分析   │     │   进化优化  │     │   日志     │   │
│  └─────────────┘     └─────────────┘     └─────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              HumanFeedback (可选)                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎯 核心模块

### Agent A - 环境生成器

```python
from agent_a.generator import AgentA

agent_a = AgentA(workspace='.')
progress = agent_a.analyze_progress('results.tsv')
env = agent_a.generate_environment(progress)
```

### Agent B - 学习者

```python
from agent_b.learner import AgentB

agent_b = AgentB(workspace='.', tools=tool_registry)
results = agent_b.autoresearch_loop(env, max_iterations=5)
```

### RL 训练器

```python
from rl.trainer import RLTrainer

trainer = RLTrainer(enable_evolution=True)
stats = trainer.train_step(results, use_grpo=True)
```

---

## 📊 课程学习

Curriculum-Forge 使用**三阶段课程学习**策略：

| 阶段 | Keep Rate | 难度 | 奖励尺度 |
|------|-----------|------|----------|
| Beginner | < 30% | 0.3 | 1.0 |
| Intermediate | 30% - 60% | 0.5 | 0.7 |
| Advanced | > 60% | 0.7 | 0.5 |

---

## 🔧 CLI 工具

```bash
# 查看系统状态
python3 cli.py status

# 查看 LLM 状态
python3 cli.py llm

# 查看验证统计
python3 cli.py verification

# 查看 Scratchpad 日志
python3 cli.py log list
python3 cli.py log show

# 查看程序手册
python3 cli.py show agent_a
python3 cli.py show agent_b
```

---

## 📝 许可

MIT License

---

## 🙏 致谢

- [Karpathy 的 autoresearch](https://github.com/karpathy/autoresearch)
- [AgentLaboratory](https://github.com/Samualzu/MINI_AGENTS)
- [gpt-researcher](https://github.com/assafelovic/gpt-researcher)
- 所有贡献者和灵感来源
