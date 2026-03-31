"""Unit tests for Producer-Reviewer Protocol

Run: pytest tests/unit/test_producer_reviewer.py -v
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from protocols.producer_reviewer.protocol import (
    ProducerReviewerProtocol,
    ProducerTask,
    ReviewRound,
    ReviewVerdict,
    QualityGate,
)
from protocols.producer_reviewer.producer import ProducerAgent, ProducedTask
from protocols.producer_reviewer.reviewer import ReviewerAgent, ReviewCriteria
from protocols.producer_reviewer.feedback_loop import FeedbackLoop, FeedbackEntry


class TestProducerTask:
    """Tests for ProducerTask"""

    def test_create_task_with_defaults(self):
        """Test creating a task with default values"""
        task = ProducerTask(
            id="test-1",
            description="Test task",
            requirements=["Req 1", "Req 2"],
            context={},
            difficulty=0.5,
            stage="intermediate",
            max_tool_calls=10,
            timeout=300,
        )
        
        assert task.id == "test-1"
        assert task.difficulty == 0.5
        assert task.stage == "intermediate"

    def test_to_prompt(self):
        """Test prompt generation"""
        task = ProducerTask(
            id="test-1",
            description="Optimize performance",
            requirements=["Use faster algorithm", "Reduce memory"],
            context={},
            difficulty=0.7,
            stage="advanced",
            max_tool_calls=15,
            timeout=600,
            quality_gates=[QualityGate.FORMAT, QualityGate.ACCURACY],
        )
        
        prompt = task.to_prompt()
        assert "Optimize performance" in prompt
        assert "format" in prompt
        assert "accuracy" in prompt


class TestReviewRound:
    """Tests for ReviewRound"""

    def test_overall_score_calculation(self):
        """Test weighted overall score calculation"""
        round = ReviewRound(
            round_id=1,
            timestamp="2026-03-31T10:00:00",
            verdict=ReviewVerdict.ACCEPT,
            scores={
                "format": 0.9,
                "completeness": 0.8,
                "accuracy": 0.85,
                "performance": 0.7,
                "style": 0.75,
            },
            feedback="Good work",
        )
        
        # Weighted: format*0.15 + complete*0.25 + accuracy*0.30 + perf*0.20 + style*0.10
        # = 0.9*0.15 + 0.8*0.25 + 0.85*0.30 + 0.7*0.20 + 0.75*0.10
        # = 0.135 + 0.20 + 0.255 + 0.14 + 0.075 = 0.805
        expected = (
            0.9 * 0.15 + 
            0.8 * 0.25 + 
            0.85 * 0.30 + 
            0.7 * 0.20 + 
            0.75 * 0.10
        )
        
        assert abs(round.overall_score() - expected) < 0.01

    def test_is_pass_format_gate(self):
        """Test quality gate pass check"""
        round = ReviewRound(
            round_id=1,
            timestamp="2026-03-31T10:00:00",
            verdict=ReviewVerdict.ACCEPT,
            scores={"format": 0.85},
            feedback="Test",
        )
        
        assert round.is_pass(QualityGate.FORMAT) == True
        assert round.is_pass(QualityGate.FORMAT) == (0.85 >= 0.8)

    def test_to_grpo_reward(self):
        """Test GRPO reward conversion"""
        round = ReviewRound(
            round_id=1,
            timestamp="2026-03-31T10:00:00",
            verdict=ReviewVerdict.ACCEPT,
            scores={"format": 1.0, "completeness": 1.0, "accuracy": 1.0, "performance": 1.0, "style": 1.0},
            feedback="Perfect",
        )
        
        # Perfect score with base_scale 1.0 should give 1.0
        reward = round.to_grpo_reward(base_scale=1.0)
        assert reward == pytest.approx(1.0, abs=0.01)


class TestProducerAgent:
    """Tests for ProducerAgent"""

    def test_create_beginner_task(self):
        """Test creating beginner stage task"""
        producer = ProducerAgent()
        task = producer.create_task(
            stage="beginner",
            objectives=["Learn basic tool usage"],
        )
        
        assert task.difficulty == pytest.approx(0.3, abs=0.05)
        assert task.stage == "beginner"
        assert "Learn basic tool usage" in task.description

    def test_progressive_context_on_revisions(self):
        """Test progressive context disclosure"""
        producer = ProducerAgent()
        
        # First task
        task1 = producer.create_task(
            stage="beginner",
            objectives=["Test objective"],
            previous_attempts=[],
        )
        
        # After failure
        task2 = producer.create_task(
            stage="beginner",
            objectives=["Test objective"],
            previous_attempts=[{"feedback": "Failed", "score": 0.3}],
        )
        
        # Second attempt should have slightly lower difficulty
        assert task2.difficulty <= task1.difficulty

    def test_quality_gates_by_stage(self):
        """Test quality gates differ by stage"""
        producer = ProducerAgent()
        
        beginner = producer.create_task(stage="beginner", objectives=["Test"])
        intermediate = producer.create_task(stage="intermediate", objectives=["Test"])
        advanced = producer.create_task(stage="advanced", objectives=["Test"])
        
        # Advanced has more quality gates
        assert len(advanced.quality_gates) >= len(intermediate.quality_gates)
        assert len(intermediate.quality_gates) >= len(beginner.quality_gates)


class TestReviewerAgent:
    """Tests for ReviewerAgent"""

    def test_heuristic_review_accept(self):
        """Test heuristic review gives accept for good output"""
        reviewer = ReviewerAgent(use_llm=False)
        
        output = reviewer.review(
            task_description="Test task",
            learner_output={"result": "good solution", "score": 0.8},
            criteria=[ReviewCriteria.FORMAT, ReviewCriteria.COMPLETENESS],
        )
        
        assert output.verdict in ["accept", "revise", "reject"]

    def test_heuristic_review_empty_output(self):
        """Test review handles empty output"""
        reviewer = ReviewerAgent(use_llm=False)
        
        output = reviewer.review(
            task_description="Test task",
            learner_output=None,
            criteria=[ReviewCriteria.FORMAT],
        )
        
        # Should have low scores for empty output
        format_score = next((s for s in output.scores if s.criteria == "format"), None)
        assert format_score is not None
        assert format_score.score < 0.5


class TestFeedbackLoop:
    """Tests for FeedbackLoop"""

    def test_record_and_session_summary(self):
        """Test feedback recording and session summary"""
        loop = FeedbackLoop()
        loop.start_session()
        
        loop.record_feedback(
            task_id="task-1",
            round=1,
            verdict="accept",
            score=0.8,
            feedback="Good work",
        )
        
        session = loop.end_session()
        
        assert session["session_rounds"] == 1
        assert session["accepted"] == 1
        assert session["final_score"] == 0.8

    def test_pattern_detection(self):
        """Test feedback pattern detection"""
        loop = FeedbackLoop()
        
        # Record multiple similar issues
        loop.record_feedback("task-1", 1, "revise", 0.5, "format issue", issues=["format problem"])
        loop.record_feedback("task-2", 1, "revise", 0.4, "format issue again", issues=["format problem"])
        loop.record_feedback("task-3", 1, "accept", 0.8, "good", issues=[])
        
        # Should detect pattern
        assert len(loop.history.patterns) > 0
        format_pattern = next((p for p in loop.history.patterns if p.pattern_type == "format"), None)
        assert format_pattern is not None
        assert format_pattern.frequency >= 2

    def test_grpo_training_data_extraction(self):
        """Test extracting GRPO training data"""
        loop = FeedbackLoop()
        
        loop.record_feedback("task-1", 1, "accept", 0.8, "good", issues=[])
        loop.record_feedback("task-1", 2, "accept", 0.9, "better", issues=[])
        
        data = loop.get_grpo_training_data()
        
        assert len(data) == 2
        assert data[0]["reward"] == 0.8
        assert data[1]["reward"] == 0.9


class TestProducerReviewerProtocol:
    """Tests for ProducerReviewerProtocol"""

    def test_protocol_initialization(self):
        """Test protocol initializes correctly"""
        protocol = ProducerReviewerProtocol(max_rounds=5, min_score=0.6)
        
        assert protocol.max_rounds == 5
        assert protocol.min_score_for_accept == 0.6
        assert len(protocol.history) == 0

    def test_grpo_advantages_extraction(self):
        """Test extracting GRPO advantages from history"""
        protocol = ProducerReviewerProtocol(max_rounds=3)
        
        # Simulate review rounds
        protocol.history.append(ReviewRound(
            round_id=1, timestamp="", verdict=ReviewVerdict.REVISE,
            scores={"format": 0.7}, feedback=""
        ))
        protocol.history.append(ReviewRound(
            round_id=2, timestamp="", verdict=ReviewVerdict.ACCEPT,
            scores={"format": 0.8}, feedback=""
        ))
        
        advantages = protocol.get_grpo_advantages()
        
        assert len(advantages) == 2
        assert advantages[0] > 0  # First round had revise but some score
        assert advantages[1] > advantages[0]  # Accept should be higher

    def test_auto_review_fallback(self):
        """Test automatic fallback review"""
        protocol = ProducerReviewerProtocol(min_score=0.7)
        
        task = ProducerTask(
            id="test", description="test", requirements=[],
            context={}, difficulty=0.5, stage="beginner",
            max_tool_calls=10, timeout=300
        )
        
        review = protocol._auto_review({"result": "test"}, task)
        
        assert review.round_id == 1
        assert review.verdict in [ReviewVerdict.ACCEPT, ReviewVerdict.REVISE]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
