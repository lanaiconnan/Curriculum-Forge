# Curriculum-Forge

<div align="center">

**Curriculum Learning for Tool-Using Reinforcement Learning Agents**

[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GStack](https://img.shields.io/badge/Framework-GStack-green.svg)](https://github.com/openclaw/openclaw)

*Building AI agents that learn to use tools through structured curricula*

[English](README.md) | [中文](README_CN.md)

</div>

---

## 📖 Overview

Curriculum-Forge is a **Dual-Agent Reinforcement Learning Framework** for training AI agents to use tools effectively through curriculum learning. Inspired by cutting-edge research from OpenAI, Anthropic, and the AutoDidact project.

### 🎯 Key Features

- **Dual-Agent Architecture**: Agent A (Generator/Analyst) + Agent B (Learner/Executor)
- **ToolRL Integration**: Reinforcement learning for tool selection and parameter generation
- **Curriculum Learning**: Progressive difficulty scaling for efficient training
- **Harness Engineering**: DocGardening + ArchitectureRuleEngine for maintainability
- **Letta-style Memory**: Structured memory blocks (Core/Archival/Recall)
- **Verification Mechanism**: SelfVerifier + ConfidenceTracker + EnhancedRewardCalculator

---

## 🏗️ Architecture

```
Curriculum-Forge
├── agent_a/                 # Generator Agent
│   ├── generator.py         # Environment generation
│   └── analyst.py           # Progress analysis
├── agent_b/                 # Learner Agent
│   └── learner.py           # Experiment execution
├── rl/                      # Reinforcement Learning
│   ├── trainer.py           # GRPO/GAE trainer
│   ├── self_verifier.py     # Verification mechanism
│   └── enhanced_reward_calculator.py
├── tools/                   # Tool Layer
│   ├── git.py              # Git operations
│   ├── moon.py             # Moon API
│   └── memory.py           # Letta-style Memory
├── shared/                  # Shared Components
│   ├── scratchpad.py       # Structured logging
│   ├── time_budget.py      # Time constraints
│   ├── doc_gardening.py    # Document maintenance
│   └── architecture_engine.py
└── tests/                   # Test Suite
    └── unit/
```

---

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/curriculum-forge.git
cd curriculum-forge

# Install dependencies
pip install -r requirements.txt
```

### Basic Usage

```bash
# Run dual-agent training (default 10 iterations)
python main.py --mode dual --iterations 10

# Run single agent mode (for testing)
python main.py --mode single --iterations 5

# Use GAE instead of GRPO
python main.py --mode dual --iterations 10 --no-grpo

# Custom time budget
python main.py --mode dual --iterations 10 --exp-time 300 --iter-time 1800
```

### CLI Commands

```bash
# Show program.md for an agent
python cli.py show agent_a

# Check if an action is allowed
python cli.py check agent_a "modify:agent_b/learner.py"

# Show system status
python cli.py status

# Show verification statistics
python cli.py verification

# Show confidence tracking
python cli.py confidence

# DocGardening check
python cli.py garden

# Architecture validation
python cli.py arch
```

---

## 🧪 Testing

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run with coverage
pytest tests/unit/ -v --cov=. --cov-report=html

# Run specific test file
pytest tests/unit/test_memory.py -v
```

---

## 📚 Documentation

- [Quick Start Guide](docs/QUICKSTART.md)
- [API Reference](docs/API.md)
- [Examples](docs/EXAMPLES.md)
- [Architecture Guide](docs/ARCHITECTURE.md)
- [中文文档](docs/QUICKSTART_CN.md)

---

## 🔬 Research Background

This project implements ideas from several research papers:

- **Curriculum Learning**: Bengio et al. (2009)
- **Tool Learning**: Qin et al. (2023) - Tool Learning with Foundation Models
- **GRPO**: Group Relative Policy Optimization
- **AutoDidact**: Self-improving AI systems
- **Letta/MemGPT**: Memory management for LLM agents

---

## 🤝 Contributing

Contributions are welcome! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **OpenAI** - For the Harness Engineering insights
- **Anthropic** - For Claude and AI safety research
- **Letta** - For the Memory Block architecture
- **AutoDidact** - For self-improvement concepts

---

<div align="center">

**Built with ❤️ using the GStack Framework**

</div>
