# 🚀 Curriculum-Forge 核心增强项目

> **项目日期**：2026-03-29  
> **目标**：加入 4 项立即可做的改进  
> **状态**：🚧 进行中

---

## 📋 项目概览

| # | 改进项 | 来源 | 状态 | 文件 |
|---|--------|------|------|------|
| 1 | 结构化报告生成 | gpt-researcher | ✅ | shared/report_generator.py |
| 2 | 反思机制 | gpt-researcher | ✅ | agent_b/reflector.py |
| 3 | 增强 RewardCalculator | AutoDidact | ✅ | rl/enhanced_reward_calculator.py |
| 4 | Scratchpad 日志 | dexter | ✅ | shared/scratchpad.py |

---

## 🎯 详细计划

### 【改进 1】结构化报告生成

**来源**：gpt-researcher

**目标**：自动生成格式化的实验报告

**设计**：
```python
class ReportGenerator:
    def generate(self, results, stats):
        return {
            'summary': self._generate_summary(results),
            'metrics': self._generate_metrics(stats),
            'recommendations': self._generate_recommendations(results),
            'next_steps': self._generate_next_steps(results),
        }
```

**状态**：🚧 进行中

---

### 【改进 2】反思机制

**来源**：gpt-researcher

**目标**：Agent 能够反思自己的行为并改进

**设计**：
```python
class Reflector:
    def reflect(self, results, stats):
        analysis = self._analyze(results)
        issues = self._identify_issues(analysis)
        improvements = self._propose_improvements(issues)
        return ReflectionResult(
            analysis=analysis,
            issues=issues,
            improvements=improvements,
        )
```

**状态**：⏳ 待开始

---

### 【改进 3】增强 RewardCalculator

**来源**：AutoDidact

**目标**：添加自验证机制，增强奖励计算

**设计**：
```python
class EnhancedRewardCalculator:
    def verify(self, trajectory):
        predictions = trajectory['predicted_tools']
        ground_truth = trajectory['ground_truth_tools']
        
        exact_match = predictions == ground_truth
        partial_match = len(set(predictions) & set(ground_truth)) / len(ground_truth)
        
        return {
            'exact_match': exact_match,
            'partial_match': partial_match,
            'confidence': self._calculate_confidence(trajectory),
        }
```

**状态**：⏳ 待开始

---

### 【改进 4】Scratchpad 日志

**来源**：dexter

**目标**：完整记录执行过程，便于调试和追溯

**设计**：
```python
class Scratchpad:
    def log(self, entry):
        with open(self.file_path, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    
    def log_thinking(self, thought, confidence=None):
        self.log({'type': 'thinking', 'thought': thought, 'confidence': confidence})
    
    def log_tool_call(self, tool, args, result):
        self.log({'type': 'tool_call', 'tool': tool, 'args': args, 'result': result})
```

**状态**：⏳ 待开始

---

## 📊 进度追踪

### Week 1（2026-03-29）
- [x] 项目计划
- [ ] 改进 1：报告生成器
- [ ] 改进 2：反思机制
- [ ] 改进 3：增强奖励
- [ ] 改进 4：Scratchpad

### Week 2
- [ ] 测试集成
- [ ] CLI 增强
- [ ] 文档编写

---

## 📁 输出文件

### 核心文件
- `shared/report_generator.py` - 报告生成器
- `agent_b/reflector.py` - 反思机制
- `rl/enhanced_reward_calculator.py` - 增强奖励
- `shared/scratchpad.py` - Scratchpad 日志

### 文档文件
- `ENHANCEMENTS_PROGRESS.md` - 本文件
- `REPORT_EXAMPLE.md` - 报告示例

---

**最后更新**：2026-03-29 11:47 GMT+8
