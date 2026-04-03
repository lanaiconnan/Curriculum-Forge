"""Token Counting & Estimation Utilities

Reference: Claude Code src/utils/tokens.ts

Implements:
- Token counting from API usage data
- Rough token estimation (when API data unavailable)
- Context window budget calculation
- Token budget tracking

For Curriculum-Forge:
- Accurate token counting from API responses
- Budget management for long conversations
- Cache token accounting (creation + read)

Usage:
    from utils.tokens import (
        token_count_from_usage,
        rough_token_count,
        estimate_tokens,
        TokenBudget,
    )
    
    # From API usage
    total = token_count_from_usage(api_response.usage)
    
    # From messages (estimation)
    total = rough_token_count(messages)
    
    # Budget tracking
    budget = TokenBudget(max_tokens=200_000, warning_threshold=0.8)
    budget.consume(input_tokens=5000, output_tokens=100)
    
    if budget.needs_compact():
        compact_messages(...)
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union


# ─── API Usage → Token Count ─────────────────────────────────────────────────

def token_count_from_usage(usage: Dict[str, Any]) -> int:
    """
    Calculate total context tokens from API usage data.
    
    From Claude Code tokens.ts:
        input_tokens
        + cache_creation_input_tokens  (new cached content)
        + cache_read_input_tokens       (read from cache)
        + output_tokens
    
    This represents the full context window size for that API call.
    
    Args:
        usage: API response usage dict, e.g.:
            {
                "input_tokens": 1000,
                "output_tokens": 200,
                "cache_creation_input_tokens": 5000,
                "cache_read_input_tokens": 8000,
            }
    
    Returns:
        Total tokens in context window
    """
    return (
        usage.get("input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
        + usage.get("output_tokens", 0)
    )


def input_token_count(usage: Dict[str, Any]) -> int:
    """Total input tokens (including cache)"""
    return (
        usage.get("input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
    )


def output_token_count(usage: Dict[str, Any]) -> int:
    """Output tokens only"""
    return usage.get("output_tokens", 0)


def cache_token_count(usage: Dict[str, Any]) -> int:
    """Cache tokens (creation + read)"""
    return (
        usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
    )


# ─── Rough Estimation ─────────────────────────────────────────────────────────

def rough_token_count(text: str) -> int:
    """
    Rough token count estimation for a string.
    
    From Claude Code roughTokenCountEstimate():
    - Simple heuristic: ~4 chars per token (English)
    - Languages with multi-byte chars: ~2 chars per token
    
    Args:
        text: Input string
    
    Returns:
        Estimated token count
    """
    if not text:
        return 0
    
    # Detect if text contains non-ASCII characters
    has_multibyte = any(ord(c) > 127 for c in text[:1000])
    
    if has_multibyte:
        # Asian languages: ~1-2 chars per token
        return len(text) // 2
    else:
        # English: ~4 chars per token
        return len(text) // 4


def estimate_tokens(text_or_messages: Union[str, List[Dict]]) -> int:
    """
    Estimate tokens for text or messages.
    
    Handles both plain text and Anthropic message format.
    
    Args:
        text_or_messages: Either:
            - A string (text content)
            - A list of message dicts with 'role' and 'content' keys
    
    Returns:
        Estimated token count
    """
    if isinstance(text_or_messages, str):
        return rough_token_count(text_or_messages)
    
    if isinstance(text_or_messages, list):
        total = 0
        for msg in text_or_messages:
            if isinstance(msg, dict):
                # Anthropic message format
                role = msg.get("role", "")
                total += 4  # Role token overhead
                
                content = msg.get("content", "")
                if isinstance(content, str):
                    total += rough_token_count(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            btype = block.get("type", "")
                            if btype == "text":
                                total += rough_token_count(block.get("text", ""))
                            elif btype in ("tool_use", "tool_result"):
                                # Tool blocks have overhead
                                inp = block.get("input", "")
                                if isinstance(inp, dict):
                                    inp = str(inp)
                                total += rough_token_count(inp)
                                
                                cnt = block.get("content", "")
                                if isinstance(cnt, dict):
                                    cnt = str(cnt)
                                total += rough_token_count(cnt)
                                total += 20  # Tool block overhead
                elif isinstance(content, dict):
                    # Single block
                    total += rough_token_count(content.get("text", ""))
            
            elif isinstance(msg, str):
                total += rough_token_count(msg)
        
        return total
    
    return 0


def estimate_messages_tokens(messages: List[Dict]) -> int:
    """
    Estimate tokens for a list of messages.
    
    Alias for estimate_tokens() with list type for clarity.
    """
    return estimate_tokens(messages)


def estimate_total_tokens(
    messages: List[Dict],
    system_prompt: Optional[str] = None,
) -> int:
    """
    Estimate total tokens including optional system prompt.
    
    Args:
        messages: List of message dicts
        system_prompt: Optional system prompt text
    
    Returns:
        Total estimated tokens
    """
    total = estimate_tokens(messages)
    if system_prompt:
        # System prompt token overhead
        total += rough_token_count(system_prompt) + 10
    return total


# ─── Token Budget ─────────────────────────────────────────────────────────────

@dataclass
class TokenBudgetStats:
    """Snapshot of budget state"""
    max_tokens: int
    current_tokens: int
    warning_threshold: float
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    
    @property
    def usage_ratio(self) -> float:
        return self.current_tokens / self.max_tokens if self.max_tokens > 0 else 0.0
    
    @property
    def remaining_tokens(self) -> int:
        return max(0, self.max_tokens - self.current_tokens)
    
    @property
    def is_warning(self) -> bool:
        return self.usage_ratio >= self.warning_threshold
    
    @property
    def is_over(self) -> bool:
        return self.current_tokens >= self.max_tokens


class TokenBudget:
    """
    Track and manage token budget for context windows.
    
    Mirrors Claude Code's budget calculation:
    - Context window = input + cache + output tokens
    - Warning threshold triggers compaction
    - Tracks cumulative usage across turns
    
    Usage:
        budget = TokenBudget(max_tokens=200_000, warning_threshold=0.8)
        
        # After each API call
        budget.consume(
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            cache_creation=resp.usage.cache_creation_input_tokens,
            cache_read=resp.usage.cache_read_input_tokens,
        )
        
        if budget.needs_compact():
            compact()
        
        # Check available for next request
        available = budget.available_for(max_output_tokens=4000)
    """
    
    def __init__(
        self,
        max_tokens: int = 200_000,
        warning_threshold: float = 0.8,
        reserve_tokens: int = 2000,
    ):
        """
        Args:
            max_tokens: Maximum context window size
            warning_threshold: Ratio at which to trigger warning (0.0-1.0)
            reserve_tokens: Reserve this many tokens for response output
        """
        self.max_tokens = max_tokens
        self.warning_threshold = warning_threshold
        self.reserve_tokens = reserve_tokens
    
    def consume(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
        usage: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Record token usage from an API response.
        
        This replaces the previous usage (not cumulative).
        Use multiple calls with incremental values if tracking cumulative.
        
        Args:
            input_tokens: Standard input tokens
            output_tokens: Output tokens
            cache_creation_tokens: New cache tokens created
            cache_read_tokens: Cache tokens read
            usage: Alternative - pass API usage dict directly
        """
        if usage:
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            cache_creation_tokens = usage.get("cache_creation_input_tokens", 0)
            cache_read_tokens = usage.get("cache_read_input_tokens", 0)
        
        self._input = input_tokens
        self._output = output_tokens
        self._cache_creation = cache_creation_tokens
        self._cache_read = cache_read_tokens
        self._total = token_count_from_usage({
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_creation_input_tokens": cache_creation_tokens,
            "cache_read_input_tokens": cache_read_tokens,
        })
    
    def snapshot(self) -> TokenBudgetStats:
        """Get current budget state snapshot"""
        return TokenBudgetStats(
            max_tokens=self.max_tokens,
            current_tokens=self._total,
            warning_threshold=self.warning_threshold,
            input_tokens=self._input,
            output_tokens=self._output,
            cache_creation_tokens=self._cache_creation,
            cache_read_tokens=self._cache_read,
        )
    
    def available_for(
        self,
        max_output_tokens: int = 4000,
        include_cache: bool = True,
    ) -> int:
        """
        Calculate available tokens for the next input.
        
        Args:
            max_output_tokens: Expected output token budget
            include_cache: If False, exclude cache tokens from current total
        
        Returns:
            Number of tokens available for next input
        """
        output_reserve = max_output_tokens
        effective_max = self.max_tokens - output_reserve
        
        if not include_cache:
            # Cache tokens don't count against budget
            # (they're preserved but don't consume context space)
            current = self._input + self._output
        else:
            current = self._total
        
        return max(0, effective_max - current)
    
    def needs_compact(self) -> bool:
        """Check if compaction is needed"""
        return self._total >= self.max_tokens * self.warning_threshold
    
    def remaining(self) -> int:
        """Tokens remaining in budget"""
        return max(0, self.max_tokens - self._total)
    
    def reset(self) -> None:
        """Reset budget counters (after compaction)"""
        self._input = 0
        self._output = 0
        self._cache_creation = 0
        self._cache_read = 0
        self._total = 0
    
    @property
    def total(self) -> int:
        return self._total
    
    # ─── Internal ─────────────────────────────────────────────────────────
    
    _input: int = 0
    _output: int = 0
    _cache_creation: int = 0
    _cache_read: int = 0
    _total: int = 0


# ─── Context Window Utilities ────────────────────────────────────────────────

def model_max_context(model: str) -> int:
    """
    Get maximum context window size for a model.
    
    Args:
        model: Model name (e.g., "claude-3-5-sonnet-20241022")
    
    Returns:
        Max context tokens, or 200_000 as default
    """
    # Claude 3.5 Sonnet / 3.7 Sonnet
    if "sonnet-4" in model or "claude-3-7" in model:
        return 200_000
    
    # Claude 3.5 Sonnet
    if "claude-3-5-sonnet" in model or "sonnet" in model:
        return 200_000
    
    # Claude 3 Opus / 3.5 Opus
    if "claude-3-opus" in model or "claude-3-5-opus" in model:
        return 200_000
    
    # Claude 3 Haiku / 3.5 Haiku
    if "claude-3-haiku" in model or "claude-3-5-haiku" in model:
        return 200_000
    
    # Default
    return 200_000


def output_token_budget(
    context_tokens: int,
    max_context: int = 200_000,
    reserve_tokens: int = 100,
) -> int:
    """
    Calculate safe output token budget given current context.
    
    Args:
        context_tokens: Current context size
        max_context: Model's max context window
        reserve_tokens: Safety buffer
    
    Returns:
        Maximum tokens for output response
    """
    return max(0, max_context - context_tokens - reserve_tokens)


# ─── Cost Estimation ──────────────────────────────────────────────────────────

@dataclass
class TokenCostConfig:
    """Cost per million tokens for different operations"""
    # Input (per 1M tokens)
    input_cost_per_m: float = 3.0
    # Cache creation (per 1M tokens)
    cache_creation_cost_per_m: float = 3.75
    # Cache read (per 1M tokens)
    cache_read_cost_per_m: float = 0.30
    # Output (per 1M tokens)
    output_cost_per_m: float = 15.0
    
    def estimate_cost(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
        usage: Optional[Dict[str, Any]] = None,
    ) -> float:
        """
        Estimate cost in USD.
        
        Args:
            input_tokens: Standard input tokens
            output_tokens: Output tokens
            cache_creation_tokens: Cache creation tokens
            cache_read_tokens: Cache read tokens
            usage: Alternative - pass API usage dict
        
        Returns:
            Estimated cost in USD
        """
        if usage:
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            cache_creation_tokens = usage.get("cache_creation_input_tokens", 0)
            cache_read_tokens = usage.get("cache_read_input_tokens", 0)
        
        cost = (
            input_tokens / 1_000_000 * self.input_cost_per_m
            + output_tokens / 1_000_000 * self.output_cost_per_m
            + cache_creation_tokens / 1_000_000 * self.cache_creation_cost_per_m
            + cache_read_tokens / 1_000_000 * self.cache_read_cost_per_m
        )
        return round(cost, 6)
