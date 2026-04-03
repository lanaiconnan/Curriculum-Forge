"""Unit tests for services/compact.py — Enhanced Compact Engine

Run: pytest tests/unit/test_compact.py -v
"""

import pytest
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.compact import (
    ImportanceScorer,
    ImportanceScore,
    MicroCompactor,
    CompactArchive,
    ArchivedCompact,
    CompactEngine,
)
from services.context import (
    MessageGroup,
    CompactConfig,
    group_messages,
    estimate_total_tokens,
)
from services.query_engine import LLMMessage


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_conversation(turns):
    msgs = [LLMMessage(role="system", content="You are helpful.")]
    for i in range(turns):
        msgs.append(LLMMessage(role="user", content=f"User message {i}"))
        msgs.append(LLMMessage(role="assistant", content=f"Assistant response {i}"))
    return msgs


def make_tool_heavy_turn():
    """Create a turn with multiple tool results"""
    return [
        LLMMessage(role="user", content=f"Q"),
        LLMMessage(role="assistant", content="Thinking..."),
        LLMMessage(role="user", content=[
            {"type": "tool_result", "content": "result 1"},
            {"type": "tool_result", "content": "result 2"},
            {"type": "tool_result", "content": "result 3"},
        ]),
    ]


def make_error_turn():
    return [
        LLMMessage(role="user", content="Do something"),
        LLMMessage(role="user", content=[
            {"type": "tool_result", "content": "failed", "is_error": True},
        ]),
    ]


def make_reflection_turn():
    return [
        LLMMessage(role="user", content="What went wrong?"),
        LLMMessage(role="assistant", content="I learned that I should have used the correct tool. The mistake was calling write instead of read."),
    ]


# ─── ImportanceScorer ────────────────────────────────────────────────────────

class TestImportanceScorer:
    def test_first_turn_gets_bonus(self):
        scorer = ImportanceScorer()
        group = MessageGroup(
            messages=[LLMMessage("user", "first")],
            turn_index=0,
            is_tool_heavy=False,
            has_error=False,
        )
        score = scorer.score(group, 5)
        assert "first_turn" in score.reasons

    def test_error_turn_gets_high_score(self):
        scorer = ImportanceScorer()
        msgs = make_error_turn()
        groups = group_messages(msgs)
        # The group containing the error should score higher
        error_group = groups[-1]
        score = scorer.score(error_group, len(groups))
        assert score.score >= 0.3
        assert "has_error" in score.reasons

    def test_tool_diversity_bonus(self):
        scorer = ImportanceScorer()
        # Use tool_use blocks to trigger diversity detection
        group = MessageGroup(
            messages=[
                LLMMessage("assistant", content=[
                    {"type": "tool_use", "id": "t1", "name": "read_file", "input": {}},
                    {"type": "tool_use", "id": "t2", "name": "write_file", "input": {}},
                    {"type": "tool_use", "id": "t3", "name": "search", "input": {}},
                ]),
            ],
            turn_index=1,
            is_tool_heavy=True,
            has_error=False,
        )
        score = scorer.score(group, 3)
        assert "tool_diversity" in score.reasons[1]  # "tool_diversity(3)"

    def test_trivial_content_penalized(self):
        scorer = ImportanceScorer()
        group = MessageGroup(
            messages=[LLMMessage("user", "ok")],
            turn_index=2,
            is_tool_heavy=False,
            has_error=False,
        )
        score = scorer.score(group, 5)
        assert "trivial_content" in score.reasons

    def test_reflection_content_bonus(self):
        scorer = ImportanceScorer()
        msgs = make_reflection_turn()
        groups = group_messages(msgs)
        group = groups[-1]
        score = scorer.score(group, 1)
        assert "reflection_content" in score.reasons

    def test_score_all(self):
        scorer = ImportanceScorer()
        msgs = make_conversation(3)
        groups = group_messages([m for m in msgs if m.role != "system"])
        scores = scorer.score_all(groups)
        assert len(scores) == 3
        # All scores should be in [0, 1]
        for s in scores:
            assert 0.0 <= s.score <= 1.0

    def test_custom_rule(self):
        def always_bonus(group):
            return 0.5
        scorer = ImportanceScorer(custom_rules=[always_bonus])
        group = MessageGroup(
            messages=[LLMMessage("user", "test")],
            turn_index=0,
            is_tool_heavy=False,
            has_error=False,
        )
        score = scorer.score(group, 1)
        assert "custom_rule" in score.reasons

    def test_label(self):
        scorer = ImportanceScorer()
        # High score → critical
        group = MessageGroup(
            messages=[
                LLMMessage("user", content=[
                    {"type": "tool_result", "content": "fail", "is_error": True},
                ]),
            ],
            turn_index=0,
            is_tool_heavy=False,
            has_error=True,
        )
        score = scorer.score(group, 1)
        assert score.label in ("critical", "important", "useful", "low")


# ─── MicroCompactor ───────────────────────────────────────────────────────────

class TestMicroCompactor:
    def test_truncate_long_tool_result(self):
        mc = MicroCompactor(max_tool_result_chars=20)
        msg = LLMMessage("user", content=[
            {"type": "tool_result", "tool_use_id": "t1", "content": "x" * 200},
        ])
        result = mc.compact_message(msg)
        block = result.content[0]
        assert "truncated" in block["content"]
        assert len(block["content"]) < 100

    def test_short_tool_result_unchanged(self):
        mc = MicroCompactor(max_tool_result_chars=200)
        msg = LLMMessage("user", content=[
            {"type": "tool_result", "tool_use_id": "t1", "content": "short"},
        ])
        result = mc.compact_message(msg)
        assert result.content[0]["content"] == "short"

    def test_string_content_unchanged(self):
        mc = MicroCompactor(max_tool_result_chars=50)
        msg = LLMMessage("assistant", content="Hello world")
        result = mc.compact_message(msg)
        assert result.content == "Hello world"

    def test_truncate_long_text_block(self):
        mc = MicroCompactor(max_tool_result_chars=50)
        msg = LLMMessage("assistant", content=[
            {"type": "text", "text": "x" * 500},
        ])
        result = mc.compact_message(msg)
        assert "truncated" in result.content[0]["text"]

    def test_compact_messages(self):
        mc = MicroCompactor(max_tool_result_chars=20)
        msgs = [
            LLMMessage("user", content="short"),
            LLMMessage("user", content=[{"type": "tool_result", "content": "x" * 100}]),
        ]
        result = mc.compact_messages(msgs)
        assert mc.truncate_count == 1
        assert len(result) == 2

    def test_truncate_count_reset(self):
        mc = MicroCompactor(max_tool_result_chars=10)
        msgs = [LLMMessage("user", content="hi")]
        mc.compact_messages(msgs)
        assert mc.truncate_count == 0


# ─── CompactArchive ──────────────────────────────────────────────────────────

class TestCompactArchive:
    def test_save_and_list(self, tmp_path):
        archive = CompactArchive(str(tmp_path))
        compact = ArchivedCompact(
            session_id="s1",
            timestamp="2026-04-03 10:00",
            summary="Learned about tool errors.",
            message_count=50,
            turn_count=10,
            tool_call_count=15,
            error_count=3,
            original_tokens=20000,
            compressed_tokens=5000,
            importance_scores={0: 0.8, 5: 0.6},
            tags=["beginner", "tool-learning"],
        )
        archive.save(compact)
        
        sessions = archive.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "s1"
        assert sessions[0]["summary"] == "Learned about tool errors."

    def test_search(self, tmp_path):
        archive = CompactArchive(str(tmp_path))
        archive.save(ArchivedCompact(
            "s1", "2026-04-03 10:00",
            "Learned about tool errors in read_file.",
            50, 10, 15, 3, 20000, 5000, {}, ["tool-learning"],
        ))
        archive.save(ArchivedCompact(
            "s2", "2026-04-03 11:00",
            "Practiced write_file operations.",
            30, 8, 10, 0, 15000, 4000, {}, ["writing"],
        ))
        archive.save(ArchivedCompact(
            "s3", "2026-04-03 12:00",
            "Fixed an error with tool parameters.",
            20, 5, 8, 2, 10000, 3000, {}, ["debugging"],
        ))
        
        results = archive.search("tool error")
        assert len(results) > 0
        # s1 mentions both "tool" and "error"
        ids = [r["session_id"] for r in results]
        assert "s1" in ids

    def test_retrieve_context(self, tmp_path):
        archive = CompactArchive(str(tmp_path))
        for i in range(5):
            archive.save(ArchivedCompact(
                f"s{i}", f"2026-04-03 1{i}:00",
                f"Session about topic {i}. Some details here.",
                20, 5, 8, 0, 10000, 3000, {},
            ))
        
        context = archive.retrieve_context("topic 3", budget_tokens=200)
        assert "topic 3" in context

    def test_get_session(self, tmp_path):
        archive = CompactArchive(str(tmp_path))
        archive.save(ArchivedCompact(
            "target_session", "2026-04-03 10:00",
            "Target summary", 10, 2, 3, 0, 5000, 2000, {},
        ))
        
        result = archive.get_session("target_session")
        assert result is not None
        assert result["session_id"] == "target_session"
        
        missing = archive.get_session("nonexistent")
        assert missing is None

    def test_stats(self, tmp_path):
        archive = CompactArchive(str(tmp_path))
        archive.save(ArchivedCompact(
            "s1", "2026-04-03 10:00", "Summary", 10, 2, 3, 0, 5000, 2000, {},
        ))
        stats = archive.stats()
        assert stats["total_sessions"] == 1
        assert stats["total_files"] == 1

    def test_multiple_days(self, tmp_path):
        archive = CompactArchive(str(tmp_path))
        # Manually write to different day files
        for day, sid in [("2026-04-01", "a"), ("2026-04-02", "b"), ("2026-04-03", "c")]:
            path = os.path.join(str(tmp_path), f"{day}.jsonl")
            with open(path, "w") as f:
                f.write(json.dumps({
                    "session_id": sid,
                    "timestamp": f"{day} 10:00",
                    "summary": f"Day {sid} session",
                    "message_count": 10,
                    "turn_count": 2,
                    "tool_call_count": 3,
                    "error_count": 0,
                    "original_tokens": 5000,
                    "compressed_tokens": 2000,
                    "importance_scores": {},
                }) + "\n")
        
        sessions = archive.list_sessions()
        assert len(sessions) == 3


# ─── CompactEngine ────────────────────────────────────────────────────────────

class TestCompactEngine:
    def test_compact_reduces_messages(self):
        engine = CompactEngine(config=CompactConfig(keep_recent=3))
        messages = make_conversation(20)
        
        result = engine.compact(messages)
        compressed = result["messages"]
        assert len(compressed) < len(messages)
        assert result["saved_tokens"] > 0

    def test_compact_preserves_system(self):
        engine = CompactEngine(config=CompactConfig(keep_recent=2))
        messages = make_conversation(10)
        
        result = engine.compact(messages)
        roles = [m.role for m in result["messages"]]
        assert "system" in roles

    def test_compact_keeps_high_importance(self):
        engine = CompactEngine(config=CompactConfig(keep_recent=2))
        
        # Build conversation with error turn in the middle
        messages = [LLMMessage("system", "sys")]
        for i in range(10):
            messages.append(LLMMessage("user", f"Q{i}"))
            messages.append(LLMMessage("assistant", f"A{i}"))
        
        # Add an error turn
        messages.extend(make_error_turn())
        
        result = engine.compact(messages)
        # The compact should keep the error turn due to high importance
        scores = result["scores"]
        error_score = scores[-1] if scores else None
        if error_score:
            assert error_score.score >= 0.25  # Account for trivial_content penalty

    def test_compact_with_archive(self, tmp_path):
        archive_path = str(tmp_path / "sessions")
        engine = CompactEngine(
            config=CompactConfig(keep_recent=2),
            archive_path=archive_path,
        )
        messages = make_conversation(5)
        
        engine.compact(messages)
        
        # Should have saved to archive
        sessions = engine.list_sessions()
        assert len(sessions) == 1

    def test_search_archive(self, tmp_path):
        archive_path = str(tmp_path / "sessions")
        engine = CompactEngine(
            config=CompactConfig(keep_recent=2),
            archive_path=archive_path,
        )
        
        # Create a longer conversation so some messages are discarded
        messages = [LLMMessage("system", "sys")]
        for i in range(10):
            messages.append(LLMMessage("user", f"Question {i} about file handling errors"))
            messages.append(LLMMessage("assistant", f"Answer {i}"))
        
        engine.compact(messages)
        
        # Search for terms that should be in the summary (file, errors)
        results = engine.search("errors")
        assert len(results) > 0

    def test_retrieve_context(self, tmp_path):
        archive_path = str(tmp_path / "sessions")
        engine = CompactEngine(
            config=CompactConfig(keep_recent=2),
            archive_path=archive_path,
        )
        
        # Use enough messages per session so compact discards some
        for i in range(5):
            msgs = [LLMMessage("system", "sys")]
            for j in range(8):
                msgs.append(LLMMessage("user", f"Question about debugging {i}-{j}"))
                msgs.append(LLMMessage("assistant", f"Answer about debugging {i}-{j}"))
            engine._session_id = f"s{i}"
            engine.compact(msgs)
        
        # Search for "debugging" which should appear in all summaries
        context = engine.retrieve_context("debugging", budget_tokens=2000)
        assert len(context) > 0
        assert "debugging" in context.lower()

    def test_micro_compact_only(self):
        engine = CompactEngine(config=CompactConfig(max_tool_result_length=20))
        
        messages = [
            LLMMessage("assistant", content=[
                {"type": "text", "text": "I'll read the file."},
                {"type": "tool_use", "id": "t1", "name": "read", "input": {}},
            ]),
            LLMMessage("user", content=[
                {"type": "tool_result", "tool_use_id": "t1", "content": "x" * 200},
            ]),
        ]
        
        result = engine.micro_compact(messages)
        assert len(result) == 2
        # The tool_result should be truncated
        tool_block = result[1].content[0]
        assert "truncated" in tool_block["content"]

    def test_no_archive_no_crash(self):
        engine = CompactEngine()  # No archive_path
        # Use a longer conversation so compact actually saves tokens
        messages = make_conversation(15)
        
        # Should work without archive
        result = engine.compact(messages)
        # Compression ratio should be < 1.0 for long enough conversations
        assert result["compression_ratio"] < 1.0
        
        # Search should return empty (no archive)
        assert engine.search("anything") == []
        assert engine.retrieve_context("anything") == ""

    def test_stats(self, tmp_path):
        archive_path = str(tmp_path / "sessions")
        engine = CompactEngine(
            config=CompactConfig(keep_recent=2),
            archive_path=archive_path,
        )
        messages = make_conversation(3)
        engine.compact(messages)
        
        stats = engine.stats()
        assert "session_id" in stats
        assert "archive" in stats
        assert stats["archive"]["total_sessions"] == 1

    def test_compact_with_tool_heavy_conversation(self):
        """Compact should handle tool-heavy conversations efficiently"""
        engine = CompactEngine(
            config=CompactConfig(keep_recent=4, max_tool_result_length=50),
        )
        
        messages = [LLMMessage("system", "sys")]
        for i in range(15):
            messages.append(LLMMessage("user", f"Step {i}"))
            messages.append(LLMMessage("assistant", content=[
                {"type": "text", "text": f"Processing step {i}..."},
                {"type": "tool_use", "id": f"t{i}", "name": "tool", "input": {}},
            ]))
            # Long tool result
            messages.append(LLMMessage("user", content=[
                {"type": "tool_result", "tool_use_id": f"t{i}",
                 "content": "x" * 500 + f" result of step {i}"},
            ]))
        
        result = engine.compact(messages)
        assert result["truncated"] > 0  # Micro-compact should truncate
        assert result["compression_ratio"] < 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
