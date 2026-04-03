"""Unit tests for services/memdir.py — Persistent Memory Directory

Run: pytest tests/unit/test_memdir.py -v
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.memdir import (
    MemoryDir,
    MemoryEntry,
    MemoryType,
    IndexEntry,
    ENTRYPOINT_NAME,
)


# ─── MemoryEntry ───────────────────────────────────────────────────────────────

class TestMemoryEntry:
    def test_to_frontmatter(self):
        entry = MemoryEntry(
            name="test_memory",
            description="A test memory",
            type=MemoryType.USER,
            content="This is the content of the memory.",
            created_at="2026-04-01",
            updated_at="2026-04-03",
            tags=["test", "demo"],
        )
        fm = entry.to_frontmatter()
        assert "---" in fm
        assert "name: test_memory" in fm
        assert "type: user" in fm
        assert "This is the content" in fm

    def test_roundtrip(self):
        entry = MemoryEntry(
            name="roundtrip",
            description="Testing roundtrip",
            type=MemoryType.FEEDBACK,
            content="Some feedback content here.",
            tags=["test"],
        )
        fm = entry.to_frontmatter()
        parsed = MemoryEntry.from_frontmatter(fm)
        assert parsed is not None
        assert parsed.name == entry.name
        assert parsed.type == entry.type
        assert entry.content.strip() in parsed.content

    def test_from_frontmatter_invalid(self):
        result = MemoryEntry.from_frontmatter("No frontmatter here")
        assert result is None

    def test_tags_parsing(self):
        entry = MemoryEntry(
            name="t",
            description="d",
            type=MemoryType.PROJECT,
            content="c",
            tags=["tag1", "tag2"],
        )
        fm = entry.to_frontmatter()
        parsed = MemoryEntry.from_frontmatter(fm)
        assert parsed is not None
        assert "tag1" in parsed.tags
        assert "tag2" in parsed.tags


# ─── IndexEntry ────────────────────────────────────────────────────────────────

class TestIndexEntry:
    def test_parse(self):
        line = "- [User Preferences](user_prefs.md) — prefers short responses"
        entry = IndexEntry.parse(line)
        assert entry is not None
        assert entry.title == "User Preferences"
        assert entry.file == "user_prefs.md"
        assert entry.hook == "prefers short responses"

    def test_parse_no_hook(self):
        line = "- [Title](file.md)"
        entry = IndexEntry.parse(line)
        assert entry is not None
        assert entry.hook == ""

    def test_parse_invalid(self):
        assert IndexEntry.parse("not a valid line") is None
        assert IndexEntry.parse("- no brackets here") is None


# ─── MemoryDir ────────────────────────────────────────────────────────────────

class TestMemoryDir:
    def test_ensure_exists(self, tmp_path):
        mdir = MemoryDir(str(tmp_path / "mem"))
        assert os.path.isdir(mdir.memory_dir)
        assert mdir.exists()

    def test_save_and_get(self, tmp_path):
        mdir = MemoryDir(str(tmp_path / "mem"))
        
        entry = MemoryEntry(
            name="test_pref",
            description="User prefers concise answers",
            type=MemoryType.USER,
            content="The user wants brief, to-the-point responses.",
            tags=["preferences"],
        )
        mdir.save("user_prefs.md", entry)
        
        retrieved = mdir.get("user_prefs.md")
        assert retrieved is not None
        assert retrieved.name == "test_pref"
        assert retrieved.type == MemoryType.USER
        assert "brief" in retrieved.content

    def test_update_memory(self, tmp_path):
        mdir = MemoryDir(str(tmp_path / "mem"))
        
        entry1 = MemoryEntry(
            name="proj",
            description="Initial",
            type=MemoryType.PROJECT,
            content="Version 1",
        )
        mdir.save("project.md", entry1)
        
        entry2 = MemoryEntry(
            name="proj",
            description="Updated",
            type=MemoryType.PROJECT,
            content="Version 2 with improvements",
        )
        mdir.save("project.md", entry2)
        
        retrieved = mdir.get("project.md")
        assert retrieved is not None
        assert "Version 2" in retrieved.content
        assert retrieved.created_at == entry1.created_at  # Preserved

    def test_list_all(self, tmp_path):
        mdir = MemoryDir(str(tmp_path / "mem"))
        
        mdir.save("a.md", MemoryEntry("a", "desc", MemoryType.USER, "content a"))
        mdir.save("b.md", MemoryEntry("b", "desc", MemoryType.FEEDBACK, "content b"))
        mdir.save("c.md", MemoryEntry("c", "desc", MemoryType.PROJECT, "content c"))
        
        all_mem = mdir.list_all()
        assert len(all_mem) == 3
        names = {m.name for m in all_mem}
        assert names == {"a", "b", "c"}

    def test_delete(self, tmp_path):
        mdir = MemoryDir(str(tmp_path / "mem"))
        
        mdir.save("todel.md", MemoryEntry("t", "d", MemoryType.USER, "c"))
        assert mdir.get("todel.md") is not None
        
        mdir.delete("todel.md")
        assert mdir.get("todel.md") is None

    def test_index_truncation(self, tmp_path):
        """MEMORY.md index should truncate at MAX_ENTRYPOINT_LINES"""
        from services.memdir import MAX_ENTRYPOINT_LINES
        mdir = MemoryDir(str(tmp_path / "mem"))
        
        # Save many memories (more than MAX_ENTRYPOINT_LINES / 3)
        for i in range(100):
            entry = MemoryEntry(
                name=f"mem_{i}",
                description=f"Memory number {i} with some description text",
                type=MemoryType.PROJECT,
                content=f"Content {i}",
            )
            mdir.save(f"mem_{i}.md", entry)
        
        # Read MEMORY.md
        with open(mdir.entrypoint_path) as f:
            content = f.read()
        
        # Should contain truncation warning
        assert "WARNING" in content or len(content.split("\n")) <= MAX_ENTRYPOINT_LINES + 5

    def test_search_basic(self, tmp_path):
        mdir = MemoryDir(str(tmp_path / "mem"))
        
        mdir.save("reward_calc.md", MemoryEntry(
            "reward_calc",
            "GRPO reward calculation",
            MemoryType.FEEDBACK,
            "Use fine-grained reward: rname=1.0, rparam=0.5, rvalue=0.5",
        ))
        mdir.save("user_prefs.md", MemoryEntry(
            "prefs", "User preferences", MemoryType.USER,
            "User prefers verbose explanations",
        ))
        
        results = mdir.search("reward", use_subprocess=False)
        assert len(results) > 0
        assert any("reward" in r["file"] for r in results)

    def test_search_no_results(self, tmp_path):
        mdir = MemoryDir(str(tmp_path / "mem"))
        mdir.save("a.md", MemoryEntry("a", "d", MemoryType.USER, "content"))
        
        results = mdir.search("xyznonexistent", use_subprocess=False)
        assert len(results) == 0

    def test_retrieve_context(self, tmp_path):
        mdir = MemoryDir(str(tmp_path / "mem"))
        
        mdir.save("grpo_reward.md", MemoryEntry(
            "grpo_reward",
            "GRPO reward calculation",
            MemoryType.FEEDBACK,
            "Use GRPO with group-normalized advantages. Reward: format=1.0, param=0.5, value=0.5.",
        ))
        mdir.save("prefs.md", MemoryEntry(
            "prefs", "User preferences", MemoryType.USER,
            "User prefers concise answers.",
        ))
        
        context = mdir.retrieve_context("GRPO reward", budget_tokens=500, max_results=5)
        assert len(context) > 0
        assert "GRPO" in context or "reward" in context.lower()

    def test_retrieve_context_empty(self, tmp_path):
        mdir = MemoryDir(str(tmp_path / "mem"))
        context = mdir.retrieve_context("anything", budget_tokens=500)
        assert context == ""

    def test_memory_age(self, tmp_path):
        mdir = MemoryDir(str(tmp_path / "mem"))
        mdir.save("new.md", MemoryEntry("new", "d", MemoryType.USER, "c"))
        
        # Very new memory should have high score
        score = mdir.get_memory_age_score("new.md")
        assert score >= 0.9

    def test_build_memory_prompt(self, tmp_path):
        mdir = MemoryDir(str(tmp_path / "mem"))
        mdir.save("test.md", MemoryEntry(
            "test", "test memory", MemoryType.USER, "Test content here."
        ))
        
        prompt = mdir.build_memory_prompt(include_content=True)
        assert "auto memory" in prompt.lower()
        assert "MEMORY.md" in prompt
        assert "frontmatter" in prompt
        assert "test memory" in prompt

    def test_build_memory_prompt_empty(self, tmp_path):
        mdir = MemoryDir(str(tmp_path / "mem"))
        prompt = mdir.build_memory_prompt(include_content=True)
        assert "empty" in prompt.lower()
        assert "test content" not in prompt

    def test_build_memory_prompt_no_content(self, tmp_path):
        mdir = MemoryDir(str(tmp_path / "mem"))
        prompt = mdir.build_memory_prompt(include_content=False)
        assert "auto memory" in prompt.lower()
        assert "test content" not in prompt

    def test_daily_log(self, tmp_path):
        mdir = MemoryDir(str(tmp_path / "mem"))
        
        log_path = mdir.append_daily_log("User corrected reward calculation approach")
        assert os.path.exists(log_path)
        
        with open(log_path) as f:
            content = f.read()
        assert "reward" in content.lower()

    def test_daily_log_multiple(self, tmp_path):
        mdir = MemoryDir(str(tmp_path / "mem"))
        
        mdir.append_daily_log("First entry")
        mdir.append_daily_log("Second entry")
        
        logs = mdir.get_recent_logs(days=1)
        assert len(logs) >= 1
        # Most recent log should have both entries
        recent = max(logs, key=lambda l: l["date"])
        assert "First entry" in recent["content"]
        assert "Second entry" in recent["content"]

    def test_stats(self, tmp_path):
        mdir = MemoryDir(str(tmp_path / "mem"))
        mdir.save("a.md", MemoryEntry("a", "d", MemoryType.USER, "c"))
        mdir.save("b.md", MemoryEntry("b", "d", MemoryType.FEEDBACK, "c"))
        
        stats = mdir.stats()
        assert stats["total_memories"] == 2
        assert stats["by_type"]["user"] == 1
        assert stats["by_type"]["feedback"] == 1

    def test_extra_guidelines(self, tmp_path):
        mdir = MemoryDir(
            str(tmp_path / "mem"),
            extra_guidelines=["- Custom rule: always use verbose mode"],
        )
        prompt = mdir.build_memory_prompt(include_content=False)
        assert "Custom rule" in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
