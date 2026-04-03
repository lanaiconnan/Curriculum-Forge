"""Experiment Execution Service

This service handles Agent B's core responsibility:
- Running experiments
- Collecting results
- Computing rewards

Based on the service-oriented architecture pattern.
"""

from typing import Any, Dict, List, Optional, Callable
from datetime import datetime
from dataclasses import dataclass, field
import logging
import time

from .base import ServiceBase, ServiceConfig, ServiceState
from .models import (
    TrainingEnvironment,
    ExperimentRecord,
    ExperimentStatus,
    LearningStage,
    ProgressMetrics,
    RewardBreakdown,
)
from .container import ServiceProvider
from .query_engine import (
    QueryEngine,
    QueryConfig,
    ToolRegistry,
    ToolDefinition,
    create_backend,
)
from .tools import (
    ManagedToolRegistry,
    ToolPermission,
    ToolResultFormatter,
    RateLimit,
)

logger = logging.getLogger(__name__)


class LearnerServiceConfig(ServiceConfig):
    """Configuration for LearnerService"""

    def __init__(
        self,
        name: str = "learner",
        workspace: str = ".",
        max_iterations: int = 5,
        max_duration: float = 300.0,
        keep_threshold: float = 0.5,
        llm_backend: str = "auto",
        llm_model: str = "claude-3-5-haiku-20241022",
        max_tokens: int = 1024,
        max_turns: int = 5,
        **kwargs
    ):
        super().__init__(name=name, **kwargs)
        self.workspace = workspace
        self.max_iterations = max_iterations
        self.max_duration = max_duration
        self.keep_threshold = keep_threshold
        self.llm_backend = llm_backend
        self.llm_model = llm_model
        self.max_tokens = max_tokens
        self.max_turns = max_turns


@dataclass
class ExperimentResult:
    """Result of a single experiment run"""
    success: bool
    reward: float
    reward_breakdown: RewardBreakdown
    duration: float
    tools_used: List[str]
    output: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class LearnerService(ServiceBase[LearnerServiceConfig]):
    """
    Service for running experiments.

    This is Agent B's core service. It:
    1. Takes an environment from EnvironmentService
    2. Runs experiments within that environment
    3. Computes rewards using RewardCalculator
    4. Returns experiment results

    Usage:
        provider = ServiceProvider()
        provider.configure(LearnerService, config)
        provider.start()

        learner = provider.get(LearnerService)
        results = learner.run_experiments(env)
    """

    def __init__(self, config: LearnerServiceConfig):
        super().__init__(config)
        self._results: List[ExperimentRecord] = []
        self._experiment_count = 0
        self._on_result: Optional[Callable[[ExperimentRecord], None]] = None
        self._query_engine: Optional[QueryEngine] = None

    def _build_query_engine(self, env: TrainingEnvironment) -> QueryEngine:
        """
        Build a QueryEngine for this environment.

        Uses ManagedToolRegistry with:
        - allow_list = env.available_tools (LLM only sees env tools)
        - rate_limits = per-tool limits based on stage
        - formatter = truncate at 2000 chars
        """
        backend = create_backend(
            backend_type=self.config.llm_backend,
            model=self.config.llm_model,
        )

        # Rate limits scale with difficulty
        calls_per_minute = max(5, int(20 * (1.0 - env.difficulty)))
        rate_limits = {
            tool: RateLimit(max_calls=calls_per_minute, window_seconds=60.0)
            for tool in env.available_tools
        }

        # Build managed registry: only env tools are visible + rate-limited
        registry = ManagedToolRegistry(
            permission=ToolPermission(
                allow_list=env.available_tools,
                rate_limits=rate_limits,
            ),
            formatter=ToolResultFormatter(max_length=2000, include_metadata=False),
        )

        for tool_name in env.available_tools:
            registry.register(ToolDefinition(
                name=tool_name,
                description=f"Execute {tool_name} operation",
                input_schema={
                    "type": "object",
                    "properties": {
                        "target": {"type": "string", "description": "Target of the operation"},
                        "params": {"type": "object", "description": "Additional parameters"},
                    },
                    "required": ["target"],
                },
                handler=lambda inp, tn=tool_name: self._execute_tool(tn, inp),
            ))

        stage_guidance = {
            "beginner": "Focus on basic tool usage. Use simple, direct approaches.",
            "intermediate": "Apply intermediate techniques. Consider parameter optimization.",
            "advanced": "Use advanced strategies. Optimize for efficiency and accuracy.",
        }
        guidance = stage_guidance.get(env.stage.value, "Complete the task efficiently.")

        system_prompt = (
            f"You are an AI agent completing tasks in a {env.stage.value} training environment.\n"
            f"{guidance}\n"
            f"Environment: {env.name}\n"
            f"Available tools: {', '.join(env.available_tools)}\n"
            f"Complete each task by calling the appropriate tool with correct parameters."
        )

        config = QueryConfig(
            system_prompt=system_prompt,
            max_tokens=self.config.max_tokens,
            max_turns=self.config.max_turns,
        )

        return QueryEngine(backend=backend, tools=registry, config=config)

    def _execute_tool(self, tool_name: str, inp: Dict[str, Any]) -> str:
        """Execute a tool and return result string"""
        target = inp.get("target", "")
        params = inp.get("params", {})
        logger.debug(f"Tool execution: {tool_name}(target={target}, params={params})")
        # In real deployment: call actual tool implementations
        return f"Tool '{tool_name}' executed on '{target}' with params {params}. Result: OK"

    def initialize(self) -> None:
        """Initialize the service"""
        logger.info(f"Initializing LearnerService in {self.config.workspace}")

    def start(self) -> None:
        """Start the service"""
        logger.info("LearnerService started")

    def stop(self) -> None:
        """Stop the service"""
        logger.info("LearnerService stopped")

    def set_result_handler(self, handler: Callable[[ExperimentRecord], None]) -> None:
        """Set a callback for when results are produced"""
        self._on_result = handler
    def compute_reward(
        self,
        tool_name: str,
        expected_tool: str,
        params: Dict[str, Any],
        expected_params: Dict[str, Any],
    ) -> RewardBreakdown:
        """
        Compute fine-grained reward.

        Based on ToolRL paper's reward design:
        - Rformat: {0, 1} for format correctness
        - Rname: {-1, 0, 1} for tool name match
        - Rparam: [-1, 1] for parameter match
        - Rvalue: [-1, 1] for value match

        Args:
            tool_name: Actual tool used
            expected_tool: Expected tool
            params: Actual parameters
            expected_params: Expected parameters

        Returns:
            RewardBreakdown with detailed scores
        """
        # Format reward
        rformat = 1.0 if tool_name and params else 0.0

        # Tool name match
        rname = 1.0 if tool_name == expected_tool else -1.0

        # Parameter match
        param_matches = 0
        param_total = max(len(expected_params), 1)
        for key, expected_value in expected_params.items():
            if key in params:
                if params[key] == expected_value:
                    param_matches += 1
        rparam = (param_matches / param_total) * 2 - 1  # Scale to [-1, 1]

        # Value match (same as param for now)
        rvalue = rparam

        return RewardBreakdown(
            rformat=rformat,
            rname=rname,
            rparam=rparam,
            rvalue=rvalue,
        )

    def _run_single_task(
        self,
        task_config: Any,  # TaskConfig
        env: TrainingEnvironment,
    ) -> ExperimentResult:
        """
        Run a single task via LLM query loop.

        Mirrors QueryEngine.submitMessage():
        1. Build prompt from task description
        2. Submit to QueryEngine (handles tool-use loop internally)
        3. Parse tool calls from result
        4. Compute reward based on tool usage vs expected
        """
        start_time = time.time()

        # Ensure query engine is built for this environment
        if self._query_engine is None:
            self._query_engine = self._build_query_engine(env)
        else:
            # Reset message history for each task (new conversation)
            self._query_engine.reset()

        # Build task prompt
        expected_tool = (
            task_config.tools_required[0]
            if task_config.tools_required else "none"
        )
        prompt = (
            f"Task: {task_config.description}\n"
            f"Target: {task_config.target}\n"
            f"Complete this task using the appropriate tool."
        )

        try:
            logger.info(f"Running task via LLM: {task_config.id}")

            # Submit to QueryEngine - this runs the full tool-use loop
            query_result = self._query_engine.submit(prompt)

            # Extract tools used from query result
            tools_used = [tc["name"] for tc in query_result.tool_calls]

            # Compute reward based on actual vs expected tool usage
            actual_tool = tools_used[0] if tools_used else "none"
            actual_params = (
                query_result.tool_calls[0]["input"]
                if query_result.tool_calls else {}
            )

            reward_breakdown = self.compute_reward(
                tool_name=actual_tool,
                expected_tool=expected_tool,
                params=actual_params,
                expected_params={},  # Ground truth params (extend later)
            )

            duration = time.time() - start_time

            logger.info(
                f"Task {task_config.id}: turns={query_result.turns} "
                f"tools={tools_used} reward={reward_breakdown.rfinal:.2f} "
                f"tokens={query_result.usage.total}"
            )

            return ExperimentResult(
                success=query_result.success,
                reward=reward_breakdown.rfinal,
                reward_breakdown=reward_breakdown,
                duration=duration,
                tools_used=tools_used,
                output=query_result.final_response,
                metadata={
                    "turns": query_result.turns,
                    "tool_calls": query_result.tool_calls,
                    "tokens": {
                        "input": query_result.usage.input_tokens,
                        "output": query_result.usage.output_tokens,
                    },
                    "model": self.config.llm_model,
                },
            )

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Task {task_config.id} failed: {e}")
            return ExperimentResult(
                success=False,
                reward=0.0,
                reward_breakdown=RewardBreakdown(),
                duration=duration,
                tools_used=[],
                output="",
                error=str(e),
            )

    def run_experiments(
        self,
        env: TrainingEnvironment,
        max_iterations: Optional[int] = None,
    ) -> List[ExperimentRecord]:
        """
        Run experiments within an environment.

        Args:
            env: Training environment
            max_iterations: Override max iterations

        Returns:
            List of experiment records
        """
        max_iter = max_iterations or self.config.max_iterations
        records = []

        # Build a fresh QueryEngine per environment (new tool set + system prompt)
        self._query_engine = self._build_query_engine(env)

        logger.info(f"Running experiments in {env.name} (max {max_iter} iterations)")

        for i in range(max_iter):
            for task in env.tasks:
                self._metrics.request_count += 1

                # Run task
                result = self._run_single_task(task, env)

                # Determine status
                if result.success and result.reward >= 0:
                    status = ExperimentStatus.KEEP
                else:
                    status = ExperimentStatus.DISCARD
                    self._metrics.error_count += 1

                # Create record
                record = ExperimentRecord(
                    commit=f"exp{self._experiment_count}",
                    timestamp=datetime.now(),
                    bpb_score=result.reward,
                    memory_mb=256,  # Placeholder
                    status=status,
                    description=f"Task {task.id}: {task.description}",
                    stage=env.stage,
                    reward=result.reward,
                    duration=result.duration,
                    tools_used=result.tools_used,
                )

                records.append(record)
                self._results.append(record)
                self._experiment_count += 1

                # Call handler if set
                if self._on_result:
                    self._on_result(record)

                logger.info(f"  Task {task.id}: reward={result.reward:.2f}, status={status.value}")

        return records

    def get_progress(self) -> ProgressMetrics:
        """Get current progress metrics"""
        return ProgressMetrics.from_records(self._results)

    def get_results(self) -> List[ExperimentRecord]:
        """Get all results"""
        return self._results.copy()

    def clear_results(self) -> None:
        """Clear all results"""
        self._results.clear()
        self._experiment_count = 0
