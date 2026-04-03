"""Context Compression — Long Conversation Support

Inspired by Claude Code's compact/ directory:
- autoCompact.ts: automatic compaction trigger
- compact.ts: message compression algorithm
- grouping.ts: message grouping strategy

Core idea (from QueryEngine.ts):
- Track token usage across turns
- When approaching limit, compress older messages
- Preserve: system prompt + recent N messages + critical results
- Summarize discarded messages

Design philosophy (from compact.ts):
- Never drop the system prompt
- Preserve the most recent conversation (last N messages)
- Summarize tool-heavy sections (each tool_result block)
- Mark the compact boundary so LLM knows context changed

Usage:
    compactor = ContextCompactor(
        max_tokens=150000,
        warning_threshold=0.8,
        keep_recent=10,
        summarize_fn=my_llm_summarizer,
    )

    if compactor.should_compact(messages, current_tokens):
        compressed = compactor.compact(messages, current_tokens)
        engine.replace_messages(compressed)
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, Tuple

from .query_engine import LLMMessage

logger = logging.getLogger(__name__)


# ─── Token Estimation ──────────────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """
    Rough token estimation.
    
    Rough rule: 1 token ≈ 4 chars for English.
    For mixed content, this is a safe overestimate.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_message_tokens(msg: LLMMessage) -> int:
    """Estimate tokens for a single message"""
    base = estimate_tokens(msg.content if isinstance(msg.content, str) else str(msg.content))
    # Role prefix adds some tokens
    return base + estimate_tokens(msg.role) + 5


def estimate_total_tokens(messages: List[LLMMessage]) -> int:
    """Estimate total tokens for a message list"""
    return sum(estimate_message_tokens(m) for m in messages)


# ─── Compact Strategy ─────────────────────────────────────────────────────────

@dataclass
class CompactConfig:
    """Configuration for context compaction"""
    max_tokens: int = 150000          # Hard limit (e.g., Claude 200k context)
    warning_threshold: float = 0.80  # Trigger compact at 80% of max
    keep_recent: int = 10             # Always keep last N messages
    summarize_tool_results: bool = True  # Summarize tool_result blocks
    max_tool_result_length: int = 200   # Truncate individual tool results


@dataclass
class CompactBoundary:
    """
    Marks where compaction occurred.
    
    Inserted as a system message so LLM understands context shift.
    """
    summary: str
    preserved_count: int       # How many recent messages kept
    removed_count: int         # How many older messages removed
    original_tokens: int
    compressed_tokens: int
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M"))
    
    def to_message(self) -> LLMMessage:
        content = (
            f"[Context compressed: removed {self.removed_count} messages, "
            f"preserved {self.preserved_count} recent ones. "
            f"Summary of removed content: {self.summary}]"
        )
        return LLMMessage(role="system", content=content)


# ─── Message Grouping ─────────────────────────────────────────────────────────

@dataclass  
class MessageGroup:
    """A group of related messages (e.g., one turn = user + assistant + tool_results)"""
    messages: List[LLMMessage]
    turn_index: int            # Which conversation turn this represents
    is_tool_heavy: bool       # Contains many tool_result blocks
    has_error: bool           # Contains error results
    
    @property
    def token_count(self) -> int:
        return sum(estimate_message_tokens(m) for m in self.messages)


def group_messages(messages: List[LLMMessage]) -> List[MessageGroup]:
    """
    Group messages into turns.
    
    A "turn" is one user message + the resulting assistant response(s).
    Tool results are attached to the assistant message that triggered them.
    
    Special case: if a user message contains tool_result blocks (as in
    Claude's API format), it's attached to the current turn rather than
    starting a new one.
    """
    groups: List[MessageGroup] = []
    current_turn: List[LLMMessage] = []
    turn_index = 0
    
    def _is_tool_result_message(msg: LLMMessage) -> bool:
        """Check if a message contains tool_result blocks"""
        if not isinstance(msg.content, list):
            return False
        return any(b.get("type") == "tool_result" for b in msg.content)
    
    def _has_error_in_message(msg: LLMMessage) -> bool:
        if not isinstance(msg.content, list):
            return False
        return any(b.get("is_error") is True for b in msg.content)
    
    for msg in messages:
        if msg.role == "user" and not _is_tool_result_message(msg):
            # Real user message (not tool_result) — new turn
            if current_turn:
                groups.append(_make_group(current_turn, turn_index))
                turn_index += 1
            current_turn = [msg]
        elif msg.role == "assistant":
            current_turn.append(msg)
        elif msg.role == "system":
            # System messages are their own groups (usually system prompt)
            groups.append(_make_group([msg], turn_index))
            turn_index += 1
        else:
            # tool_result, etc — attach to current turn
            current_turn.append(msg)
    
    # Don't forget the last turn
    if current_turn:
        groups.append(_make_group(current_turn, turn_index))
    
    return groups


def _make_group(messages: List[LLMMessage], turn_index: int) -> MessageGroup:
    """Create a MessageGroup from a list of messages"""
    
    def _is_tool_result_message(msg: LLMMessage) -> bool:
        if not isinstance(msg.content, list):
            return False
        return any(b.get("type") == "tool_result" for b in msg.content)
    
    def _has_error_in_message(msg: LLMMessage) -> bool:
        if not isinstance(msg.content, list):
            return False
        return any(b.get("is_error") is True for b in msg.content)
    
    # Count tool_result blocks across all messages in the group
    tool_result_blocks = 0
    error_blocks = 0
    for msg in messages:
        if isinstance(msg.content, list):
            tool_result_blocks += sum(
                1 for b in msg.content if b.get("type") == "tool_result"
            )
            error_blocks += sum(
                1 for b in msg.content if b.get("is_error") is True
            )
    
    return MessageGroup(
        messages=messages,
        turn_index=turn_index,
        is_tool_heavy=tool_result_blocks >= 3,
        has_error=error_blocks > 0,
    )


# ─── Default Summarizer ───────────────────────────────────────────────────────

def default_summarize_fn(removed_groups: List[MessageGroup]) -> str:
    """
    Simple rule-based summarizer for removed messages.
    
    In production, replace with an LLM call:
        summary = llm.call("Summarize: ...")
    
    This default version creates a brief rule-based summary.
    """
    total_msgs = sum(len(g.messages) for g in removed_groups)
    tool_calls = 0
    errors = sum(1 for g in removed_groups if g.has_error)
    
    # Count tool_result blocks across all groups
    for g in removed_groups:
        for m in g.messages:
            if isinstance(m.content, list):
                tool_calls += sum(
                    1 for b in m.content
                    if b.get("type") in ("tool_use", "tool_result")
                )
    
    parts = []
    if tool_calls > 0:
        parts.append(f"{tool_calls} tool call{'s' if tool_calls != 1 else ''}")
    if errors > 0:
        parts.append(f"{errors} error{'s' if errors != 1 else ''}")
    if total_msgs > 0:
        parts.append(f"{total_msgs} message{'s' if total_msgs != 1 else ''}")
    
    if not parts:
        return "Previous conversation with no significant events."
    
    return "Previous conversation: " + ", ".join(parts) + "."


# ─── ContextCompactor ────────────────────────────────────────────────────────

class ContextCompactor:
    """
    Compresses long conversations to fit within token budget.

    Inspired by Claude Code's autoCompact.ts + compact.ts:

    autoCompact.ts role:
        - Tracks current token usage
        - Determines when to trigger compaction
        - Tracks autoCompact state (tracking_token_count, etc.)

    compact.ts role:
        - Groups messages into turns
        - Decides which turns to keep/summarize
        - Inserts compact boundary marker

    Flow:
        should_compact() → compact() → get_compressed_messages()

    Usage:
        compactor = ContextCompactor(config)
        if compactor.should_compact(messages, token_count):
            result = compactor.compact(messages, token_count)
            # Replace engine's messages with result.messages
            # Log result.boundary for debugging
    """

    def __init__(
        self,
        config: Optional[CompactConfig] = None,
        summarize_fn: Optional[Callable[[List[MessageGroup]], str]] = None,
    ):
        self.config = config or CompactConfig()
        self.summarize_fn = summarize_fn or default_summarize_fn

        # State (persists across calls)
        self._compact_count = 0
        self._last_compact_tokens = 0
        self._last_compact_time: Optional[float] = None

    @property
    def compact_count(self) -> int:
        """Number of times compaction has been performed"""
        return self._compact_count

    @property
    def last_compact_tokens(self) -> int:
        return self._last_compact_tokens

    def should_compact(
        self,
        messages: List[LLMMessage],
        current_tokens: int,
    ) -> Tuple[bool, str]:
        """
        Check if compaction is needed.

        Returns (should_compact, reason)

        Conditions:
        1. Token count exceeds warning threshold
        2. Not compacted too recently (debounce)
        3. Enough messages to warrant compaction
        """
        max_tokens = self.config.max_tokens
        threshold = self.config.warning_threshold

        # Condition 1: Token threshold
        if current_tokens >= max_tokens * threshold:
            return True, (
                f"Token count ({current_tokens}) exceeds "
                f"{threshold:.0%} of max ({int(max_tokens * threshold)})"
            )

        # Condition 2: Debounce — don't compact twice in 5 minutes
        if self._last_compact_time is not None:
            elapsed = time.time() - self._last_compact_time
            if elapsed < 300:  # 5 minutes
                return False, f"Debounce: compacted {elapsed:.0f}s ago"

        # Condition 3: Enough messages
        if len(messages) < self.config.keep_recent * 2:
            return False, f"Only {len(messages)} messages, not enough to compact"

        return False, "No compaction needed"

    def compact(
        self,
        messages: List[LLMMessage],
        current_tokens: Optional[int] = None,
    ) -> Tuple[List[LLMMessage], CompactBoundary]:
        """
        Compress messages to fit within token budget.

        Algorithm (from compact.ts):
        1. Keep: system prompt (first message if role=system)
        2. Keep: last N messages (keep_recent)
        3. Keep: compact boundary marker
        4. Summarize: everything in between

        Args:
            messages: Full message history
            current_tokens: Pre-computed token count (computed if None)

        Returns:
            (compressed_messages, compact_boundary)
        """
        if current_tokens is None:
            current_tokens = estimate_total_tokens(messages)

        original_count = len(messages)
        original_tokens = current_tokens

        # Step 1: Find system message (always keep first if system)
        system_messages = [m for m in messages if m.role == "system"]
        non_system = [m for m in messages if m.role != "system"]

        # Step 2: Keep last N messages
        keep = non_system[-self.config.keep_recent:] if non_system else []
        discard = non_system[:-self.config.keep_recent] if non_system else []

        # Step 3: Group discarded messages
        discarded_groups = group_messages(discard)

        # Step 4: Generate summary
        summary = self.summarize_fn(discarded_groups)

        # Step 5: Build boundary
        boundary = CompactBoundary(
            summary=summary,
            preserved_count=len(keep),
            removed_count=len(discard),
            original_tokens=original_tokens,
            compressed_tokens=0,  # Will update below
        )

        # Step 6: Build compressed message list
        compressed = cast(List[LLMMessage], list(system_messages))
        compressed.append(boundary.to_message())
        compressed.extend(keep)

        # Update boundary with actual compressed token count
        boundary.compressed_tokens = estimate_total_tokens(compressed)

        # Update state
        self._compact_count += 1
        self._last_compact_tokens = boundary.compressed_tokens
        self._last_compact_time = time.time()

        logger.info(
            f"Compacted {original_count} msgs → {len(compressed)} msgs "
            f"({original_tokens} → {boundary.compressed_tokens} tokens, "
            f"removed {boundary.removed_count}, kept {boundary.preserved_count})"
        )

        return compressed, boundary

    def get_state(self) -> Dict[str, Any]:
        """Get current compaction state for debugging/logging"""
        return {
            "compact_count": self._compact_count,
            "last_compact_tokens": self._last_compact_tokens,
            "last_compact_time": (
                time.strftime("%H:%M:%S", time.localtime(self._last_compact_time))
                if self._last_compact_time else None
            ),
            "config": {
                "max_tokens": self.config.max_tokens,
                "warning_threshold": self.config.warning_threshold,
                "keep_recent": self.config.keep_recent,
            },
        }


# ─── CompactResult ───────────────────────────────────────────────────────────

@dataclass
class CompactResult:
    """Result of a compaction operation"""
    original_messages: int
    compressed_messages: int
    original_tokens: int
    compressed_tokens: int
    removed_count: int
    preserved_count: int
    boundary: CompactBoundary

    @property
    def compression_ratio(self) -> float:
        if self.original_tokens == 0:
            return 1.0
        return self.compressed_tokens / self.original_tokens

    @property
    def saved_tokens(self) -> int:
        return self.original_tokens - self.compressed_tokens


# Helper for type hints
cast = lambda _t, x: x


# ─── Integration with QueryEngine ────────────────────────────────────────────

class CompactableQueryEngine:
    """
    A QueryEngine wrapper that automatically handles context compaction.

    Wraps an existing QueryEngine and:
    - Tracks token usage after each submit()
    - Triggers compaction when threshold exceeded
    - Replaces engine's message history with compressed version

    Usage:
        base_engine = QueryEngine(backend=..., tools=...)
        engine = CompactableQueryEngine(base_engine, config=CompactConfig())

        # Works like normal QueryEngine, but auto-compacts
        result = engine.submit("Hello")
        # Internally may compact if tokens exceed threshold
    """

    def __init__(
        self,
        engine: 'QueryEngine',          # noqa: F821
        config: Optional[CompactConfig] = None,
        summarize_fn: Optional[Callable[[List[MessageGroup]], str]] = None,
    ):
        from .query_engine import QueryEngine
        self._engine = engine
        self._compactor = ContextCompactor(config, summarize_fn)
        self._compact_history: List[CompactResult] = []

    @property
    def compactor(self) -> ContextCompactor:
        return self._compactor

    @property
    def compact_history(self) -> List[CompactResult]:
        return self._compact_history.copy()

    def submit(
        self,
        prompt: str,
        extra_system: Optional[str] = None,
    ) -> 'QueryResult':               # noqa: F821
        """Submit a message, auto-compacting if needed"""
        from .query_engine import QueryResult

        # Check if compaction needed BEFORE submitting
        current_tokens = self._engine._usage.total
        should, reason = self._compactor.should_compact(
            self._engine._messages, current_tokens
        )

        if should:
            logger.info(f"Pre-submit compaction triggered: {reason}")
            messages, boundary = self._compactor.compact(
                self._engine._messages, current_tokens
            )

            # Replace engine's message history
            self._engine._messages = messages

            # Record history
            self._compact_history.append(CompactResult(
                original_messages=len(messages) + boundary.removed_count,
                compressed_messages=len(messages),
                original_tokens=boundary.original_tokens,
                compressed_tokens=boundary.compressed_tokens,
                removed_count=boundary.removed_count,
                preserved_count=boundary.preserved_count,
                boundary=boundary,
            ))

        # Forward to base engine
        return self._engine.submit(prompt, extra_system)

    def reset(self) -> None:
        """Reset both engine and compactor state"""
        self._engine.reset()
        self._compact_count = 0
        self._last_compact_tokens = 0
        self._compact_history.clear()

    def __getattr__(self, name: str) -> Any:
        """Delegate unknown attributes to underlying engine"""
        return getattr(self._engine, name)
