# Curriculum-Forge

<div align="center">

**AI Agent Town — 多 Agent 协作治理系统**

[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GStack](https://img.shields.io/badge/Framework-GStack-green.svg)](https://github.com/openclaw/openclaw)

*构建 AI Agent 协作、学习、进化的"小镇"*

[English](README.md) | [中文](README_CN.md)

</div>

---

## 📖 项目简介

Curriculum-Forge 正在演进为 **AI Agent Town** —— 一个多 Agent 协作系统，让多个 AI Agent 在其中协作、学习、进化，共同完成复杂任务。

### 🎯 核心目标

- 🤝 **多 Agent 协作**：多个 Agent 按角色分工，协同完成任务
- 🧠 **自我演进**：Agent 能够从经验中学习，持续改进
- 🏛️ **协作治理**：建立治理机制，管理 Agent 行为和资源
- 📚 **知识沉淀**：将经验转化为可复用的知识库

### 🚀 当前进展

| 阶段 | 状态 | 内容 |
|------|------|------|
| Phase 1 | ✅ 完成 | 知识层基础（Syzygy Vault + Experience Generator） |
| Phase 2 | 🚧 进行中 | Stella 记忆增强 |
| Phase 3 | 📋 计划中 | 治理层（Keeper、Mayor、Front Desk） |

---

## 🏗️ 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                        AI Agent Town                         │
├─────────────────────────────────────────────────────────────┤
│  用户层        │  Human Operators / API Clients              │
├─────────────────────────────────────────────────────────────┤
│  治理层        │  Keeper │ Mayor │ Front Desk                │
├─────────────────────────────────────────────────────────────┤
│  Agent 层      │  Teacher │ Learner │ Reviewer │ Stella      │
├─────────────────────────────────────────────────────────────┤
│  知识层        │  Syzygy Vault（Markdown + [[wikilink]]）     │
├─────────────────────────────────────────────────────────────┤
│  进化层        │  auto-research 风格的研究循环                 │
└─────────────────────────────────────────────────────────────┘
```

### 核心组件

| 组件 | 说明 |
|------|------|
| **Syzygy Vault** | 知识库存储，Markdown 格式 + 双向链接 |
| **Experience Generator** | 从任务执行生成经验页 |
| **Stella** | 记忆增强型 Agent，检索历史经验辅助决策 |
| **Keeper** | 资源管理（任务调度、负载均衡） |
| **Mayor** | 规则与声誉管理 |
| **Front Desk** | 用户交互前台 |

---

## 🔧 已实现功能

### Phase 1 - 知识层 ✅

```python
from syzygy_core.knowledge import SyzygyVault, ExperienceGenerator

# 创建知识库
vault = SyzygyVault("~/agent_town/vault")

# 生成经验页
generator = ExperienceGenerator(vault)
exp = generator.generate(task, result)

# 检索历史经验
results = vault.search_by_tags(["error-handling", "retry"])

# 知识图谱可视化
print(vault.ascii_graph("task_123"))
```

**测试覆盖**：9/9 tests passing

---

## 📚 技术栈

| 类别 | 技术 |
|------|------|
| **语言** | Python 3.7+ |
| **Web 框架** | FastAPI |
| **异步运行时** | asyncio |
| **知识库** | Markdown + [[wikilink]] |
| **认证** | API Key + JWT |
| **部署** | Docker + K8s + Helm |

---

## 🚀 快速开始

### 安装

```bash
# 克隆项目
git clone https://github.com/lanaiconnan/Curriculum-Forge.git
cd Curriculum-Forge

# 安装依赖
pip install -r requirements.txt
```

### 启动 Gateway

```bash
# 开发模式
python runtimes/gateway.py

# 生产模式（Docker）
docker-compose up -d
```

### CLI 工具

```bash
# 文档健康检查
python cli.py garden

# 架构规则验证
python cli.py arch

# 查看系统状态
python cli.py status
```

---

## 🧪 测试

```bash
# 运行所有测试
pytest tests/ -v

# 单元测试
pytest tests/unit/ -v

# 集成测试
pytest tests/integration/ -v

# 覆盖率报告
pytest tests/ -v --cov=. --cov-report=html
```

**当前测试基线**：1080 passed, 1 skipped

---

## 📖 文档

| 文档 | 说明 |
|------|------|
| [架构设计](AI_AGENT_TOWN_ARCHITECTURE.md) | AI Agent Town 完整架构蓝图 |
| [API 文档](docs/GATEWAY_API_CN.md) | Gateway REST API |
| [部署指南](docs/DEPLOYMENT_CN.md) | Docker/K8s 部署 |
| [安全指南](docs/SECURITY_GUIDE_CN.md) | 认证与权限 |
| [配置说明](docs/CONFIG_CN.md) | 配置参数详解 |

---

## 🔄 项目演进

Curriculum-Forge 最初是一个 **Curriculum Learning for Tool-Using RL Agents** 框架，现在正在演进为 **AI Agent Town** 多 Agent 协作系统。

### 历史版本

| 版本 | 定位 |
|------|------|
| v1.0 | 双 Agent RL 训练框架 |
| v2.0 | 多 Agent 协作治理系统（进行中） |

---

## 🤝 贡献

欢迎贡献！请查看 [Contributing Guide](CONTRIBUTING.md) 了解详情。

---

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件。

---

## 🙏 致谢

- **Karpathy** - auto-research 项目启发
- **OpenAI** - Harness Engineering 理念
- **Anthropic** - Claude 与 AI 安全研究
- **Letta/MemGPT** - Memory Block 架构

---

<div align="center">

**Built with ❤️ using the GStack Framework**

</div>
