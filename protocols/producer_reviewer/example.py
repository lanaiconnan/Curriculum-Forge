"""Usage Example: Producer-Reviewer Protocol with Curriculum-Forge

This example demonstrates how to integrate the Producer-Reviewer protocol
with the existing Curriculum-Forge dual-agent system.

Key integration points:
1. ProducerAgent wraps Agent A (generator)
2. ReviewerAgent evaluates Agent B's outputs
3. FeedbackLoop feeds review scores into GRPO
4. Progressive disclosure adjusts context based on performance
"""

import sys
import os

# Add Curriculum-Forge to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from protocols.producer_reviewer import (
    ProducerReviewerProtocol,
    ProtocolConfig,
    ProducerAgent,
    ReviewerAgent,
    FeedbackLoop,
    ReviewCriteria,
    QualityGate,
)

from agent_a.generator import AgentA, AgentBProgress
from agent_b.learner import AgentB


def create_protocol(
    agent_a: AgentA,
    agent_b: AgentB,
    grpo_trainer=None,
    max_rounds: int = 3,
) -> ProducerReviewerProtocol:
    """
    Create and configure the Producer-Buyer protocol.
    
    Args:
        agent_a: Agent A (Generator) instance
        agent_b: Agent B (Learner) instance  
        grpo_trainer: Optional GRPO trainer for advantage calculation
        max_rounds: Maximum review rounds per task
        
    Returns:
        Configured ProducerReviewerProtocol instance
    """
    
    # Configure quality gates for RL training
    quality_gates = [
        QualityGate.SYNTAX,
        QualityGate.COMPLETENESS,
        QualityGate.CORRECTNESS,
    ]
    
    # Configure protocol
    config = ProtocolConfig(
        max_rounds=max_rounds,
        quality_gates=quality_gates,
        min_accept_score=0.7,
        enable_grpo_feedback=True,
        progressive_disclosure=True,
        initial_context_ratio=0.3,
        context_increment=0.25,
    )
    
    # Create producer wrapper (wraps Agent A)
    producer = ProducerAgent(agent_a)
    
    # Create reviewer with RL-specific criteria weights
    reviewer = ReviewerAgent(
        criteria_weights={
            ReviewCriteria.TOOL_SELECTION: 1.5,
            ReviewCriteria.PARAMETER_ACCURACY: 1.2,
            ReviewCriteria.REWARD_QUALITY: 2.0,      # Most important
            ReviewCriteria.LEARNING_PROGRESS: 1.8,   # Second most important
            ReviewCriteria.EFFICIENCY: 0.8,
            ReviewCriteria.EXPLORATION: 1.0,
        },
        min_accept_score=0.7,
        strict_mode=False,
    )
    
    # Create feedback loop for GRPO integration
    feedback_loop = FeedbackLoop(
        grpo_trainer=grpo_trainer,
        group_size=4,
        reward_scale=1.0,
    )
    
    # Create protocol
    protocol = ProducerReviewerProtocol(
        producer_agent=producer,
        reviewer_agent=reviewer,
        config=config,
        grpo_trainer=grpo_trainer,
    )
    
    # Register callbacks for feedback integration
    def on_review_complete(task, feedback):
        """Record feedback when review completes"""
        feedback_loop.record_feedback(
            task_id=task.id,
            round=task.round,
            verdict=feedback.verdict.value,
            overall_score=feedback.overall_score,
            criteria_scores=feedback.scores,
        )
    
    protocol.on_review_complete = on_review_complete
    
    return protocol, feedback_loop


def run_training_session(
    agent_a: AgentA,
    agent_b: AgentB,
    grpo_trainer,
    num_tasks: int = 5,
) -> dict:
    """
    Run a training session with Producer-Buyer protocol.
    
    This replaces the simple generate->learn loop with a 
    structured review cycle that feeds back into GRPO.
    """
    
    # Create protocol
    protocol, feedback_loop = create_protocol(
        agent_a, agent_b, grpo_trainer, max_rounds=3
    )
    
    results = []
    
    for i in range(num_tasks):
        # Get Agent B's current progress
        progress = AgentBProgress(
            total_experiments=agent_b.total_time,  # Approximate
            keep_rate=0.3 + (i * 0.1),  # Simulated progress
            best_score=100 + (i * 5),
        )
        
        # Task description
        task_desc = f"Training task {i+1}: Optimize for score > {progress.best_score + 10}"
        
        # Context for producer
        context = {
            'progress': progress,
            'baseline': progress.best_score,
            'max_time': agent_b.max_experiment_time,
        }
        
        # Execute protocol
        final_round = protocol.execute(task_desc, context)
        
        # Record result
        task_result = {
            'task_id': i + 1,
            'accepted': final_round.is_accepted(),
            'rounds': final_round.round_number,
            'final_score': final_round.feedback.overall_score if final_round.feedback else 0,
        }
        results.append(task_result)
        
        print(f"Task {i+1}: {'✓ Accepted' if task_result['accepted'] else '✗ Not accepted'} "
              f"({final_round.round_number} rounds, score={task_result['final_score']:.1%})")
    
    # Analyze feedback patterns
    analysis = feedback_loop.analyze_feedback_patterns()
    suggestions = feedback_loop.suggest_training_adjustments()
    
    return {
        'task_results': results,
        'feedback_analysis': analysis,
        'suggestions': suggestions,
        'protocol_stats': protocol.get_stats(),
    }


def main():
    """Example usage"""
    print("=" * 60)
    print("Producer-Reviewer Protocol Example")
    print("=" * 60)
    
    # Initialize agents (simplified - would normally load from config)
    workspace = "./workspace"
    
    try:
        agent_a = AgentA(workspace=workspace)
    except Exception as e:
        print(f"Note: AgentA init issue (non-critical): {e}")
        agent_a = None
    
    try:
        agent_b = AgentB(workspace=workspace, max_experiment_time=300)
    except Exception as e:
        print(f"Note: AgentB init issue (non-critical): {e}")
        agent_b = None
    
    # Create protocol with mock agents for demonstration
    class MockAgentA:
        def generate_environment(self, progress):
            class Env:
                id = "demo-env-1"
                name = "Demo Environment"
                description = "Difficulty: 0.5"
                tasks = [{"id": "t1", "type": "test"}]
                reward_config = {"baseline": 100}
            return Env()
    
    class MockAgentB:
        def run(self, env):
            class Result:
                status = "keep"
                reward = 0.75
                metrics = {"score": 105}
            return [Result()]
    
    mock_producer = MockAgentA()
    mock_reviewer = ReviewerAgent()
    
    # Configure protocol
    config = ProtocolConfig(
        max_rounds=2,
        quality_gates=[QualityGate.SYNTAX, QualityGate.COMPLETENESS],
        min_accept_score=0.6,
    )
    
    protocol = ProducerReviewerProtocol(
        producer_agent=mock_producer,
        reviewer_agent=mock_reviewer,
        config=config,
    )
    
    # Execute a demo task
    print("\nExecuting demo task...")
    final_round = protocol.execute(
        "Generate a training environment for code optimization",
        context={"baseline": 100, "max_time": 300}
    )
    
    print(f"\nResults:")
    print(f"  Status: {final_round.feedback.verdict.value if final_round.feedback else 'no feedback'}")
    print(f"  Rounds: {final_round.round_number}")
    if final_round.feedback:
        print(f"  Score: {final_round.feedback.overall_score:.1%}")
        print(f"  Issues: {len(final_round.feedback.issues)}")
        print(f"  Suggestions: {len(final_round.feedback.suggestions)}")
    
    print(f"\nProtocol Stats: {protocol.get_stats()}")
    
    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
