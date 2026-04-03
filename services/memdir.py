"""Persistent Memory Directory — memdir/

Reference: Claude Code src/memdir/memdir.ts

Implements a file-based, persistent memory system:
- MEMORY.md: index entrypoint (loaded into system prompt)
- Topic files: individual memories with frontmatter
- 4 memory types: user, feedback, project, reference
- Search: grep-style keyword matching over .md files
- Memory aging: decay old memories' relevance

For Curriculum-Forge, memories store:
- user: Agent A/B preferences, collaboration style
- feedback: Reward patterns, reward calculation feedback
- project: Curriculum configs, RL hyperparameters
- reference: Experiment results, past training runs

Storage layout:
    memory/
    ├── MEMORY.md              # Index (≤200 lines, ≤25KB)
    ├── user_role.md           # Topic files
    ├── feedback_reward.md
    ├── project_config.md
    ├── reference_results.md
    └── session_2026-04-03.md  # Daily session log

Usage:
    mdir = MemoryDir("memory/", memory_type="agent")
    
    # Save a memory
    mdir.save("user_role.md", {
        "name": "user_role",
        "description": "User prefers concise responses",
        "type": "user",
        "content": "...",
    })
    
    # Load into system prompt
    prompt = mdir.build_memory_prompt()
    
    # Search past memories
    results = mdir.find_relevant("reward calculation errors")
    
    # Retrieve for current context
    context = mdir.retrieve_context("GRPO training", budget_tokens=1000)
"""

import os
import re
import time
import json
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

import logging

logger = logging.getLogger(__name__)


# ─── Constants ────────────────────────────────────────────────────────────────

ENTRYPOINT_NAME = "MEMORY.md"
MAX_ENTRYPOINT_LINES = 200
MAX_ENTRYPOINT_BYTES = 25_000
MAX_ENTRYPOINT_CHARS = 150  # per index line


# ─── Memory Types ─────────────────────────────────────────────────────────────

class MemoryType(Enum):
    USER = "user"           # Who the user is, preferences, how they collaborate
    FEEDBACK = "feedback"   # User feedback, corrections, preferences on outputs
    PROJECT = "project"     # Project-specific: configs, architecture, decisions
    REFERENCE = "reference" # Reference info: docs, patterns, APIs

    @classmethod
    def all_sections(cls) -> List[str]:
        return [
            "## Memory types",
            "",
            "Each memory file has a `type` field in its frontmatter. Use the type that best fits:",
            "",
            "### user",
            "Who the user is, their role, goals, preferences, working style, and anything personal. Updated when the user tells you something about themselves.",
            "",
            "### feedback",
            "Feedback from the user about your outputs: corrections, what went well, what to improve. Updated when the user gives you feedback.",
            "",
            "### project",
            "Project-specific context: architecture, conventions, the current state of the codebase, open decisions, active tasks.",
            "",
            "### reference",
            "Reference information that is useful to have available: documentation, external systems, APIs, important links.",
        ]


# ─── Data Models ─────────────────────────────────────────────────────────────

@dataclass
class MemoryEntry:
    """A single memory stored in a topic file"""
    name: str
    description: str
    type: MemoryType
    content: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    def to_frontmatter(self) -> str:
        """Serialize to YAML-like frontmatter"""
        created = self.created_at or time.strftime("%Y-%m-%d")
        updated = self.updated_at or created
        tags_str = ", ".join(self.tags) if self.tags else ""
        return "\n".join([
            "---",
            f"name: {self.name}",
            f"description: {self.description}",
            f"type: {self.type.value}",
            f"created: {created}",
            f"updated: {updated}",
            f"tags: [{tags_str}]" if tags_str else "tags: []",
            "---",
            "",
            self.content,
        ])

    @classmethod
    def from_frontmatter(cls, text: str) -> Optional["MemoryEntry"]:
        """Parse a memory file with frontmatter"""
        if not text.strip().startswith("---"):
            return None
        
        match = re.match(r"^---\n(.*?)\n---\n(.*)$", text.strip(), re.DOTALL)
        if not match:
            return None
        
        fm_text, content = match.groups()
        fields = {}
        for line in fm_text.split("\n"):
            if ":" in line:
                key, _, value = line.partition(":")
                fields[key.strip()] = value.strip().strip('"')
        
        try:
            mem_type = MemoryType(fields.get("type", "user"))
        except ValueError:
            mem_type = MemoryType.USER
        
        # Parse tags
        tags_raw = fields.get("tags", "[]")
        tags = []
        if tags_raw and tags_raw not in ("[]", ""):
            # Handle "[tag1, tag2]" or "tag1, tag2"
            inner = tags_raw.strip("[]").strip()
            if inner:
                tags = [t.strip().strip('"') for t in inner.split(",")]
        
        return cls(
            name=fields.get("name", "untitled"),
            description=fields.get("description", ""),
            type=mem_type,
            content=content.strip(),
            created_at=fields.get("created") or fields.get("updated"),
            updated_at=fields.get("updated") or fields.get("created"),
            tags=tags,
        )


@dataclass
class IndexEntry:
    """A single line in MEMORY.md"""
    title: str
    file: str
    hook: str

    @classmethod
    def parse(cls, line: str) -> Optional["IndexEntry"]:
        """Parse: `- [Title](file.md) — one-line hook`"""
        m = re.match(r"- \[(.+?)\]\((.+?)\)(?: — (.+))?", line.strip())
        if not m:
            return None
        return cls(title=m.group(1), file=m.group(2), hook=m.group(3) or "")


# ─── MemoryDir ───────────────────────────────────────────────────────────────

class MemoryDir:
    """
    Persistent file-based memory directory.
    
    Mirrors Claude Code's memdir.ts:
    - MEMORY.md is the index (loaded into system prompt)
    - Topic files store individual memories with frontmatter
    - Grep-style search over .md files
    - Memory aging for relevance scoring
    
    Usage:
        mdir = MemoryDir("memory/")
        mdir.save("preferences.md", {...})
        prompt = mdir.build_memory_prompt()
        results = mdir.search("reward calculation")
        context = mdir.retrieve_context("GRPO", budget_tokens=1000)
    """
    
    def __init__(
        self,
        memory_dir: str,
        memory_type: str = "agent",
        extra_guidelines: Optional[List[str]] = None,
    ):
        self.memory_dir = os.path.abspath(memory_dir)
        self.memory_type = memory_type  # "agent" or "auto"
        self.extra_guidelines = extra_guidelines or []
        os.makedirs(self.memory_dir, exist_ok=True)
    
    @property
    def entrypoint_path(self) -> str:
        return os.path.join(self.memory_dir, ENTRYPOINT_NAME)
    
    # ─── Directory Management ──────────────────────────────────────────────
    
    def ensure_exists(self) -> None:
        """Ensure memory directory exists (idempotent)"""
        os.makedirs(self.memory_dir, exist_ok=True)
    
    def exists(self) -> bool:
        """Check if memory directory exists"""
        return os.path.isdir(self.memory_dir)
    
    # ─── Index Operations ─────────────────────────────────────────────────
    
    def _read_index(self) -> List[IndexEntry]:
        """Parse MEMORY.md into index entries"""
        if not os.path.exists(self.entrypoint_path):
            return []
        
        try:
            with open(self.entrypoint_path, "r") as f:
                content = f.read()
        except Exception:
            return []
        
        entries = []
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("- ["):
                entry = IndexEntry.parse(line)
                if entry:
                    entries.append(entry)
        return entries
    
    def _write_index(self, entries: List[IndexEntry]) -> None:
        """Write index entries to MEMORY.md"""
        lines = ["# auto memory", "", ""]
        
        # Add type sections
        by_type: Dict[MemoryType, List[IndexEntry]] = {t: [] for t in MemoryType}
        for entry in entries:
            # Infer type from filename
            mem = self.get(entry.file)
            if mem:
                by_type[mem.type].append(entry)
            else:
                by_type[MemoryType.PROJECT].append(entry)
        
        for mem_type in MemoryType:
            type_entries = by_type[mem_type]
            if not type_entries:
                continue
            lines.append(f"### {mem_type.value}")
            lines.append("")
            for e in type_entries:
                hook = f" — {e.hook}" if e.hook else ""
                lines.append(f"- [{e.title}]({e.file}){hook}")
            lines.append("")
        
        content = "\n".join(lines).strip() + "\n"
        
        # Truncate if needed
        content_lines = content.split("\n")
        was_truncated = len(content_lines) > MAX_ENTRYPOINT_LINES
        if was_truncated:
            content_lines = content_lines[:MAX_ENTRYPOINT_LINES]
            content = "\n".join(content_lines)
            content += f"\n\n> WARNING: MEMORY.md is {len(content_lines)} lines (limit: {MAX_ENTRYPOINT_LINES}). Index truncated."
        
        was_byte_truncated = len(content.encode("utf-8")) > MAX_ENTRYPOINT_BYTES
        if was_byte_truncated:
            content_bytes = content.encode("utf-8")
            cut_at = content_bytes.rfind(b"\n", 0, MAX_ENTRYPOINT_BYTES)
            if cut_at > 0:
                content = content_bytes[:cut_at].decode("utf-8")
            content += f"\n\n> WARNING: MEMORY.md is {len(content_bytes)} bytes (limit: {MAX_ENTRYPOINT_BYTES}). Index truncated."
        
        with open(self.entrypoint_path, "w") as f:
            f.write(content)
    
    # ─── Memory CRUD ──────────────────────────────────────────────────────
    
    def save(self, filename: str, entry: MemoryEntry) -> str:
        """
        Save a memory to a topic file and update MEMORY.md index.
        
        If the file already exists, updates it (preserves created_at).
        Mutates entry.created_at if creating a new file.
        """
        filepath = os.path.join(self.memory_dir, filename)
        
        # Update timestamps
        if os.path.exists(filepath):
            existing = self.get(filename)
            if existing:
                entry.created_at = existing.created_at
                entry.updated_at = time.strftime("%Y-%m-%d")
            else:
                entry.created_at = time.strftime("%Y-%m-%d")
                entry.updated_at = entry.created_at
        else:
            entry.created_at = time.strftime("%Y-%m-%d")
            entry.updated_at = entry.created_at
        
        # Write topic file
        with open(filepath, "w") as f:
            f.write(entry.to_frontmatter())
        
        # Update index
        entries = self._read_index()
        
        # Remove old entry for this file
        entries = [e for e in entries if e.file != filename]
        
        # Add new entry
        entries.append(IndexEntry(
            title=entry.name,
            file=filename,
            hook=entry.description[:MAX_ENTRYPOINT_CHARS],
        ))
        
        self._write_index(entries)
        logger.info(f"Memory saved: {filename}")
        return filepath
    
    def get(self, filename: str) -> Optional[MemoryEntry]:
        """Load a specific memory by filename"""
        filepath = os.path.join(self.memory_dir, filename)
        if not os.path.exists(filepath):
            return None
        
        try:
            with open(filepath, "r") as f:
                text = f.read()
            return MemoryEntry.from_frontmatter(text)
        except Exception:
            return None
    
    def list_all(self) -> List[MemoryEntry]:
        """List all memories in the directory"""
        memories = []
        if not os.path.isdir(self.memory_dir):
            return memories
        
        for fname in os.listdir(self.memory_dir):
            if not fname.endswith(".md") or fname == ENTRYPOINT_NAME:
                continue
            mem = self.get(fname)
            if mem:
                memories.append(mem)
        return memories
    
    def delete(self, filename: str) -> bool:
        """Delete a memory and remove it from the index"""
        filepath = os.path.join(self.memory_dir, filename)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception:
                return False
        
        # Update index
        entries = self._read_index()
        entries = [e for e in entries if e.file != filename]
        self._write_index(entries)
        return True
    
    # ─── Search ───────────────────────────────────────────────────────────
    
    def search(
        self,
        query: str,
        max_results: int = 10,
        use_subprocess: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Grep-style search over memory .md files.
        
        Searches both filenames and content.
        Returns ranked results (more keyword matches = higher rank).
        
        Set use_subprocess=False for cross-platform (pure Python fallback).
        """
        if not os.path.isdir(self.memory_dir):
            return []
        
        query_lower = query.lower()
        query_tokens = set(query_lower.split())
        
        results = []
        
        if use_subprocess:
            try:
                result = subprocess.run(
                    ["grep", "-rn", query, self.memory_dir,
                     "--include=*.md", "--exclude=" + ENTRYPOINT_NAME],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode in (0, 1):  # 0=found, 1=not found
                    for line in result.stdout.strip().split("\n"):
                        if not line:
                            continue
                        parts = line.split(":", 2)
                        if len(parts) >= 3:
                            fname = os.path.basename(parts[0])
                            line_no = parts[1]
                            text = parts[2]
                            results.append({
                                "file": fname,
                                "line": int(line_no),
                                "text": text.strip(),
                                "score": self._score_match(query_lower, text),
                            })
            except Exception as e:
                logger.warning(f"grep subprocess failed: {e}, falling back to pure Python")
                use_subprocess = False
        
        if not use_subprocess or not results:
            # Pure Python fallback
            if not os.path.isdir(self.memory_dir):
                return []
            
            for fname in os.listdir(self.memory_dir):
                if not fname.endswith(".md") or fname == ENTRYPOINT_NAME:
                    continue
                filepath = os.path.join(self.memory_dir, fname)
                try:
                    with open(filepath, "r") as f:
                        lines = f.readlines()
                    for i, line in enumerate(lines):
                        if query_lower in line.lower():
                            results.append({
                                "file": fname,
                                "line": i + 1,
                                "text": line.strip(),
                                "score": self._score_match(query_lower, line),
                            })
                except Exception:
                    continue
        
        # Rank and dedupe by file
        by_file: Dict[str, Dict] = {}
        for r in sorted(results, key=lambda x: x["score"], reverse=True):
            fname = r["file"]
            if fname not in by_file or r["score"] > by_file[fname]["score"]:
                by_file[fname] = r
        
        ranked = sorted(by_file.values(), key=lambda x: x["score"], reverse=True)
        return ranked[:max_results]
    
    def _score_match(self, query: str, text: str) -> float:
        """Score how well text matches query"""
        text_lower = text.lower()
        score = 0.0
        
        for token in query.split():
            count = text_lower.count(token)
            score += count * 0.5
        
        # Title/name match bonus
        for token in query.split():
            if token in text_lower[:100]:
                score += 1.0
        
        return score
    
    # ─── Memory Age & Relevance ─────────────────────────────────────────────
    
    def get_memory_age_days(self, filename: str) -> int:
        """Get age of a memory file in days"""
        filepath = os.path.join(self.memory_dir, filename)
        if not os.path.exists(filepath):
            return 999
        
        mtime = os.path.getmtime(filepath)
        age_seconds = time.time() - mtime
        return int(age_seconds / 86400)
    
    def get_memory_age_score(self, filename: str) -> float:
        """
        Score memory by age (0.0-1.0, older = lower).
        
        Mirrors Claude Code's memoryAge.ts:
        - Recent (< 7 days): 1.0
        - 7-30 days: linear decay to 0.5
        - 30-90 days: linear decay to 0.2
        - > 90 days: 0.1
        """
        days = self.get_memory_age_days(filename)
        
        if days <= 7:
            return 1.0
        elif days <= 30:
            return 1.0 - 0.5 * (days - 7) / 23
        elif days <= 90:
            return 0.5 - 0.3 * (days - 30) / 60
        else:
            return max(0.1, 0.2 - 0.1 * (days - 90) / 365)
    
    def retrieve_context(
        self,
        query: str,
        budget_tokens: int = 2000,
        max_results: int = 5,
    ) -> str:
        """
        Retrieve relevant memories that fit within a token budget.
        
        Combines search relevance + memory age scoring.
        Returns formatted context string.
        """
        # Search memories
        search_results = self.search(query, max_results=max_results * 2)
        
        if not search_results:
            return ""
        
        # Score by relevance × age
        scored = []
        for result in search_results:
            fname = result["file"]
            relevance = result.get("score", 0.5)
            age_score = self.get_memory_age_score(fname)
            combined = relevance * age_score
            
            mem = self.get(fname)
            if mem:
                scored.append({
                    "file": fname,
                    "name": mem.name,
                    "type": mem.type.value,
                    "content": mem.content[:500],  # limit content
                    "combined_score": combined,
                    "relevance": relevance,
                    "age_score": age_score,
                    "age_days": self.get_memory_age_days(fname),
                })
        
        scored.sort(key=lambda x: x["combined_score"], reverse=True)
        scored = scored[:max_results]
        
        # Assemble context within budget
        context_parts = []
        total_chars = 0
        budget_chars = budget_tokens * 4  # ~4 chars/token
        
        for item in scored:
            part = (
                f"## [{item['type']}] {item['name']} (age: {item['age_days']}d, score: {item['combined_score']:.2f})\n"
                f"{item['content']}"
            )
            if total_chars + len(part) > budget_chars:
                break
            context_parts.append(part)
            total_chars += len(part)
        
        if not context_parts:
            return ""
        
        return "\n\n".join(context_parts)
    
    # ─── Prompt Building ──────────────────────────────────────────────────
    
    def build_memory_prompt(
        self,
        include_content: bool = True,
    ) -> str:
        """
        Build the memory prompt for system prompt injection.
        
        Args:
            include_content: If True, includes MEMORY.md content.
                           If False, returns only the behavioral instructions.
        """
        self.ensure_exists()
        
        lines = self._build_instructions()
        
        if include_content:
            lines.append("")
            lines.append(f"## {ENTRYPOINT_NAME}")
            lines.append("")
            
            if os.path.exists(self.entrypoint_path):
                try:
                    with open(self.entrypoint_path, "r") as f:
                        raw = f.read()
                    
                    # Truncate if needed
                    trimmed = raw.strip()
                    content_lines = trimmed.split("\n")
                    
                    if len(content_lines) > MAX_ENTRYPOINT_LINES:
                        trimmed = "\n".join(content_lines[:MAX_ENTRYPOINT_LINES])
                        trimmed += f"\n\n> WARNING: {ENTRYPOINT_NAME} is {len(content_lines)} lines (limit: {MAX_ENTRYPOINT_LINES}). Only part was loaded."
                    
                    byte_count = len(trimmed.encode("utf-8"))
                    if byte_count > MAX_ENTRYPOINT_BYTES:
                        bytes_b = trimmed.encode("utf-8")
                        cut_at = bytes_b.rfind(b"\n", 0, MAX_ENTRYPOINT_BYTES)
                        if cut_at > 0:
                            trimmed = bytes_b[:cut_at].decode("utf-8")
                        trimmed += f"\n\n> WARNING: {ENTRYPOINT_NAME} is {byte_count} bytes (limit: {MAX_ENTRYPOINT_BYTES}). Index truncated."
                    
                    lines.append(trimmed)
                except Exception:
                    lines.append(f"Your {ENTRYPOINT_NAME} is empty.")
            else:
                lines.append(
                    f"Your {ENTRYPOINT_NAME} is currently empty. "
                    "When you save new memories, they will appear here."
                )
        
        return "\n".join(lines)
    
    def _build_instructions(self) -> List[str]:
        """Build behavioral instructions (without MEMORY.md content)"""
        display_name = "auto memory"
        
        how_to_save = [
            "## How to save memories",
            "",
            "Saving a memory is a two-step process:",
            "",
            "**Step 1** — write the memory to its own file (e.g., `user_role.md`, `feedback_reward.md`) using this frontmatter format:",
            "",
            "```yaml",
            "---",
            "name: <title>",
            'description: <one-line hook under 150 chars>',
            "type: <user|feedback|project|reference>",
            "created: YYYY-MM-DD",
            "updated: YYYY-MM-DD",
            "tags: []",
            "---",
            "",
            "<memory content>",
            "```",
            "",
            f"**Step 2** — add a pointer to that file in `{ENTRYPOINT_NAME}`. "
            f"`{ENTRYPOINT_NAME}` is an index, not a memory — each entry should be one line, "
            f"under ~150 characters: `- [Title](file.md) — one-line hook`. "
            f"Never write memory content directly into `{ENTRYPOINT_NAME}`.",
            "",
            f"- `{ENTRYPOINT_NAME}` is always loaded into your conversation context — "
            f"lines after {MAX_ENTRYPOINT_LINES} will be truncated, so keep the index concise",
            "- Keep the name, description, and type fields in memory files up-to-date",
            "- Organize memory semantically by topic, not chronologically",
            "- Update or remove memories that turn out to be wrong or outdated",
            "- Do not write duplicate memories. Check for existing files before writing new ones.",
        ]
        
        lines = [
            f"# {display_name}",
            "",
            f"You have a persistent, file-based memory system at `{self.memory_dir}`. "
            "This directory already exists — write to it directly.",
            "",
            "Build up this memory system over time so that future conversations can have "
            "a complete picture of who you are working with, how to collaborate, "
            "what behaviors to avoid or repeat, and the context behind the work.",
            "",
            "If the user explicitly asks you to remember something, save it immediately. "
            "If they ask you to forget something, find and remove the relevant entry.",
            "",
            *MemoryType.all_sections(),
            "",
            "## What NOT to save to memory",
            "",
            "- Things derivable from the current project state (code patterns, file structure, git history)",
            "- Current conversation context (that's what the conversation is for)",
            "- Transient or session-specific information",
            "",
            *how_to_save,
            "",
            "## When to access memory",
            "",
            "- When the user starts a new conversation",
            "- When asked to recall something about the user or project",
            "- When planning significant work, check for relevant memories first",
            "",
            "## Memory vs other persistence",
            "- Use a plan instead of memory: when aligning on approach before starting work",
            "- Use tasks instead of memory: when breaking work into discrete steps within a conversation",
            "- Use memory: for information useful across future conversations",
        ]
        
        if self.extra_guidelines:
            lines.extend(["", *self.extra_guidelines])
        
        return lines
    
    # ─── Daily Log (KAIROS-style) ──────────────────────────────────────────
    
    def append_daily_log(self, entry: str) -> str:
        """
        Append an entry to today's daily log file.
        
        For long-lived sessions: append-only log, distilled nightly.
        Mirrors Claude Code's KAIROS assistant mode.
        """
        today = time.strftime("%Y-%m-%d")
        year = today[:4]
        month = today[5:7]
        
        log_dir = os.path.join(self.memory_dir, "logs", year, month)
        os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(log_dir, f"{today}.md")
        timestamp = time.strftime("%H:%M")
        
        entry_line = f"- [{timestamp}] {entry}\n"
        
        with open(log_file, "a") as f:
            f.write(entry_line)
        
        logger.info(f"Daily log appended: {log_file}")
        return log_file
    
    def get_recent_logs(self, days: int = 7) -> List[Dict[str, str]]:
        """Get recent daily log entries"""
        logs = []
        today_struct = time.localtime()
        
        for i in range(days):
            days_ago = i
            log_time = time.localtime(time.time() - days_ago * 86400)
            year = time.strftime("%Y", log_time)
            month = time.strftime("%m", log_time)
            day_str = time.strftime("%Y-%m-%d", log_time)
            
            log_file = os.path.join(
                self.memory_dir, "logs", year, month, f"{day_str}.md"
            )
            if os.path.exists(log_file):
                try:
                    with open(log_file, "r") as f:
                        content = f.read()
                    logs.append({
                        "date": day_str,
                        "path": log_file,
                        "content": content,
                    })
                except Exception:
                    pass
        
        return logs
    
    # ─── Stats ─────────────────────────────────────────────────────────────
    
    def stats(self) -> Dict[str, Any]:
        """Memory directory statistics"""
        entries = self.list_all()
        total_bytes = 0
        oldest = 999
        newest = 0
        
        for mem in entries:
            filepath = os.path.join(self.memory_dir, f"{mem.name}.md")
            if os.path.exists(filepath):
                total_bytes += os.path.getsize(filepath)
                age = self.get_memory_age_days(f"{mem.name}.md")
                oldest = min(oldest, age)
                newest = max(newest, age)
        
        by_type = {t.value: 0 for t in MemoryType}
        for mem in entries:
            by_type[mem.type.value] += 1
        
        return {
            "memory_dir": self.memory_dir,
            "total_memories": len(entries),
            "total_bytes": total_bytes,
            "oldest_age_days": oldest if oldest < 999 else None,
            "newest_age_days": newest,
            "by_type": by_type,
            "has_daily_logs": os.path.exists(os.path.join(self.memory_dir, "logs")),
        }
