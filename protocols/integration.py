"""Integration: Producer-Reviewer Protocol with Curriculum-Forge

Bridges the new Producer-Reviewer protocol with existing:
- AgentA (Generator + Analyst)
- AgentB (Learner)
- RLTrainer (GRPO)
- ExperienceBuffer

Usage:
    from protocols.integration import ProducerReviewerIntegration

    integration = ProducerReviewerIntegration(
        agent_a=agent_a,
        agent_b=agent_b,
        trainer=trainer,
        buffer=experience_buffer,
    )

    result = integration.run_episode(
        stage="intermediate",
        objectives=["Optimize performance", "Reduce memory usage"],
    )
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from protocols.producer_reviewer.protocol import (
    ProducerReviewerProtocol,
    ProducerTask,
    ReviewRound,
    ReviewVerdict,
    QualityGate,
)
from protocols.producer_reviewer.producer import ProducerAgent
from protocols.producer_reviewer.reviewer import ReviewerAgent, ReviewCriteria
from protocols.producer_reviewer.feedback_loop import FeedbackLoop


@dataclass
class EpisodeResult:
    """Result of a full Producer-Reviewer episode"""
    verdict: str
    rounds: int
    final_reward: float
    grpo_rewards: List[float]
    feedback_summary: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_rl_experience(self) -> Dict[str, Any]:
        """Convert to format for RLTrainer.train_step()"""
        return {
            "id": self.metadata.get("task_id", "unknown"),
            "status": "keep" if self.verdict == "accept" else "discard",
            "reward": self.final_reward,
            "predicted_tools": self.metadata.get("tools_used", []),
            "ground_truth_tools": self.metadata.get("expected_tools", []),
            "description": self.metadata.get("description", ""),
        }


class ProducerReviewerIntegration:
    """
    Integration layer connecting Producer-Reviewer protocol
    with Curriculum-Forge's existing Agent A/B/GRPO system.

    Architecture:
    
        AgentA.generate_environment()
              |
              v
        ProducerAgent.create_task()
              |
              v
        [Producer-Reviewer Loop]
              |
        AgentB.run_experiment()  <-- Learner
              |
        ReviewerAgent.review()   <-- Agent A as Reviewer
              |
        FeedbackLoop.record()
              |
              v
        RLTrainer.train_step()   <-- GRPO with review rewards
              |
        ExperienceBuffer.add()
    """

    def __init__(
        self,
        agent_a,
        agent_b,
        trainer,
        experience_buffer,
        max_review_rounds: int = 3,
        use_llm_reviewer: bool = False,
    ):
        """
        Args:
            agent_a: AgentA instance (Generator + Analyst)
            agent_b: AgentB instance (Learner)
            trainer: RLTrainer instance (GRPO)
            experience_buffer: ExperienceBuffer instance
            max_review_rounds: Max review iterations per episode
            use_llm_reviewer: Use LLM for review (vs heuristic)
        """
        self.agent_a = agent_a
        self.agent_b = agent_b
        self.trainer = trainer
        self.experience_buffer = experience_buffer

        # Protocol components
        self.protocol = ProducerReviewerProtocol(max_rounds=max_review_rounds)
        self.producer = ProducerAgent()
        self.reviewer = ReviewerAgent(use_llm=use_llm_reviewer)
        self.feedback_loop = FeedbackLoop()

        # Stats
        self.episode_count = 0
        self.episode_results: List[EpisodeResult] = []

    def run_episode(
        self,
        stage: str,
        objectives: List[str],
        context: Dict[str, Any] = None,
    ) -> EpisodeResult:
        """
        Run a full Producer-Reviewer episode.

        Flow:
        1. Agent A generates environment (existing logic)
        2. Producer wraps it as a ProducerTask
        3. Review loop: Agent B executes, Agent A reviews
        4. GRPO trains on review-weighted rewards
        5. Experience buffer updated

        Args:
            stage: Learning stage (beginner/intermediate/advanced)
            objectives: Task objectives
            context: Optional additional context

        Returns:
            EpisodeResult with verdict, reward, and training data
        """
        self.episode_count += 1
        self.feedback_loop.start_session()

        # Step 1: Agent A generates environment (existing logic)
        from agent_a.generator import AgentBProgress
        progress = AgentBProgress(
            total_experiments=self.episode_count * 5,
            keep_rate=0.5 if stage == "intermediate" else (0.2 if stage == "beginner" else 0.7),
        )
        env = self.agent_a.generate_environment(progress)

        # Step 2: Producer creates structured task
        task = self.producer.create_task(
            stage=stage,
            objectives=objectives,
            context=context,
        )
        producer_task = task.to_producer_task()

        # Step 3: Run Producer-Reviewer loop
        grpo_rewards = []
        final_result = None

        for round_num in range(1, self.protocol.max_rounds + 1):
            # Agent B executes
            ideas = self.agent_b.propose_ideas(env)
            if not ideas:
                break

            experiment_results = []
            for idea in ideas[:2]:  # Limit per round
                result = self.agent_b.run_experiment(idea, env)
                experiment_results.append(result)

            # Aggregate output for review
            learner_output = self._aggregate_results(experiment_results)

            # Agent A reviews (using Analyst capabilities)
            review = self._run_review(producer_task, learner_output, round_num)

            # Record feedback
            self.feedback_loop.record_feedback(
                task_id=producer_task.id,
                round=round_num,
                verdict=review.verdict.value,
                score=review.overall_score(),
                feedback=review.feedback,
                issues=[r for r in review.revisions_requested],
            )

            # Collect GRPO reward
            grpo_rewards.append(review.to_grpo_reward())

            if review.verdict == ReviewVerdict.ACCEPT:
                final_result = {
                    "verdict": "accept",
                    "rounds": round_num,
                    "reward": review.to_grpo_reward(),
                    "experiment_results": experiment_results,
                }
                break
            elif review.verdict == ReviewVerdict.REJECT:
                final_result = {
                    "verdict": "reject",
                    "rounds": round_num,
                    "reward": 0.0,
                    "experiment_results": experiment_results,
                }
                break
            else:
                # REVISE: update task with feedback and continue
                producer_task = self.protocol._revise_task(
                    producer_task,
                    review.feedback,
                    review.revisions_requested,
                )

        # Handle max rounds without accept
        if final_result is None:
            final_result = {
                "verdict": "max_rounds",
                "rounds": self.protocol.max_rounds,
                "reward": grpo_rewards[-1] * 0.5 if grpo_rewards else 0.0,
                "experiment_results": [],
            }

        # Step 4: GRPO training with review-weighted rewards
        rl_data = [
            {
                "id": f"ep{self.episode_count}-r{i+1}",
                "status": "keep" if r >= 0.6 else "discard",
                "reward": r,
                "predicted_tools": [],
                "ground_truth_tools": [],
                "description": f"Round {i+1} reward",
            }
            for i, r in enumerate(grpo_rewards)
        ]

        if rl_data:
            train_stats = self.trainer.train_step(rl_data, use_grpo=True)
        else:
            train_stats = {}

        # Step 5: Update experience buffer
        from shared.experience_buffer import Experience
        for i, reward in enumerate(grpo_rewards):
            exp = Experience(
                state={"task_id": producer_task.id, "round": i + 1, "stage": stage},
                action={"objectives": objectives},
                reward=reward,
                next_state={"done": i == len(grpo_rewards) - 1},
                done=(i == len(grpo_rewards) - 1),
                info={"verdict": final_result["verdict"], "train_stats": train_stats},
                priority=reward,
            )
            self.experience_buffer.add(exp)

        # Step 6: Compile episode result
        session_summary = self.feedback_loop.end_session()

        episode = EpisodeResult(
            verdict=final_result["verdict"],
            rounds=final_result["rounds"],
            final_reward=final_result["reward"],
            grpo_rewards=grpo_rewards,
            feedback_summary=self.protocol.get_feedback_summary(),
            metadata={
                "task_id": producer_task.id,
                "stage": stage,
                "objectives": objectives,
                "train_stats": train_stats,
                "session_summary": session_summary,
                "description": producer_task.description,
            },
        )

        self.episode_results.append(episode)
        return episode

    def _aggregate_results(self, results: List[Any]) -> Dict[str, Any]:
        """Aggregate Agent B experiment results for review"""
        if not results:
            return {"status": "no_results", "score": 0.0}

        keep_count = sum(1 for r in results if r.status == "keep")
        avg_reward = sum(r.reward for r in results) / len(results)
        avg_score = sum(r.metrics.get("score", 0) for r in results) / len(results)

        return {
            "status": "keep" if keep_count > len(results) / 2 else "discard",
            "keep_rate": keep_count / len(results),
            "avg_reward": avg_reward,
            "avg_score": avg_score,
            "experiment_count": len(results),
            "outputs": [r.output for r in results],
        }

    def _run_review(
        self,
        task: ProducerTask,
        learner_output: Dict[str, Any],
        round_num: int,
    ) -> ReviewRound:
        """Run review using Agent A's Analyst capabilities"""
        # Determine criteria based on stage
        criteria_map = {
            "beginner": [ReviewCriteria.FORMAT, ReviewCriteria.COMPLETENESS, ReviewCriteria.ACCURACY],
            "intermediate": [ReviewCriteria.FORMAT, ReviewCriteria.COMPLETENESS, ReviewCriteria.ACCURACY, ReviewCriteria.STYLE],
            "advanced": list(ReviewCriteria),
        }
        criteria = criteria_map.get(task.stage, list(ReviewCriteria))

        # Use heuristic review (LLM review requires external integration)
        review_output = self.reviewer.review(
            task_description=task.description,
            learner_output=learner_output,
            criteria=criteria,
            context=task.context,
        )

        # Convert to ReviewRound
        scores = {s.criteria: s.score for s in review_output.scores}
        verdict = ReviewVerdict(review_output.verdict)

        return ReviewRound(
            round_id=round_num,
            timestamp=__import__("datetime").datetime.now().isoformat(),
            verdict=verdict,
            scores=scores,
            feedback=review_output.feedback,
            revisions_requested=review_output.revisions_needed,
        )

    def get_statistics(self) -> Dict[str, Any]:
        """Get integration statistics"""
        if not self.episode_results:
            return {"total_episodes": 0}

        verdicts = {}
        for ep in self.episode_results:
            verdicts[ep.verdict] = verdicts.get(ep.verdict, 0) + 1

        avg_reward = sum(ep.final_reward for ep in self.episode_results) / len(self.episode_results)
        avg_rounds = sum(ep.rounds for ep in self.episode_results) / len(self.episode_results)

        return {
            "total_episodes": len(self.episode_results),
            "verdict_distribution": verdicts,
            "acceptance_rate": verdicts.get("accept", 0) / len(self.episode_results),
            "average_reward": avg_reward,
            "average_rounds": avg_rounds,
            "feedback_analysis": self.feedback_loop.export_for_analysis(),
        }

    def print_summary(self):
        """Print a human-readable summary"""
        stats = self.get_statistics()
        print("\n" + "=" * 60)
        print("Producer-Reviewer Integration Summary")
        print("=" * 60)
        print(f"Total Episodes:    {stats['total_episodes']}")
        print(f"Acceptance Rate:   {stats.get('acceptance_rate', 0):.1%}")
        print(f"Average Reward:    {stats.get('average_reward', 0):.3f}")
        print(f"Average Rounds:    {stats.get('average_rounds', 0):.1f}")
        print(f"Verdict Breakdown: {stats.get('verdict_distribution', {})}")
        print("=" * 60)
