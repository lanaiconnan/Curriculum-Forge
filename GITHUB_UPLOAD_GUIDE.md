# GitHub 上传指南

## 📦 项目已准备就绪

Curriculum-Forge 项目已完成 Git 初始化和首次提交。

### ✅ 已完成的工作

- Git 仓库初始化
- .gitignore 配置
- MIT LICENSE
- 完整的 README.md
- requirements.txt
- CI/CD 配置
- 50 个文件，14095 行代码

---

## 🚀 上传到 GitHub 的步骤

### 方法 1: 使用 GitHub Desktop

1. 打开 GitHub Desktop
2. File → Add Local Repository
3. 选择路径: `~/.qclaw/workspace/dual-agent-tool-rl`
4. 点击 "Publish repository"
5. 填写仓库名称: `curriculum-forge`
6. 选择 Public 或 Private
7. 点击 "Publish repository"

### 方法 2: 使用 GitHub 网页

1. 访问 https://github.com/new
2. 创建新仓库:
   - Repository name: `curriculum-forge`
   - Description: `Curriculum Learning for Tool-Using RL Agents`
   - 选择 Public
   - **不要**勾选 "Initialize with README" (已有)
3. 创建后，复制仓库 URL

然后在终端执行:

```bash
cd ~/.qclaw/workspace/dual-agent-tool-rl
git remote add origin https://github.com/YOUR_USERNAME/curriculum-forge.git
git branch -M main
git push -u origin main
```

### 方法 3: 使用 SSH (推荐)

如果你已配置 SSH key:

```bash
cd ~/.qclaw/workspace/dual-agent-tool-rl
git remote add origin git@github.com:YOUR_USERNAME/curriculum-forge.git
git branch -M main
git push -u origin main
```

---

## 📊 项目统计

| 指标 | 数值 |
|------|------|
| Python 文件 | 40 个 |
| 文档文件 | 20 个 |
| 测试文件 | 5 个 |
| 总代码行数 | 14,095 |
| 测试覆盖 | 62+ tests |

---

## 🏆 项目亮点

### 核心功能

1. **Dual-Agent Architecture**
   - Agent A: Generator/Analyst
   - Agent B: Learner/Executor

2. **ToolRL Integration**
   - GRPO/GAE Training
   - Reward Calculation

3. **Curriculum Learning**
   - Progressive Difficulty
   - Dynamic Scaling

4. **Harness Engineering**
   - DocGardening
   - ArchitectureRuleEngine

5. **Letta-style Memory**
   - Core Memory
   - Archival Memory
   - Recall Memory

6. **Verification Mechanism**
   - SelfVerifier
   - ConfidenceTracker
   - EnhancedRewardCalculator

---

## 📝 仓库描述建议

```
🎓 Curriculum-Forge - A Dual-Agent RL Framework for Training Tool-Using AI Agents

Features: ToolRL, Curriculum Learning, Harness Engineering, Letta Memory, Self-Verification

Built with GStack Framework | MIT License | Python 3.7+
```

---

## 🏷️ 建议的 Topics

- artificial-intelligence
- reinforcement-learning
- curriculum-learning
- tool-learning
- llm
- agents
- grpo
- autodidact
- letta
- memgpt
- gstack

---

## 🔗 相关链接

- OpenAI: https://openai.com
- Anthropic: https://anthropic.com
- Letta: https://letta.com
- GStack: https://github.com/openclaw/openclaw
