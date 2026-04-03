"""Tool Permission & Management Layer

Inspired by Claude Code's Tool.ts / useCanUseTool.ts:
- ToolPermission: allow/deny lists + rate limiting
- ToolResultFormatter: truncate, structure, normalize errors
- ToolStats: per-tool call statistics (feeds reward calculation)
- ManagedToolRegistry: ToolRegistry + permission + formatting + stats

Design mirrors Claude Code's canUseTool pattern:
  canUseTool(tool, input, context) → {behavior: "allow"|"deny", reason?}

Usage:
    registry = ManagedToolRegistry(
        permission=ToolPermission(
            allow_list=["read_file", "search"],
            rate_limits={"read_file": RateLimit(max_calls=10, window_seconds=60)},
        ),
        formatter=ToolResultFormatter(max_length=2000),
    )

    registry.register(ToolDefinition(...))

    # Execute with permission check + formatting + stats
    result = registry.execute(ToolUseBlock(...))

    # Stats for reward calculation
    stats = registry.stats.get("read_file")
    print(stats.success_rate)
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from enum import Enum
from collections import deque

from .query_engine import (
    ToolRegistry,
    ToolDefinition,
    ToolUseBlock,
    ToolResultBlock,
)

logger = logging.getLogger(__name__)


# ─── Permission ───────────────────────────────────────────────────────────────

class PermissionBehavior(Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass
class PermissionResult:
    behavior: PermissionBehavior
    reason: Optional[str] = None

    @property
    def allowed(self) -> bool:
        return self.behavior == PermissionBehavior.ALLOW


@dataclass
class RateLimit:
    """Sliding-window rate limit for a tool"""
    max_calls: int          # Max calls allowed in window
    window_seconds: float   # Window size in seconds

    def __post_init__(self):
        self._timestamps: deque = deque()

    def check(self) -> bool:
        """Returns True if call is allowed, False if rate-limited"""
        now = time.time()
        # Evict old timestamps outside the window
        while self._timestamps and now - self._timestamps[0] > self.window_seconds:
            self._timestamps.popleft()
        return len(self._timestamps) < self.max_calls

    def record(self) -> None:
        """Record a call timestamp"""
        self._timestamps.append(time.time())

    @property
    def current_count(self) -> int:
        now = time.time()
        return sum(1 for t in self._timestamps if now - t <= self.window_seconds)

    @property
    def remaining(self) -> int:
        return max(0, self.max_calls - self.current_count)


@dataclass
class ToolPermission:
    """
    Permission policy for tool execution.

    Mirrors Claude Code's ToolPermissionContext:
    - allow_list: only these tools may be called (empty = all allowed)
    - deny_list: these tools are always blocked
    - rate_limits: per-tool rate limiting
    - require_confirmation: tools that need explicit approval (future)

    Priority: deny_list > allow_list > rate_limits
    """
    allow_list: Optional[List[str]] = None   # None = allow all
    deny_list: List[str] = field(default_factory=list)
    rate_limits: Dict[str, RateLimit] = field(default_factory=dict)

    def check(self, tool_name: str) -> PermissionResult:
        """
        Check if a tool call is permitted.

        Returns PermissionResult with behavior and optional reason.
        """
        # 1. Deny list takes priority
        if tool_name in self.deny_list:
            return PermissionResult(
                behavior=PermissionBehavior.DENY,
                reason=f"Tool '{tool_name}' is in deny list",
            )

        # 2. Allow list (if set, only listed tools are permitted)
        if self.allow_list is not None and tool_name not in self.allow_list:
            return PermissionResult(
                behavior=PermissionBehavior.DENY,
                reason=f"Tool '{tool_name}' not in allow list",
            )

        # 3. Rate limit
        if tool_name in self.rate_limits:
            rl = self.rate_limits[tool_name]
            if not rl.check():
                return PermissionResult(
                    behavior=PermissionBehavior.DENY,
                    reason=(
                        f"Tool '{tool_name}' rate limited: "
                        f"{rl.current_count}/{rl.max_calls} calls "
                        f"in {rl.window_seconds}s window"
                    ),
                )

        return PermissionResult(behavior=PermissionBehavior.ALLOW)

    def record_call(self, tool_name: str) -> None:
        """Record a successful call for rate limiting"""
        if tool_name in self.rate_limits:
            self.rate_limits[tool_name].record()

    @classmethod
    def allow_all(cls) -> 'ToolPermission':
        """Permissive policy: allow everything"""
        return cls()

    @classmethod
    def allow_only(cls, tools: List[str]) -> 'ToolPermission':
        """Restrictive policy: only listed tools"""
        return cls(allow_list=tools)

    @classmethod
    def deny_only(cls, tools: List[str]) -> 'ToolPermission':
        """Deny specific tools, allow rest"""
        return cls(deny_list=tools)


# ─── Result Formatter ─────────────────────────────────────────────────────────

@dataclass
class ToolResultFormatter:
    """
    Normalizes and formats tool results before returning to LLM.

    Mirrors Claude Code's applyToolResultBudget / result formatting:
    - Truncate overly long outputs
    - Wrap errors in consistent format
    - Add metadata (tool name, duration)
    - Structured output option
    """
    max_length: int = 4000          # Max chars in result
    truncation_marker: str = "\n... [truncated]"
    include_metadata: bool = False  # Add tool name + duration to result
    error_prefix: str = "ERROR: "

    def format_success(
        self,
        tool_name: str,
        content: str,
        duration: float = 0.0,
    ) -> str:
        """Format a successful tool result"""
        result = content

        # Truncate if needed
        if len(result) > self.max_length:
            cutoff = self.max_length - len(self.truncation_marker)
            result = result[:cutoff] + self.truncation_marker
            logger.debug(
                f"Tool '{tool_name}' result truncated: "
                f"{len(content)} → {len(result)} chars"
            )

        # Optional metadata header
        if self.include_metadata:
            result = f"[{tool_name} | {duration:.3f}s]\n{result}"

        return result

    def format_error(
        self,
        tool_name: str,
        error: str,
        duration: float = 0.0,
    ) -> str:
        """Format an error result"""
        msg = f"{self.error_prefix}{error}"
        if self.include_metadata:
            msg = f"[{tool_name} | {duration:.3f}s | ERROR]\n{msg}"
        return msg

    def format_denied(self, tool_name: str, reason: str) -> str:
        """Format a permission-denied result"""
        return f"{self.error_prefix}Permission denied for '{tool_name}': {reason}"


# ─── Tool Stats ───────────────────────────────────────────────────────────────

@dataclass
class ToolCallRecord:
    """Record of a single tool call"""
    tool_name: str
    success: bool
    duration: float
    denied: bool = False
    timestamp: float = field(default_factory=time.time)


@dataclass
class ToolStats:
    """
    Per-tool call statistics.

    Used by reward calculation to assess tool usage quality.
    Mirrors Claude Code's countToolCalls / usage tracking.
    """
    tool_name: str
    total_calls: int = 0
    success_calls: int = 0
    error_calls: int = 0
    denied_calls: int = 0
    total_duration: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.success_calls / self.total_calls

    @property
    def avg_duration(self) -> float:
        if self.success_calls == 0:
            return 0.0
        return self.total_duration / self.success_calls

    def record(self, record: ToolCallRecord) -> None:
        self.total_calls += 1
        if record.denied:
            self.denied_calls += 1
        elif record.success:
            self.success_calls += 1
            self.total_duration += record.duration
        else:
            self.error_calls += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool": self.tool_name,
            "total": self.total_calls,
            "success": self.success_calls,
            "error": self.error_calls,
            "denied": self.denied_calls,
            "success_rate": round(self.success_rate, 4),
            "avg_duration_ms": round(self.avg_duration * 1000, 2),
        }


class StatsTracker:
    """Tracks stats across all tools"""

    def __init__(self):
        self._stats: Dict[str, ToolStats] = {}
        self._history: List[ToolCallRecord] = []

    def record(self, record: ToolCallRecord) -> None:
        if record.tool_name not in self._stats:
            self._stats[record.tool_name] = ToolStats(tool_name=record.tool_name)
        self._stats[record.tool_name].record(record)
        self._history.append(record)

    def get(self, tool_name: str) -> Optional[ToolStats]:
        return self._stats.get(tool_name)

    def all(self) -> Dict[str, ToolStats]:
        return self._stats.copy()

    def summary(self) -> Dict[str, Any]:
        return {
            "total_calls": len(self._history),
            "tools": {name: s.to_dict() for name, s in self._stats.items()},
        }

    def reset(self) -> None:
        self._stats.clear()
        self._history.clear()

    @property
    def total_calls(self) -> int:
        return len(self._history)

    @property
    def denied_calls(self) -> int:
        return sum(1 for r in self._history if r.denied)

    @property
    def error_calls(self) -> int:
        return sum(1 for r in self._history if not r.success and not r.denied)


# ─── ManagedToolRegistry ──────────────────────────────────────────────────────

class ManagedToolRegistry(ToolRegistry):
    """
    ToolRegistry with permission control, result formatting, and stats.

    Extends the base ToolRegistry from query_engine.py:
    - Wraps execute() with permission check
    - Formats results via ToolResultFormatter
    - Tracks stats via StatsTracker

    This is the production-grade registry to use in LearnerService
    and DualAgentCoordinator.

    Usage:
        registry = ManagedToolRegistry(
            permission=ToolPermission.allow_only(["read_file", "search"]),
            formatter=ToolResultFormatter(max_length=2000),
        )
        registry.register(ToolDefinition(...))

        result = registry.execute(ToolUseBlock(...))
        print(registry.stats.summary())
    """

    def __init__(
        self,
        permission: Optional[ToolPermission] = None,
        formatter: Optional[ToolResultFormatter] = None,
    ):
        super().__init__()
        self.permission = permission or ToolPermission.allow_all()
        self.formatter = formatter or ToolResultFormatter()
        self.stats = StatsTracker()

    def execute(self, tool_use: ToolUseBlock) -> ToolResultBlock:
        """
        Execute a tool with permission check, formatting, and stats.

        Flow:
          1. Check permission → deny if not allowed
          2. Execute handler
          3. Format result (truncate, metadata)
          4. Record stats
          5. Return ToolResultBlock
        """
        start = time.time()
        tool_name = tool_use.name

        # 1. Permission check
        perm = self.permission.check(tool_name)
        if not perm.allowed:
            logger.warning(f"Tool denied: {tool_name} — {perm.reason}")
            self.stats.record(ToolCallRecord(
                tool_name=tool_name,
                success=False,
                denied=True,
                duration=0.0,
            ))
            return ToolResultBlock(
                tool_use_id=tool_use.id,
                content=self.formatter.format_denied(tool_name, perm.reason or ""),
                is_error=True,
            )

        # 2. Execute
        tool = self._tools.get(tool_name)
        if not tool:
            duration = time.time() - start
            self.stats.record(ToolCallRecord(
                tool_name=tool_name,
                success=False,
                duration=duration,
            ))
            return ToolResultBlock(
                tool_use_id=tool_use.id,
                content=self.formatter.format_error(
                    tool_name, f"Unknown tool: {tool_name}", duration
                ),
                is_error=True,
            )

        try:
            raw_result = tool.handler(tool_use.input)
            duration = time.time() - start

            # 3. Format success
            formatted = self.formatter.format_success(
                tool_name, str(raw_result), duration
            )

            # 4. Record stats + rate limit
            self.permission.record_call(tool_name)
            self.stats.record(ToolCallRecord(
                tool_name=tool_name,
                success=True,
                duration=duration,
            ))

            logger.debug(f"Tool '{tool_name}' OK in {duration*1000:.1f}ms")

            return ToolResultBlock(
                tool_use_id=tool_use.id,
                content=formatted,
            )

        except Exception as e:
            duration = time.time() - start
            logger.error(f"Tool '{tool_name}' error: {e}")
            self.stats.record(ToolCallRecord(
                tool_name=tool_name,
                success=False,
                duration=duration,
            ))
            return ToolResultBlock(
                tool_use_id=tool_use.id,
                content=self.formatter.format_error(tool_name, str(e), duration),
                is_error=True,
            )

    def to_api_format(self) -> List[Dict[str, Any]]:
        """
        Return only permitted tools in API format.

        Filters out denied tools so LLM never sees them.
        """
        all_tools = super().to_api_format()

        if self.permission.allow_list is None and not self.permission.deny_list:
            return all_tools  # No filtering needed

        filtered = []
        for tool_def in all_tools:
            name = tool_def["name"]
            perm = self.permission.check(name)
            if perm.allowed:
                filtered.append(tool_def)
            else:
                logger.debug(f"Tool '{name}' hidden from LLM: {perm.reason}")

        return filtered
