"""Enhanced Compact Engine + Historical Message Archive

Extends the basic ContextCompactor (services/context.py) with:
- Importance scoring: keep high-value messages (errors, key decisions, tool failures)
- LLM-powered summarization (replaceable, with fallback to rule-based)
- Micro-compact: compress individual tool_result blocks in-place
- Session memory: persist compressed summaries to disk
- Full-text search: retrieve relevant past context

Architecture (mirrors Claude Code compact/):
    CompactEngine (core)
    ├── MicroCompactor    — in-place tool_result compression
    ├── ImportanceScorer   — score messages by value
    ├── CompactArchive    — persistent storage + search
    └── CompactSession     — session-scoped lifecycle

Usage:
    engine = CompactEngine(archive_path="memory/sessions/")
    
    # Auto-compact when needed
    if engine.should_compact(messages, tokens):
        result = engine.compact(messages, tokens)
    
    # Search past history
    results = engine.search("how to read files", max_results=5)
    
    # Retrieve relevant context for current conversation
    context = engine.retrieve_context("debugging a tool error", budget_tokens=2000)
"""

import os
import json
import re
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, Tuple
from enum import Enum

from .query_engine import LLMMessage
from .context import (
    ContextCompactor,
    CompactConfig,
    CompactBoundary,
    MessageGroup,
    group_messages,
    estimate_tokens,
    estimate_total_tokens,
)

logger = logging.getLogger(__name__)


# ─── Importance Scoring ──────────────────────────────────────────────────────

@dataclass
class ImportanceScore:
    """Score for a message group's retention value"""
    group_index: int
    score: float           # 0.0-1.0
    reasons: List[str]

    @property
    def label(self) -> str:
        if self.score >= 0.8:
            return "critical"
        elif self.score >= 0.5:
            return "important"
        elif self.score >= 0.3:
            return "useful"
        return "low"


class ImportanceScorer:
    """
    Score message groups by retention value.
    
    High-importance messages (keep during compact):
    - Contain errors or failures
    - Contain key decisions or stage transitions
    - Are the first or last in a conversation
    - Have high tool diversity
    - Contain explicit questions or reflections
    
    Low-importance messages (safe to discard):
    - Repetitive tool calls
    - Long tool outputs with no errors
    - Acknowledgment messages ("ok", "done")
    """
    
    def __init__(
        self,
        custom_rules: Optional[List[Callable[[MessageGroup], float]]] = None,
    ):
        self._custom_rules = custom_rules or []
    
    def score(self, group: MessageGroup, total_groups: int) -> ImportanceScore:
        """Score a single message group"""
        score = 0.0
        reasons = []
        
        # 1. Position bonus: first and last groups are more important
        if group.turn_index == 0:
            score += 0.2
            reasons.append("first_turn")
        if group.turn_index >= total_groups - 2:
            score += 0.15
            reasons.append("recent_turn")
        
        # 2. Error bonus: groups with errors are valuable for learning
        if group.has_error:
            score += 0.3
            reasons.append("has_error")
        
        # 3. Tool diversity: more different tools = more informative
        tool_names = self._extract_tool_names(group)
        if len(tool_names) > 2:
            score += 0.15
            reasons.append(f"tool_diversity({len(tool_names)})")
        
        # 4. Content heuristics
        combined_text = self._extract_text(group)
        
        # Contains explicit learning/reflection markers
        reflection_markers = [
            "learned", "mistake", "correct", "wrong", "should have",
            "improve", "note:", "important", "key insight", "conclusion",
            "总结", "错误", "教训", "改进", "注意",
        ]
        if any(marker in combined_text.lower() for marker in reflection_markers):
            score += 0.2
            reasons.append("reflection_content")
        
        # Short trivial messages are low value
        if len(combined_text.strip()) < 20:
            score -= 0.15
            reasons.append("trivial_content")
        
        # Repetitive patterns
        if self._is_repetitive(combined_text):
            score -= 0.1
            reasons.append("repetitive")
        
        # 5. Custom rules
        for rule in self._custom_rules:
            bonus = rule(group)
            score += bonus
            if bonus != 0:
                reasons.append("custom_rule")
        
        # Clamp to [0, 1]
        score = max(0.0, min(1.0, score))
        
        return ImportanceScore(
            group_index=group.turn_index,
            score=score,
            reasons=reasons,
        )
    
    def score_all(self, groups: List[MessageGroup]) -> List[ImportanceScore]:
        """Score all groups"""
        return [self.score(g, len(groups)) for g in groups]
    
    def _extract_tool_names(self, group: MessageGroup) -> List[str]:
        names = set()
        for msg in group.messages:
            if isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict):
                        if block.get("type") == "tool_use":
                            names.add(block.get("name", ""))
                        elif block.get("type") == "tool_result":
                            names.add("tool_result")
        return list(names)
    
    def _extract_text(self, group: MessageGroup) -> str:
        parts = []
        for msg in group.messages:
            if isinstance(msg.content, str):
                parts.append(msg.content)
            elif isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict):
                        parts.append(block.get("text", "") or block.get("content", "") or "")
        return " ".join(parts)
    
    def _is_repetitive(self, text: str) -> bool:
        """Detect repetitive content (same phrase repeated 3+ times)"""
        words = text.lower().split()
        if len(words) < 10:
            return False
        # Check for repeated 3-word sequences
        trigrams = [" ".join(words[i:i+3]) for i in range(len(words)-2)]
        if len(trigrams) < 3:
            return False
        from collections import Counter
        counts = Counter(trigrams)
        return counts.most_common(1)[0][1] >= 3


# ─── Micro Compactor ─────────────────────────────────────────────────────────

class MicroCompactor:
    """
    In-place compression of tool_result blocks.
    
    Instead of removing entire messages, truncate individual tool outputs
    to save tokens while preserving the conversation structure.
    
    Mirrors Claude Code's microCompact.ts.
    """
    
    def __init__(self, max_tool_result_chars: int = 200):
        self.max_chars = max_tool_result_chars
        self._truncate_count = 0
    
    def compact_message(self, msg: LLMMessage) -> LLMMessage:
        """Micro-compact a single message's tool_result blocks"""
        if not isinstance(msg.content, list):
            return msg
        
        new_content = []
        for block in msg.content:
            if not isinstance(block, dict):
                new_content.append(block)
                continue
            
            if block.get("type") == "tool_result":
                content = block.get("content", "")
                if isinstance(content, str) and len(content) > self.max_chars:
                    block = dict(block)
                    block["content"] = (
                        content[:self.max_chars] + f"\n... [{len(content)} chars truncated]"
                    )
                    self._truncate_count += 1
            elif block.get("type") == "text":
                # Also truncate very long text blocks
                text = block.get("text", "")
                if isinstance(text, str) and len(text) > self.max_chars * 2:
                    block = dict(block)
                    block["text"] = text[:self.max_chars * 2] + "\n... [truncated]"
            
            new_content.append(block)
        
        return LLMMessage(role=msg.role, content=new_content)
    
    def compact_messages(self, messages: List[LLMMessage]) -> List[LLMMessage]:
        """Micro-compact all messages"""
        self._truncate_count = 0
        return [self.compact_message(m) for m in messages]
    
    @property
    def truncate_count(self) -> int:
        return self._truncate_count


# ─── Compact Archive (Persistence) ────────────────────────────────────────────

@dataclass
class ArchivedCompact:
    """A single compacted session stored on disk"""
    session_id: str
    timestamp: str
    summary: str
    message_count: int
    turn_count: int
    tool_call_count: int
    error_count: int
    original_tokens: int
    compressed_tokens: int
    importance_scores: Dict[int, float]  # turn_index -> score
    tags: List[str] = field(default_factory=list)


class CompactArchive:
    """
    Persistent storage for compacted session summaries.
    
    Stores compressed conversation summaries as JSON Lines (.jsonl).
    Supports:
    - Append new compacts
    - Full-text search over summaries
    - Retrieve by session ID
    - Token-aware retrieval (fit within budget)
    
    Mirrors Claude Code's memdir/ pattern:
    - Lightweight file-based storage
    - No external database dependency
    - Human-readable .jsonl format
    
    Storage format:
        memory/sessions/
        ├── 2026-04-03.jsonl     # One file per day
        ├── 2026-04-02.jsonl
        └── ...
    """
    
    def __init__(self, archive_dir: str):
        self.archive_dir = archive_dir
        os.makedirs(archive_dir, exist_ok=True)
    
    def _today_file(self) -> str:
        return os.path.join(self.archive_dir, f"{time.strftime('%Y-%m-%d')}.jsonl")
    
    def save(self, compact: ArchivedCompact) -> None:
        """Append a compacted session to today's archive"""
        path = self._today_file()
        record = {
            "session_id": compact.session_id,
            "timestamp": compact.timestamp,
            "summary": compact.summary,
            "message_count": compact.message_count,
            "turn_count": compact.turn_count,
            "tool_call_count": compact.tool_call_count,
            "error_count": compact.error_count,
            "original_tokens": compact.original_tokens,
            "compressed_tokens": compact.compressed_tokens,
            "importance_scores": compact.importance_scores,
            "tags": compact.tags,
        }
        with open(path, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    def search(
        self,
        query: str,
        max_results: int = 10,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Full-text search over archived compacts.
        
        Simple keyword matching (no external dependencies).
        In production, can be replaced with vector search / SQLite FTS.
        """
        results = []
        query_lower = query.lower()
        query_tokens = set(query_lower.split())
        
        # Determine which files to search
        if date_from and date_to:
            files = self._files_in_range(date_from, date_to)
        else:
            files = sorted(self._list_files())
        
        # Search in reverse chronological order (most recent first)
        for filepath in reversed(files):
            if not os.path.exists(filepath):
                continue
            for line in self._read_lines(filepath):
                try:
                    record = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                
                # Score: count matching tokens
                text = f"{record.get('summary', '')} {' '.join(record.get('tags', []))}".lower()
                match_count = sum(1 for t in query_tokens if t in text)
                
                if match_count > 0:
                    record["_score"] = match_count
                    record["_source_file"] = os.path.basename(filepath)
                    results.append(record)
                    
                    if len(results) >= max_results:
                        # Sort by score descending
                        results.sort(key=lambda r: r["_score"], reverse=True)
                        return results
        
        results.sort(key=lambda r: r["_score"], reverse=True)
        return results
    
    def retrieve_context(
        self,
        query: str,
        budget_tokens: int = 2000,
    ) -> str:
        """
        Retrieve relevant past context that fits within a token budget.
        
        Uses search to find relevant compacts, then assembles
        a context string that fits within the budget.
        """
        results = self.search(query, max_results=20)
        if not results:
            return ""
        
        context_parts = []
        total_tokens = 0
        
        for record in results:
            summary = record.get("summary", "")
            ts = record.get("timestamp", "")
            part = f"[{ts}] {summary}"
            part_tokens = estimate_tokens(part)
            
            if total_tokens + part_tokens > budget_tokens:
                break
            
            context_parts.append(part)
            total_tokens += part_tokens
        
        if not context_parts:
            return ""
        
        header = f"Relevant past context ({len(context_parts)} sessions):"
        return header + "\n" + "\n".join(context_parts)
    
    def list_sessions(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List archived sessions (most recent first)"""
        sessions = []
        
        files = sorted(self._list_files(), reverse=True)
        for filepath in files:
            if not os.path.exists(filepath):
                continue
            for line in self._read_lines(filepath):
                try:
                    record = json.loads(line)
                    sessions.append(record)
                except (json.JSONDecodeError, ValueError):
                    continue
                if len(sessions) >= limit:
                    return sessions
        
        return sessions
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific session by ID"""
        for filepath in self._list_files():
            if not os.path.exists(filepath):
                continue
            for line in self._read_lines(filepath):
                try:
                    record = json.loads(line)
                    if record.get("session_id") == session_id:
                        return record
                except (json.JSONDecodeError, ValueError):
                    continue
        return None
    
    def stats(self) -> Dict[str, Any]:
        """Archive statistics"""
        total_sessions = 0
        total_files = 0
        
        for filepath in self._list_files():
            if not os.path.exists(filepath):
                continue
            total_files += 1
            for line in self._read_lines(filepath):
                if line.strip():
                    total_sessions += 1
        
        return {
            "archive_dir": self.archive_dir,
            "total_sessions": total_sessions,
            "total_files": total_files,
            "disk_usage_mb": self._disk_usage_mb(),
        }
    
    # ─── Internal ─────────────────────────────────────────────────────────
    
    def _list_files(self) -> List[str]:
        if not os.path.isdir(self.archive_dir):
            return []
        return sorted([
            os.path.join(self.archive_dir, f)
            for f in os.listdir(self.archive_dir)
            if f.endswith(".jsonl")
        ])
    
    def _files_in_range(self, date_from: str, date_to: str) -> List[str]:
        result = []
        for filepath in self._list_files():
            basename = os.path.basename(filepath).replace(".jsonl", "")
            if date_from <= basename <= date_to:
                result.append(filepath)
        return sorted(result)
    
    def _read_lines(self, filepath: str) -> List[str]:
        try:
            with open(filepath, "r") as f:
                return f.readlines()
        except Exception:
            return []
    
    def _disk_usage_mb(self) -> float:
        total = 0
        for filepath in self._list_files():
            if os.path.exists(filepath):
                total += os.path.getsize(filepath)
        return round(total / (1024 * 1024), 2)


# ─── Compact Engine (Main API) ────────────────────────────────────────────────

class CompactEngine:
    """
    Enhanced compact engine with importance scoring and archive search.
    
    Extends ContextCompactor with:
    - ImportanceScorer: keep valuable messages during compact
    - MicroCompactor: in-place tool_result truncation
    - CompactArchive: persistent storage + search
    
    Usage:
        engine = CompactEngine(archive_path="memory/sessions/")
        
        # Auto-compact with importance scoring
        if engine.should_compact(messages, tokens):
            result = engine.compact(messages, tokens)
            # result.archive is automatically saved
        
        # Search past history
        results = engine.search("tool error handling")
        
        # Retrieve relevant context
        context = engine.retrieve_context("debugging", budget_tokens=2000)
    """
    
    def __init__(
        self,
        config: Optional[CompactConfig] = None,
        archive_path: Optional[str] = None,
        summarize_fn: Optional[Callable[[List[MessageGroup]], str]] = None,
        importance_rules: Optional[List[Callable[[MessageGroup], float]]] = None,
    ):
        self.config = config or CompactConfig()
        self._summarize_fn = summarize_fn
        self._scorer = ImportanceScorer(custom_rules=importance_rules)
        self._micro_compactor = MicroCompactor(
            max_tool_result_chars=self.config.max_tool_result_length
        )
        
        # Archive (optional)
        self.archive: Optional[CompactArchive] = None
        if archive_path:
            self.archive = CompactArchive(archive_path)
        
        # Session ID for tracking
        self._session_id = f"session_{int(time.time() * 1000)}"
    
    @property
    def session_id(self) -> str:
        return self._session_id
    
    @property
    def scorer(self) -> ImportanceScorer:
        return self._scorer
    
    @property
    def micro_compactor(self) -> MicroCompactor:
        return self._micro_compactor
    
    def should_compact(
        self,
        messages: List[LLMMessage],
        current_tokens: int,
    ) -> Tuple[bool, str]:
        """Check if compaction is needed (same interface as ContextCompactor)"""
        from .context import ContextCompactor
        # Use a lightweight check — detailed logic in compact()
        max_tokens = self.config.max_tokens
        threshold = self.config.warning_threshold
        
        if current_tokens >= max_tokens * threshold:
            return True, f"Token count ({current_tokens}) exceeds {threshold:.0%} threshold"
        
        if len(messages) < self.config.keep_recent * 2:
            return False, f"Only {len(messages)} messages"
        
        return False, "No compaction needed"
    
    def compact(
        self,
        messages: List[LLMMessage],
        current_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Enhanced compact with importance scoring.
        
        Algorithm:
        1. Group messages into turns
        2. Score each group by importance
        3. Keep: system + high-importance + recent messages
        4. Summarize discarded messages
        5. Micro-compact kept messages (truncate tool results)
        6. Archive the compact (if archive enabled)
        
        Returns dict with:
            messages: compressed message list
            boundary: CompactBoundary
            scores: importance scores
            truncated: micro-compact truncation count
            saved_tokens: tokens saved
        """
        if current_tokens is None:
            current_tokens = estimate_total_tokens(messages)
        
        original_count = len(messages)
        original_tokens = current_tokens
        
        # Step 1: Separate system messages
        system_msgs = [m for m in messages if m.role == "system"]
        non_system = [m for m in messages if m.role != "system"]
        
        # Step 2: Group and score
        groups = group_messages(non_system)
        scores = self._scorer.score_all(groups)
        
        # Step 3: Select what to keep
        keep_count = min(self.config.keep_recent, len(non_system))
        recent_msgs = non_system[-keep_count:] if non_system else []
        recent_indices = set(range(len(groups) - keep_count, len(groups))) if keep_count < len(groups) else set()
        
        # Also keep high-importance groups not in recent
        high_importance_msgs = []
        for i, (group, score) in enumerate(zip(groups, scores)):
            if i not in recent_indices and score.score >= 0.5:
                high_importance_msgs.extend(group.messages)
        
        # Step 4: Determine discarded
        recent_flat = set(id(m) for m in recent_msgs)
        hi_flat = set(id(m) for m in high_importance_msgs)
        
        discard_groups = []
        for group in groups:
            all_recent = all(id(m) in recent_flat for m in group.messages)
            all_hi = all(id(m) in hi_flat for m in group.messages)
            if not all_recent and not all_hi:
                discard_groups.append(group)
        
        # Step 5: Summarize discarded
        summarize_fn = self._summarize_fn or self._build_detailed_summary
        summary = summarize_fn(discard_groups, scores)
        
        # Step 6: Build boundary
        boundary = CompactBoundary(
            summary=summary,
            preserved_count=len(recent_msgs) + len(high_importance_msgs),
            removed_count=sum(len(g.messages) for g in discard_groups),
            original_tokens=original_tokens,
            compressed_tokens=0,
        )
        
        # Step 7: Assemble compressed messages
        compressed: List[LLMMessage] = list(system_msgs)
        compressed.append(boundary.to_message())
        compressed.extend(high_importance_msgs)
        compressed.extend(recent_msgs)
        
        # Step 8: Micro-compact (truncate long tool results in kept messages)
        self._micro_compactor._truncate_count = 0
        compressed = self._micro_compactor.compact_messages(compressed)
        
        boundary.compressed_tokens = estimate_total_tokens(compressed)
        
        # Step 9: Archive
        if self.archive:
            archived = ArchivedCompact(
                session_id=self._session_id,
                timestamp=time.strftime("%Y-%m-%d %H:%M"),
                summary=summary,
                message_count=original_count,
                turn_count=len(groups),
                tool_call_count=sum(
                    1 for g in groups for m in g.messages
                    if isinstance(m.content, list)
                    and any(b.get("type") == "tool_use" for b in m.content if isinstance(b, dict))
                ),
                error_count=sum(1 for s in scores if "has_error" in s.reasons),
                original_tokens=original_tokens,
                compressed_tokens=boundary.compressed_tokens,
                importance_scores={
                    s.group_index: round(s.score, 3) for s in scores
                },
            )
            self.archive.save(archived)
        
        logger.info(
            f"Enhanced compact: {original_count} → {len(compressed)} msgs "
            f"({original_tokens} → {boundary.compressed_tokens} tokens, "
            f"micro-truncated={self._micro_compactor.truncate_count})"
        )
        
        return {
            "messages": compressed,
            "boundary": boundary,
            "scores": scores,
            "truncated": self._micro_compactor.truncate_count,
            "saved_tokens": original_tokens - boundary.compressed_tokens,
            "compression_ratio": round(boundary.compressed_tokens / max(original_tokens, 1), 3),
        }
    
    def micro_compact(self, messages: List[LLMMessage]) -> List[LLMMessage]:
        """Run only micro-compaction (truncate tool results in-place)"""
        return self._micro_compactor.compact_messages(messages)
    
    def search(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search archived session history"""
        if not self.archive:
            logger.warning("No archive configured, cannot search")
            return []
        return self.archive.search(query, max_results=max_results)
    
    def retrieve_context(self, query: str, budget_tokens: int = 2000) -> str:
        """Retrieve relevant past context within token budget"""
        if not self.archive:
            return ""
        return self.archive.retrieve_context(query, budget_tokens)
    
    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List archived sessions"""
        if not self.archive:
            return []
        return self.archive.list_sessions(limit=limit)
    
    def stats(self) -> Dict[str, Any]:
        """Get engine + archive statistics"""
        result = {
            "session_id": self._session_id,
            "config": {
                "max_tokens": self.config.max_tokens,
                "warning_threshold": self.config.warning_threshold,
                "keep_recent": self.config.keep_recent,
            },
        }
        if self.archive:
            result["archive"] = self.archive.stats()
        return result
    
    # ─── Detailed Summary Builder ──────────────────────────────────────────
    
    def _build_detailed_summary(
        self,
        groups: List[MessageGroup],
        scores: List[ImportanceScore],
    ) -> str:
        """Build a detailed summary from importance scores"""
        if not groups:
            return "No previous context."
        
        total_msgs = sum(len(g.messages) for g in groups)
        
        # Collect highlights
        highlights = []
        for group, score in zip(groups, scores):
            if score.score >= 0.5 and score.reasons:
                highlights.append(
                    f"Turn {group.turn_index}: "
                    + ", ".join(score.reasons)
                    + f" (score={score.score:.2f})"
                )
        
        # Count tool calls and errors
        tool_calls = 0
        errors = sum(1 for s in scores if "has_error" in s.reasons)
        for g in groups:
            for m in g.messages:
                if isinstance(m.content, list):
                    tool_calls += sum(
                        1 for b in m.content
                        if isinstance(b, dict) and b.get("type") == "tool_use"
                    )
        
        # Extract keywords from user messages (first 20 chars of each)
        user_topics = []
        for g in groups:
            for m in g.messages:
                if m.role == "user":
                    text = ""
                    if isinstance(m.content, str):
                        text = m.content.strip()
                    elif isinstance(m.content, list):
                        for b in m.content:
                            if isinstance(b, dict) and b.get("type") == "text":
                                text = b.get("text", "").strip()
                    if text and len(text) > 5:
                        user_topics.append(text[:50])
        topic_str = "; ".join(user_topics[:5]) if user_topics else ""
        
        parts = [
            f"Removed {total_msgs} messages across {len(groups)} turns.",
            f"Tool calls: {tool_calls}, Errors: {errors}.",
        ]
        
        if topic_str:
            parts.append(f"Topics: {topic_str}")
        
        if highlights:
            parts.append("Key events: " + "; ".join(highlights[:5]))
        
        return " ".join(parts)
