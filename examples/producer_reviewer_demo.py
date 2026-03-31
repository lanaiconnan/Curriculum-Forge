"""Example: Producer-Reviewer Protocol in Curriculum-Forge

Demonstrates how to use the Producer-Reviewer integration
with the existing Agent A/B/GRPO system.

Run:
    python examples/producer_reviewer_demo.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_a.generator import AgentA
from agent_b.learner import AgentB
from rl.trainer import RLTrainer, RLConfig
from shared.experience_buffer import ExperienceBuffer
from protocols.integration import ProducerReviewerIntegration


def run_demo():
    print("=" * 60)
    print("Curriculum-Forge: Producer-Reviewer Protocol Demo")
    print("=" * 60)

    # --- Setup existing components ---
    agent_a = AgentA(workspace=".", enable_analyst=True)
    agent_b = AgentB(workspace=".", max_experiment_time=60)
    trainer = RLTrainer(config=RLConfig(learning_rate=3e-4, gamma=0.99))
    buffer = ExperienceBuffer(capacity=1000, use_priority=True)

    # --- Create integration ---
    integration = ProducerReviewerIntegration(
        agent_a=agent_a,
        agent_b=agent_b,
        trainer=trainer,
        experience_buffer=buffer,
        max_review_rounds=3,
        use_llm_reviewer=False,  # Use heuristic reviewer (no LLM key needed)
    )

    # --- Run episodes across stages ---
    episodes = [
        {
            "stage": "beginner",
            "objectives": ["Improve code performance", "Reduce memory usage"],
        },
        {
            "stage": "intermediate",
            "objectives": ["Refactor with tests", "Optimize hot path"],
        },
        {
            "stage": "advanced",
            "objectives": ["Multi-objective optimization", "Handle edge cases"],
        },
    ]

    for i, ep_config in enumerate(episodes, 1):
        print(f"\n[Episode {i}] Stage: {ep_config['stage']}")
        print(f"  Objectives: {ep_config['objectives']}")

        result = integration.run_episode(
            stage=ep_config["stage"],
            objectives=ep_config["objectives"],
        )

        print(f"  Verdict:    {result.verdict}")
        print(f"  Rounds:     {result.rounds}")
        print(f"  Reward:     {result.final_reward:.3f}")
        print(f"  GRPO Rewards per round: {[f'{r:.3f}' for r in result.grpo_rewards]}")

    # --- Print summary ---
    integration.print_summary()

    # --- Show experience buffer stats ---
    buf_stats = buffer.get_stats()
    print(f"\nExperience Buffer: {buf_stats['buffer_size']} entries "
          f"({buf_stats['fill_ratio']:.1%} full)")


if __name__ == "__main__":
    run_demo()
