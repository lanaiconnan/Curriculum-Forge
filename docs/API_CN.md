# 📚 API 文档

本文档提供 Curriculum-Forge 核心模块的完整 API 参考。

---

## 📁 项目结构

```
curriculum-forge/
├── agent_a/          # Agent A - 环境生成器
│   ├── generator.py   # 核心生成器
│   └── analyst.py     # Analyst Agent
├── agent_b/          # Agent B - 学习者
│   └── learner.py     # 核心学习器
├── rl/               # 强化学习
│   ├── trainer.py     # RL 训练器
│   ├── evolution.py   # 进化算法
│   └── enhanced_reward_calculator.py  # 奖励计算器
├── shared/           # 共享模块
│   ├── scratchpad.py        # Scratchpad 日志
│   ├── human_feedback.py    # HumanFeedback
│   ├── local_llm.py        # 本地 LLM
│   ├── time_budget.py       # 时间预算
│   └── report_generator.py  # 报告生成
└── tools/            # 工具注册表
```

---

## 🤖 Agent A - 环境生成器

### agent_a.generator.AgentA

```python
from agent_a.generator import AgentA, AgentBProgress, TrainingEnvironment
```

#### 初始化

```python
AgentA(
    workspace: str = ".",
    scratchpad: Scratchpad = None,
    enable_analyst: bool = True,
    enable_human_feedback: bool = True
)
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| workspace | str | "." | 工作区路径 |
| scratchpad | Scratchpad | None | Scratchpad 实例 |
| enable_analyst | bool | True | 启用 Analyst Agent |
| enable_human_feedback | bool | True | 启用 HumanFeedback |

#### 方法

##### analyze_progress()

```python
def analyze_progress(self, results_tsv: str) -> AgentBProgress
```

分析 Agent B 的实验进度。

**参数：**
- `results_tsv`: 结果文件路径

**返回：**
- `AgentBProgress`: 包含 total_experiments, keep_rate, best_score 等

---

##### generate_environment()

```python
def generate_environment(self, progress: AgentBProgress) -> TrainingEnvironment
```

根据进度生成训练环境。

**参数：**
- `progress`: AgentBProgress 实例

**返回：**
- `TrainingEnvironment`: 训练环境配置

---

### agent_a.generator.TrainingEnvironment

```python
@dataclass
class TrainingEnvironment:
    id: str                           # 环境 ID
    name: str                         # 环境名称
    description: str                  # 描述
    tasks: List[Dict]                 # 任务列表
    difficulty: float                  # 难度 (0-1)
    available_tools: List[str]        # 可用工具
    tool_constraints: Dict            # 工具约束
    reward_config: Dict              # 奖励配置
```

---

## 📊 Agent B - 学习者

### agent_b.learner.AgentB

```python
from agent_b.learner import AgentB
```

#### 初始化

```python
AgentB(
    workspace: str = ".",
    tools: List = None,
    scratchpad: Scratchpad = None,
    max_experiment_time: int = 300
)
```

#### 方法

##### autoresearch_loop()

```python
def autoresearch_loop(
    self,
    environment: TrainingEnvironment,
    max_iterations: int = 5
) -> List[Dict]
```

运行自主研究循环。

**参数：**
- `environment`: TrainingEnvironment 实例
- `max_iterations`: 最大迭代次数

**返回：**
- `List[Dict]`: 实验结果列表

---

## 🧠 Analyst Agent

### agent_a.analyst.AnalystAgent

```python
from agent_a.analyst import AnalystAgent, AnalysisReport
```

#### 初始化

```python
AnalystAgent(scratchpad: Scratchpad = None)
```

#### 方法

##### analyze()

```python
def analyze(self, results: List[Dict[str, Any]]) -> AnalysisReport
```

执行完整分析。

**参数：**
- `results`: 实验结果列表

**返回：**
- `AnalysisReport`: 包含趋势分析、模式、异常、洞察

##### print_report()

```python
def print_report(self, report: AnalysisReport)
```

打印分析报告。

---

## 🧬 进化算法

### rl.evolution.EvolutionOptimizer

```python
from rl.evolution import EvolutionOptimizer, SelectionMethod
```

#### 初始化

```python
EvolutionOptimizer(
    population_size: int = 10,
    mutation_rate: float = 0.1,
    crossover_rate: float = 0.8,
    selection_method: SelectionMethod = SelectionMethod.TOURNAMENT,
    scratchpad: Scratchpad = None
)
```

#### 方法

##### evolve()

```python
def evolve(
    self,
    generations: int,
    fitness_func: Callable[[Dict], float],
    elite_size: int = 2
) -> List[EvolutionStats]
```

执行进化循环。

##### get_best_genotype()

```python
def get_best_genotype(self) -> Dict[str, Any]
```

获取最优基因型（超参数）。

##### print_summary()

```python
def print_summary(self)
```

打印种群摘要。

---

## 🤝 HumanFeedback

### shared.human_feedback.HumanFeedbackManager

```python
from shared.human_feedback import HumanFeedbackManager, FeedbackType, Priority
```

#### 初始化

```python
HumanFeedbackManager(
    workspace: str = ".",
    scratchpad: Scratchpad = None
)
```

#### 方法

##### request_guidance()

```python
def request_guidance(
    self,
    context: Dict,
    question: str = None,
    timeout: int = 30
) -> Optional[Feedback]
```

请求人类指导（交互式）。

##### add_constraint()

```python
def add_constraint(
    self,
    name: str,
    description: str,
    rule: Callable[[Dict], bool],
    priority: Priority = Priority.MEDIUM
) -> Constraint
```

添加约束条件。

##### validate_environment()

```python
def validate_environment(self, env: Dict) -> Tuple[bool, List[str]]
```

验证环境是否满足约束。

##### record_preference()

```python
def record_preference(
    self,
    key: str,
    value: Any,
    weight: float = 1.0
) -> UserPreference
```

记录用户偏好。

---

## 🔒 本地 LLM

### shared.local_llm.LocalLLMManager

```python
from shared.local_llm import LocalLLMManager, LLMConfig, Provider
```

#### 初始化

```python
LocalLLMManager(config: LLMConfig = None)
```

#### 方法

##### auto_detect()

```python
def auto_detect(self) -> Tuple[bool, str]
```

自动检测可用的本地模型。

##### check_health()

```python
def check_health(self) -> Tuple[bool, str]
```

检查 LLM 服务健康状态。

##### enable_offline_mode()

```python
def enable_offline_mode(self)
```

启用离线模式。

---

## 📝 Scratchpad 日志

### shared.scratchpad.ScratchpadManager

```python
from shared.scratchpad import ScratchpadManager
```

#### 方法

##### create()

```python
def create(self) -> Scratchpad
```

创建新的 Scratchpad 会话。

##### save_current()

```python
def save_current(self) -> str
```

保存当前 Scratchpad。

##### list_sessions()

```python
def list_sessions(self) -> List[str]
```

列出所有会话。

---

## 🧪 奖励计算器

### rl.enhanced_reward_calculator.EnhancedRewardCalculator

```python
from rl.enhanced_reward_calculator import EnhancedRewardCalculator
```

#### 方法

##### calculate()

```python
def calculate(self, trajectory: Dict) -> EnhancedReward
```

计算增强奖励。

##### get_verdict()

```python
def get_verdict(self, reward: EnhancedReward) -> str
```

获取判定结果 (excellent/good/fair/poor)。

##### get_feedback()

```python
def get_feedback(self, reward: EnhancedReward) -> str
```

获取反馈信息。

---

## ⚙️ RL 训练器

### rl.trainer.RLTrainer

```python
from rl.trainer import RLTrainer, RLConfig
```

#### 初始化

```python
RLTrainer(
    config: RLConfig = None,
    enable_evolution: bool = False
)
```

#### 方法

##### train_step()

```python
def train_step(
    self,
    results: List,
    use_grpo: bool = True
) -> Dict[str, Any]
```

执行训练步骤。

---

## 📋 数据类型

### AgentBProgress

```python
@dataclass
class AgentBProgress:
    total_experiments: int = 0    # 总实验数
    keep_rate: float = 0.0        # 保留率
    best_score: float = 0.0       # 最佳分数
    weak_areas: List[str] = []    # 弱点领域
```

### AnalysisReport

```python
@dataclass
class AnalysisReport:
    timestamp: str                          # 时间戳
    experiment_count: int                   # 实验数量
    trend_analysis: Dict[str, TrendAnalysis]  # 趋势分析
    patterns: List[Pattern]                # 模式列表
    anomalies: List[Anomaly]               # 异常列表
    insights: List[Insight]                # 洞察列表
    summary: str                           # 摘要
```

---

## 🔧 CLI 命令

| 命令 | 说明 |
|------|------|
| `python3 cli.py status` | 查看系统状态 |
| `python3 cli.py llm` | 查看 LLM 状态 |
| `python3 cli.py verification` | 查看验证统计 |
| `python3 cli.py confidence` | 查看置信度追踪 |
| `python3 cli.py log list` | 列出日志会话 |
| `python3 cli.py log show` | 查看最新日志 |
| `python3 cli.py show agent_a` | 查看 Agent A 手册 |
| `python3 cli.py show agent_b` | 查看 Agent B 手册 |

---

**更多示例请查看 [使用示例](EXAMPLES_CN.md)**
