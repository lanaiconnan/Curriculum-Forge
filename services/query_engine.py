"""LLM Query Engine for Curriculum-Forge

Inspired by Claude Code's QueryEngine.ts:
- submitMessage() → query loop
- Tool use handling (tool_use → tool_result → continue)
- Message history management across turns
- Token budget tracking
- Retry with backoff

Supports multiple backends:
- Anthropic Claude (via anthropic SDK)
- OpenAI-compatible (via openai SDK)
- Mock (for testing without API keys)
"""

import os
import time
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, Generator

logger = logging.getLogger(__name__)


# ─── Message Types ────────────────────────────────────────────────────────────

@dataclass
class ToolUseBlock:
    """A tool call requested by the LLM"""
    id: str
    name: str
    input: Dict[str, Any]


@dataclass
class ToolResultBlock:
    """Result of executing a tool"""
    tool_use_id: str
    content: str
    is_error: bool = False


@dataclass
class LLMMessage:
    """A message in the conversation"""
    role: str  # "user" | "assistant"
    content: Any  # str | list of content blocks


@dataclass
class LLMResponse:
    """Response from the LLM"""
    content: str
    tool_uses: List[ToolUseBlock]
    stop_reason: str  # "end_turn" | "tool_use" | "max_tokens"
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


@dataclass
class TokenUsage:
    """Accumulated token usage"""
    input_tokens: int = 0
    output_tokens: int = 0
    
    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens
    
    def add(self, response: LLMResponse) -> None:
        self.input_tokens += response.input_tokens
        self.output_tokens += response.output_tokens


# ─── Tool Registry ────────────────────────────────────────────────────────────

ToolHandler = Callable[[Dict[str, Any]], str]


@dataclass
class ToolDefinition:
    """A tool that the LLM can call"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: ToolHandler


class ToolRegistry:
    """Registry of available tools"""
    
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
    
    def register(self, tool: ToolDefinition) -> 'ToolRegistry':
        self._tools[tool.name] = tool
        return self
    
    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)
    
    def to_api_format(self) -> List[Dict[str, Any]]:
        """Convert to Anthropic/OpenAI tool format"""
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in self._tools.values()
        ]
    
    def execute(self, tool_use: ToolUseBlock) -> ToolResultBlock:
        """Execute a tool call"""
        tool = self._tools.get(tool_use.name)
        if not tool:
            return ToolResultBlock(
                tool_use_id=tool_use.id,
                content=f"Unknown tool: {tool_use.name}",
                is_error=True,
            )
        
        try:
            result = tool.handler(tool_use.input)
            return ToolResultBlock(
                tool_use_id=tool_use.id,
                content=str(result),
            )
        except Exception as e:
            logger.error(f"Tool '{tool_use.name}' error: {e}")
            return ToolResultBlock(
                tool_use_id=tool_use.id,
                content=f"Tool error: {e}",
                is_error=True,
            )


# ─── LLM Backend ─────────────────────────────────────────────────────────────

class LLMBackend(ABC):
    """Abstract LLM backend"""
    
    @abstractmethod
    def call(
        self,
        messages: List[LLMMessage],
        system: str,
        tools: List[Dict[str, Any]],
        max_tokens: int,
    ) -> LLMResponse:
        pass
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        pass


class MockBackend(LLMBackend):
    """
    Mock backend for testing without API keys.
    
    Simulates realistic LLM behavior:
    - Calls tools when task requires them
    - Returns structured responses
    - Tracks call count
    """
    
    def __init__(self, tool_call_probability: float = 0.7, model: str = "mock-llm", **kwargs):
        self.tool_call_probability = tool_call_probability
        self._model = model
        self._call_count = 0
        self._tool_call_count = 0
    
    @property
    def model_name(self) -> str:
        return self._model
    
    def call(
        self,
        messages: List[LLMMessage],
        system: str,
        tools: List[Dict[str, Any]],
        max_tokens: int,
    ) -> LLMResponse:
        import random
        self._call_count += 1
        
        # Decide whether to call a tool
        should_use_tool = (
            tools
            and random.random() < self.tool_call_probability
            and self._tool_call_count < 3  # Limit tool calls per episode
        )
        
        if should_use_tool:
            tool = random.choice(tools)
            tool_name = tool["name"]
            
            # Generate plausible input based on schema
            tool_input = self._generate_tool_input(tool)
            
            self._tool_call_count += 1
            
            return LLMResponse(
                content=f"I'll use the {tool_name} tool to complete this task.",
                tool_uses=[
                    ToolUseBlock(
                        id=f"tool_{self._call_count}_{int(time.time()*1000) % 10000}",
                        name=tool_name,
                        input=tool_input,
                    )
                ],
                stop_reason="tool_use",
                input_tokens=len(str(messages)) // 4,
                output_tokens=50,
                model=self.model_name,
            )
        else:
            # Final answer
            self._tool_call_count = 0  # Reset for next episode
            return LLMResponse(
                content="Task completed. I've analyzed the environment and executed the required operations.",
                tool_uses=[],
                stop_reason="end_turn",
                input_tokens=len(str(messages)) // 4,
                output_tokens=80,
                model=self.model_name,
            )
    
    def _generate_tool_input(self, tool_def: Dict[str, Any]) -> Dict[str, Any]:
        """Generate plausible input for a tool"""
        schema = tool_def.get("input_schema", {})
        props = schema.get("properties", {})
        required = schema.get("required", [])
        
        result = {}
        for key in required:
            prop = props.get(key, {})
            prop_type = prop.get("type", "string")
            if prop_type == "string":
                result[key] = f"test_{key}_value"
            elif prop_type == "integer":
                result[key] = 1
            elif prop_type == "number":
                result[key] = 1.0
            elif prop_type == "boolean":
                result[key] = True
            elif prop_type == "array":
                result[key] = []
        
        return result


class AnthropicBackend(LLMBackend):
    """
    Anthropic Claude backend.
    
    Requires: pip install anthropic
    Env: ANTHROPIC_API_KEY
    """
    
    def __init__(self, model: str = "claude-3-5-haiku-20241022"):
        self._model = model
        self._client = None
    
    @property
    def model_name(self) -> str:
        return self._model
    
    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
                api_key = os.environ.get("ANTHROPIC_API_KEY")
                if not api_key:
                    raise ValueError("ANTHROPIC_API_KEY not set")
                self._client = anthropic.Anthropic(api_key=api_key)
            except ImportError:
                raise ImportError("pip install anthropic")
        return self._client
    
    def call(
        self,
        messages: List[LLMMessage],
        system: str,
        tools: List[Dict[str, Any]],
        max_tokens: int,
    ) -> LLMResponse:
        client = self._get_client()
        
        # Convert messages to Anthropic format
        api_messages = []
        for msg in messages:
            if isinstance(msg.content, str):
                api_messages.append({"role": msg.role, "content": msg.content})
            else:
                api_messages.append({"role": msg.role, "content": msg.content})
        
        kwargs = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": api_messages,
        }
        if tools:
            kwargs["tools"] = tools
        
        response = client.messages.create(**kwargs)
        
        # Parse response
        content_text = ""
        tool_uses = []
        
        for block in response.content:
            if block.type == "text":
                content_text = block.text
            elif block.type == "tool_use":
                tool_uses.append(ToolUseBlock(
                    id=block.id,
                    name=block.name,
                    input=block.input,
                ))
        
        return LLMResponse(
            content=content_text,
            tool_uses=tool_uses,
            stop_reason=response.stop_reason,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
        )


# ─── Query Engine ─────────────────────────────────────────────────────────────

@dataclass
class QueryConfig:
    """Configuration for QueryEngine"""
    system_prompt: str = "You are a helpful AI assistant."
    max_tokens: int = 1024
    max_turns: int = 10          # Max tool-use turns per query
    max_total_tokens: int = 50000  # Budget limit
    retry_attempts: int = 3
    retry_delay: float = 1.0


@dataclass
class QueryResult:
    """Result of a complete query (may span multiple turns)"""
    final_response: str
    turns: int
    tool_calls: List[Dict[str, Any]]
    usage: TokenUsage
    success: bool
    error: Optional[str] = None


class QueryEngine:
    """
    LLM query engine with tool-use loop.
    
    Mirrors Claude Code's QueryEngine.ts:
    
        submitMessage(prompt)
            → query(messages, tools)
                → LLM call
                → if tool_use: execute tools, append results, loop
                → if end_turn: return final response
    
    Usage:
        engine = QueryEngine(
            backend=AnthropicBackend(),
            tools=registry,
            config=QueryConfig(system_prompt="You are..."),
        )
        
        result = engine.submit("Solve this task: ...")
        print(result.final_response)
    """
    
    def __init__(
        self,
        backend: LLMBackend,
        tools: Optional[ToolRegistry] = None,
        config: Optional[QueryConfig] = None,
    ):
        self.backend = backend
        self.tools = tools or ToolRegistry()
        self.config = config or QueryConfig()
        
        # Session state (persists across turns, like QueryEngine.mutableMessages)
        self._messages: List[LLMMessage] = []
        self._usage = TokenUsage()
        self._turn_count = 0
    
    def reset(self) -> None:
        """Reset session state (start new conversation)"""
        self._messages = []
        self._usage = TokenUsage()
        self._turn_count = 0
    
    @property
    def usage(self) -> TokenUsage:
        return self._usage
    
    @property
    def messages(self) -> List[LLMMessage]:
        return self._messages.copy()
    
    def submit(
        self,
        prompt: str,
        extra_system: Optional[str] = None,
    ) -> QueryResult:
        """
        Submit a message and run the query loop until completion.
        
        Mirrors QueryEngine.submitMessage():
        1. Append user message
        2. Call LLM
        3. If tool_use: execute tools, append results, loop
        4. If end_turn: return final response
        
        Args:
            prompt: User message
            extra_system: Additional system context for this turn
        
        Returns:
            QueryResult with final response and metadata
        """
        # Check token budget
        if self._usage.total >= self.config.max_total_tokens:
            return QueryResult(
                final_response="",
                turns=0,
                tool_calls=[],
                usage=self._usage,
                success=False,
                error=f"Token budget exceeded ({self._usage.total} >= {self.config.max_total_tokens})",
            )
        
        # Append user message
        self._messages.append(LLMMessage(role="user", content=prompt))
        
        # Build system prompt
        system = self.config.system_prompt
        if extra_system:
            system = f"{system}\n\n{extra_system}"
        
        # Tool definitions for API
        tool_defs = self.tools.to_api_format()
        
        # Query loop (mirrors the while loop in query.ts)
        turns = 0
        all_tool_calls: List[Dict[str, Any]] = []
        final_response = ""
        
        while turns < self.config.max_turns:
            turns += 1
            self._turn_count += 1
            
            # Call LLM with retry
            response = self._call_with_retry(system, tool_defs)
            if response is None:
                return QueryResult(
                    final_response=final_response,
                    turns=turns,
                    tool_calls=all_tool_calls,
                    usage=self._usage,
                    success=False,
                    error="LLM call failed after retries",
                )
            
            # Track usage
            self._usage.add(response)
            
            # Append assistant message
            if response.tool_uses:
                # Build content blocks (text + tool_use)
                content_blocks = []
                if response.content:
                    content_blocks.append({"type": "text", "text": response.content})
                for tu in response.tool_uses:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tu.id,
                        "name": tu.name,
                        "input": tu.input,
                    })
                self._messages.append(LLMMessage(role="assistant", content=content_blocks))
            else:
                self._messages.append(LLMMessage(role="assistant", content=response.content))
                final_response = response.content
            
            logger.debug(
                f"Turn {turns}: stop_reason={response.stop_reason} "
                f"tool_uses={len(response.tool_uses)} "
                f"tokens={response.input_tokens}+{response.output_tokens}"
            )
            
            # Check stop condition
            if response.stop_reason == "end_turn" or not response.tool_uses:
                final_response = response.content
                break
            
            # Execute tools (mirrors runTools() in toolOrchestration.ts)
            tool_results = []
            for tool_use in response.tool_uses:
                logger.info(f"Executing tool: {tool_use.name}({json.dumps(tool_use.input)[:80]})")
                result = self.tools.execute(tool_use)
                tool_results.append(result)
                all_tool_calls.append({
                    "name": tool_use.name,
                    "input": tool_use.input,
                    "result": result.content[:200],
                    "is_error": result.is_error,
                })
                logger.info(
                    f"Tool result: {result.content[:100]}"
                    f"{'[ERROR]' if result.is_error else ''}"
                )
            
            # Append tool results as user message
            tool_result_blocks = [
                {
                    "type": "tool_result",
                    "tool_use_id": r.tool_use_id,
                    "content": r.content,
                    "is_error": r.is_error,
                }
                for r in tool_results
            ]
            self._messages.append(LLMMessage(role="user", content=tool_result_blocks))
            
            # Check token budget after each turn
            if self._usage.total >= self.config.max_total_tokens:
                logger.warning(f"Token budget exceeded mid-loop: {self._usage.total}")
                break
        
        return QueryResult(
            final_response=final_response,
            turns=turns,
            tool_calls=all_tool_calls,
            usage=self._usage,
            success=True,
        )
    
    def _call_with_retry(
        self,
        system: str,
        tool_defs: List[Dict[str, Any]],
    ) -> Optional[LLMResponse]:
        """Call LLM with exponential backoff retry"""
        last_error = None
        
        for attempt in range(self.config.retry_attempts):
            try:
                return self.backend.call(
                    messages=self._messages,
                    system=system,
                    tools=tool_defs,
                    max_tokens=self.config.max_tokens,
                )
            except Exception as e:
                last_error = e
                wait = self.config.retry_delay * (2 ** attempt)
                logger.warning(
                    f"LLM call failed (attempt {attempt+1}/{self.config.retry_attempts}): {e}. "
                    f"Retrying in {wait:.1f}s..."
                )
                time.sleep(wait)
        
        logger.error(f"LLM call failed after {self.config.retry_attempts} attempts: {last_error}")
        return None


# ─── Factory ──────────────────────────────────────────────────────────────────

def create_backend(backend_type: str = "auto", **kwargs) -> LLMBackend:
    """
    Create an LLM backend.
    
    Args:
        backend_type: "auto" | "anthropic" | "mock"
        **kwargs: Backend-specific options (model, etc.)
    
    Returns:
        LLMBackend instance
    
    "auto" tries Anthropic first, falls back to Mock.
    """
    if backend_type == "mock":
        return MockBackend(**kwargs)
    
    if backend_type == "anthropic":
        return AnthropicBackend(**kwargs)
    
    # auto: try Anthropic, fall back to Mock
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic  # noqa: F401
            logger.info("Using Anthropic backend")
            return AnthropicBackend(**kwargs)
        except ImportError:
            logger.warning("anthropic not installed, falling back to Mock")
    
    logger.info("Using Mock backend (no API key)")
    return MockBackend(**kwargs)
