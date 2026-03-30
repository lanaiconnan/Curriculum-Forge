"""Evolution Algorithm - 进化优化

来自 OpenAlpha_Evolve 的灵感：
- 种群管理
- 适应度评估
- 遗传操作（交叉、变异、选择）
- 自适应参数
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable, Tuple
from datetime import datetime
from enum import Enum
import random
import copy
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from shared.scratchpad import Scratchpad
    SCRATCHPAD_AVAILABLE = True
except ImportError:
    SCRATCHPAD_AVAILABLE = False
    Scratchpad = None


class SelectionMethod(Enum):
    """选择方法"""
    TOURNAMENT = "tournament"       # 竞标赛选择
    ROULETTE = "roulette"          # 轮盘赌选择
    RANK = "rank"                  # 排名选择
    ELITISM = "elitism"            # 精英选择


@dataclass
class Individual:
    """个体（Agent 候选）"""
    id: str
    genotype: Dict[str, Any]       # 基因型（超参数）
    fitness: float = 0.0           # 适应度
    age: int = 0                   # 年龄（代数）
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'genotype': self.genotype,
            'fitness': self.fitness,
            'age': self.age,
            'created_at': self.created_at,
        }


@dataclass
class EvolutionStats:
    """进化统计"""
    generation: int
    best_fitness: float
    avg_fitness: float
    worst_fitness: float
    diversity: float              # 种群多样性
    best_individual: Individual = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'generation': self.generation,
            'best_fitness': self.best_fitness,
            'avg_fitness': self.avg_fitness,
            'worst_fitness': self.worst_fitness,
            'diversity': self.diversity,
            'best_individual': self.best_individual.to_dict() if self.best_individual else None,
            'timestamp': self.timestamp,
        }


class EvolutionOptimizer:
    """
    进化优化器
    
    核心功能：
    1. 种群管理 - 维护多个 Agent 候选
    2. 适应度评估 - 评估每个 Agent 的性能
    3. 遗传操作 - 交叉、变异、选择
    4. 自适应参数 - 动态调整超参数
    """
    
    def __init__(
        self,
        population_size: int = 10,
        mutation_rate: float = 0.1,
        crossover_rate: float = 0.8,
        selection_method: SelectionMethod = SelectionMethod.TOURNAMENT,
        scratchpad: Scratchpad = None,
    ):
        """
        初始化进化优化器
        
        Args:
            population_size: 种群大小
            mutation_rate: 变异率
            crossover_rate: 交叉率
            selection_method: 选择方法
            scratchpad: Scratchpad 日志实例
        """
        self.population_size = population_size
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.selection_method = selection_method
        self.scratchpad = scratchpad
        
        # 种群
        self.population: List[Individual] = []
        self.generation = 0
        self.history: List[EvolutionStats] = []
        
        # 基因型模板（超参数范围）
        self.genotype_template = {
            'learning_rate': (0.001, 0.1),
            'reward_scale': (0.5, 2.0),
            'difficulty_increment': (0.05, 0.2),
            'keep_rate_threshold': (0.3, 0.7),
        }
    
    def _log_thinking(self, thought: str, confidence: float = None):
        """记录思考日志"""
        if self.scratchpad:
            self.scratchpad.log_thinking(
                thought=thought,
                confidence=confidence,
                context='Evolution - 进化优化'
            )
    
    # ========== 种群初始化 ==========
    
    def initialize_population(self):
        """初始化种群"""
        self.population = []
        
        for i in range(self.population_size):
            genotype = self._generate_random_genotype()
            individual = Individual(
                id=f"ind_{self.generation}_{i}",
                genotype=genotype,
            )
            self.population.append(individual)
        
        self._log_thinking(
            f'初始化种群: {self.population_size} 个个体',
            confidence=0.9
        )
    
    def _generate_random_genotype(self) -> Dict[str, Any]:
        """生成随机基因型"""
        genotype = {}
        
        for param, (min_val, max_val) in self.genotype_template.items():
            if isinstance(min_val, float):
                genotype[param] = random.uniform(min_val, max_val)
            else:
                genotype[param] = random.randint(min_val, max_val)
        
        return genotype
    
    # ========== 适应度评估 ==========
    
    def evaluate_fitness(
        self,
        fitness_func: Callable[[Dict[str, Any]], float]
    ):
        """
        评估种群适应度
        
        Args:
            fitness_func: 适应度函数 (genotype) -> fitness
        """
        for individual in self.population:
            try:
                individual.fitness = fitness_func(individual.genotype)
            except Exception as e:
                self._log_thinking(f'适应度评估失败: {e}', confidence=0.5)
                individual.fitness = 0.0
        
        self._log_thinking(
            f'适应度评估完成: {len(self.population)} 个个体',
            confidence=0.9
        )
    
    # ========== 遗传操作 ==========
    
    def select_parents(self, num_parents: int = 2) -> List[Individual]:
        """
        选择父代
        
        Args:
            num_parents: 选择数量
        
        Returns:
            List[Individual]: 选中的个体
        """
        if self.selection_method == SelectionMethod.TOURNAMENT:
            return self._tournament_selection(num_parents)
        elif self.selection_method == SelectionMethod.ROULETTE:
            return self._roulette_selection(num_parents)
        elif self.selection_method == SelectionMethod.RANK:
            return self._rank_selection(num_parents)
        else:
            return self._elitism_selection(num_parents)
    
    def _tournament_selection(self, num_parents: int) -> List[Individual]:
        """竞标赛选择"""
        parents = []
        tournament_size = max(2, self.population_size // 5)
        
        for _ in range(num_parents):
            tournament = random.sample(self.population, tournament_size)
            winner = max(tournament, key=lambda x: x.fitness)
            parents.append(winner)
        
        return parents
    
    def _roulette_selection(self, num_parents: int) -> List[Individual]:
        """轮盘赌选择"""
        # 计算适应度总和
        total_fitness = sum(max(0, ind.fitness) for ind in self.population)
        
        if total_fitness <= 0:
            return random.sample(self.population, num_parents)
        
        parents = []
        for _ in range(num_parents):
            pick = random.uniform(0, total_fitness)
            current = 0
            
            for individual in self.population:
                current += max(0, individual.fitness)
                if current >= pick:
                    parents.append(individual)
                    break
        
        return parents
    
    def _rank_selection(self, num_parents: int) -> List[Individual]:
        """排名选择"""
        sorted_pop = sorted(self.population, key=lambda x: x.fitness, reverse=True)
        
        # 计算排名权重
        weights = [self.population_size - i for i in range(self.population_size)]
        total_weight = sum(weights)
        
        parents = []
        for _ in range(num_parents):
            pick = random.uniform(0, total_weight)
            current = 0
            
            for i, individual in enumerate(sorted_pop):
                current += weights[i]
                if current >= pick:
                    parents.append(individual)
                    break
        
        return parents
    
    def _elitism_selection(self, num_parents: int) -> List[Individual]:
        """精英选择"""
        sorted_pop = sorted(self.population, key=lambda x: x.fitness, reverse=True)
        return sorted_pop[:num_parents]
    
    def crossover(self, parent1: Individual, parent2: Individual) -> Individual:
        """
        交叉操作
        
        Args:
            parent1: 父代 1
            parent2: 父代 2
        
        Returns:
            Individual: 子代
        """
        if random.random() > self.crossover_rate:
            # 不进行交叉，直接复制
            return copy.deepcopy(parent1)
        
        # 均匀交叉
        child_genotype = {}
        
        for param in self.genotype_template.keys():
            if random.random() < 0.5:
                child_genotype[param] = parent1.genotype[param]
            else:
                child_genotype[param] = parent2.genotype[param]
        
        child = Individual(
            id=f"ind_{self.generation}_{random.randint(0, 10000)}",
            genotype=child_genotype,
        )
        
        return child
    
    def mutate(self, individual: Individual) -> Individual:
        """
        变异操作
        
        Args:
            individual: 个体
        
        Returns:
            Individual: 变异后的个体
        """
        mutated = copy.deepcopy(individual)
        
        for param, (min_val, max_val) in self.genotype_template.items():
            if random.random() < self.mutation_rate:
                # 高斯变异
                current = mutated.genotype[param]
                std_dev = (max_val - min_val) * 0.1
                
                new_value = current + random.gauss(0, std_dev)
                new_value = max(min_val, min(max_val, new_value))
                
                mutated.genotype[param] = new_value
        
        return mutated
    
    # ========== 进化循环 ==========
    
    def evolve(
        self,
        generations: int,
        fitness_func: Callable[[Dict[str, Any]], float],
        elite_size: int = 2,
    ) -> List[EvolutionStats]:
        """
        执行进化循环
        
        Args:
            generations: 进化代数
            fitness_func: 适应度函数
            elite_size: 精英个体数量
        
        Returns:
            List[EvolutionStats]: 进化统计历史
        """
        # 初始化种群
        self.initialize_population()
        
        for gen in range(generations):
            self.generation = gen
            
            # 1. 评估适应度
            self.evaluate_fitness(fitness_func)
            
            # 2. 记录统计
            stats = self._record_stats()
            self.history.append(stats)
            
            self._log_thinking(
                f'Generation {gen}: best={stats.best_fitness:.4f}, '
                f'avg={stats.avg_fitness:.4f}, diversity={stats.diversity:.4f}',
                confidence=0.9
            )
            
            # 3. 选择精英
            sorted_pop = sorted(self.population, key=lambda x: x.fitness, reverse=True)
            elite = sorted_pop[:elite_size]
            
            # 4. 生成新种群
            new_population = elite.copy()
            
            while len(new_population) < self.population_size:
                # 选择父代
                parents = self.select_parents(2)
                
                # 交叉
                child = self.crossover(parents[0], parents[1])
                
                # 变异
                child = self.mutate(child)
                
                # 更新 ID 和年龄
                child.id = f"ind_{gen}_{len(new_population)}"
                child.age = gen
                
                new_population.append(child)
            
            # 5. 更新种群
            self.population = new_population[:self.population_size]
        
        return self.history
    
    def _record_stats(self) -> EvolutionStats:
        """记录统计信息"""
        fitnesses = [ind.fitness for ind in self.population]
        
        best_individual = max(self.population, key=lambda x: x.fitness)
        
        # 计算多样性（基因型差异）
        diversity = self._calculate_diversity()
        
        stats = EvolutionStats(
            generation=self.generation,
            best_fitness=max(fitnesses),
            avg_fitness=sum(fitnesses) / len(fitnesses),
            worst_fitness=min(fitnesses),
            diversity=diversity,
            best_individual=best_individual,
        )
        
        return stats
    
    def _calculate_diversity(self) -> float:
        """计算种群多样性"""
        if len(self.population) < 2:
            return 0.0
        
        # 计算基因型之间的平均差异
        total_diff = 0.0
        count = 0
        
        for i in range(len(self.population)):
            for j in range(i + 1, len(self.population)):
                diff = self._genotype_distance(
                    self.population[i].genotype,
                    self.population[j].genotype
                )
                total_diff += diff
                count += 1
        
        if count == 0:
            return 0.0
        
        return total_diff / count
    
    def _genotype_distance(self, g1: Dict[str, Any], g2: Dict[str, Any]) -> float:
        """计算两个基因型之间的距离"""
        distance = 0.0
        
        for param, (min_val, max_val) in self.genotype_template.items():
            if param in g1 and param in g2:
                # 归一化差异
                diff = abs(g1[param] - g2[param]) / (max_val - min_val)
                distance += diff
        
        return distance / len(self.genotype_template)
    
    # ========== 结果获取 ==========
    
    def get_best_individual(self) -> Individual:
        """获取最优个体"""
        return max(self.population, key=lambda x: x.fitness)
    
    def get_best_genotype(self) -> Dict[str, Any]:
        """获取最优基因型"""
        return self.get_best_individual().genotype
    
    def get_population_summary(self) -> Dict[str, Any]:
        """获取种群摘要"""
        fitnesses = [ind.fitness for ind in self.population]
        
        return {
            'population_size': len(self.population),
            'best_fitness': max(fitnesses),
            'avg_fitness': sum(fitnesses) / len(fitnesses),
            'worst_fitness': min(fitnesses),
            'diversity': self._calculate_diversity(),
            'generation': self.generation,
        }
    
    def print_summary(self):
        """打印摘要"""
        summary = self.get_population_summary()
        best = self.get_best_individual()
        
        print("\n" + "=" * 60)
        print("🧬 Evolution Optimizer Summary")
        print("=" * 60)
        
        print(f"\n📊 Population Statistics:")
        print(f"   Generation: {summary['generation']}")
        print(f"   Population size: {summary['population_size']}")
        print(f"   Best fitness: {summary['best_fitness']:.4f}")
        print(f"   Avg fitness: {summary['avg_fitness']:.4f}")
        print(f"   Worst fitness: {summary['worst_fitness']:.4f}")
        print(f"   Diversity: {summary['diversity']:.4f}")
        
        print(f"\n🏆 Best Individual:")
        print(f"   ID: {best.id}")
        print(f"   Fitness: {best.fitness:.4f}")
        print(f"   Genotype:")
        for param, value in best.genotype.items():
            print(f"      {param}: {value:.4f}")
        
        print("=" * 60)
    
    def print_history(self, limit: int = 10):
        """打印进化历史"""
        print("\n" + "=" * 60)
        print("📈 Evolution History")
        print("=" * 60)
        
        print(f"\n{'Gen':<5} {'Best':<10} {'Avg':<10} {'Worst':<10} {'Diversity':<10}")
        print("-" * 60)
        
        for stats in self.history[-limit:]:
            print(
                f"{stats.generation:<5} "
                f"{stats.best_fitness:<10.4f} "
                f"{stats.avg_fitness:<10.4f} "
                f"{stats.worst_fitness:<10.4f} "
                f"{stats.diversity:<10.4f}"
            )
        
        print("=" * 60)
