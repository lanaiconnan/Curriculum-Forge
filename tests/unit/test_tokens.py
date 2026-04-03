"""Unit tests for utils/tokens.py — Token Counting & Estimation

Run: pytest tests/unit/test_tokens.py -v
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.tokens import (
    token_count_from_usage,
    input_token_count,
    output_token_count,
    cache_token_count,
    rough_token_count,
    estimate_tokens,
    estimate_messages_tokens,
    estimate_total_tokens,
    TokenBudget,
    TokenBudgetStats,
    model_max_context,
    output_token_budget,
    TokenCostConfig,
)


# ─── API Usage → Token Count ─────────────────────────────────────────────────

class TestTokenCountFromUsage:
    def test_basic_usage(self):
        usage = {
            "input_tokens": 1000,
            "output_tokens": 200,
        }
        assert token_count_from_usage(usage) == 1200

    def test_with_cache(self):
        usage = {
            "input_tokens": 1000,
            "output_tokens": 200,
            "cache_creation_input_tokens": 5000,
            "cache_read_input_tokens": 8000,
        }
        assert token_count_from_usage(usage) == 1000 + 200 + 5000 + 8000

    def test_empty_usage(self):
        assert token_count_from_usage({}) == 0

    def test_input_token_count(self):
        usage = {
            "input_tokens": 1000,
            "cache_creation_input_tokens": 500,
            "cache_read_input_tokens": 300,
        }
        assert input_token_count(usage) == 1800

    def test_output_token_count(self):
        usage = {"output_tokens": 500}
        assert output_token_count(usage) == 500

    def test_cache_token_count(self):
        usage = {
            "cache_creation_input_tokens": 1000,
            "cache_read_input_tokens": 2000,
        }
        assert cache_token_count(usage) == 3000


# ─── Rough Estimation ─────────────────────────────────────────────────────────

class TestRoughTokenCount:
    def test_empty(self):
        assert rough_token_count("") == 0

    def test_english_text(self):
        # ~4 chars per token
        text = "Hello world this is a test"
        count = rough_token_count(text)
        assert 5 <= count <= 10  # Approximate

    def test_multibyte_text(self):
        # ~2 chars per token for Asian languages
        text = "你好世界这是一个测试"
        count = rough_token_count(text)
        assert 5 <= count <= 15  # Approximate

    def test_long_text(self):
        text = "x" * 4000
        count = rough_token_count(text)
        assert count == 1000  # 4000 / 4


class TestEstimateTokens:
    def test_string(self):
        text = "Hello world"
        count = estimate_tokens(text)
        assert count > 0

    def test_simple_messages(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        count = estimate_tokens(messages)
        assert count > 0

    def test_content_blocks(self):
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "I will help you."},
                    {"type": "tool_use", "name": "read", "input": {"path": "/file"}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "content": "file contents here"},
                ],
            },
        ]
        count = estimate_tokens(messages)
        assert count > 0

    def test_empty_list(self):
        assert estimate_tokens([]) == 0

    def test_estimate_total_with_system(self):
        messages = [
            {"role": "user", "content": "Hello"},
        ]
        total = estimate_total_tokens(messages, system_prompt="You are helpful.")
        assert total > estimate_tokens(messages)


# ─── TokenBudget ─────────────────────────────────────────────────────────────

class TestTokenBudget:
    def test_initial_state(self):
        budget = TokenBudget(max_tokens=200_000)
        assert budget.total == 0
        assert budget.remaining() == 200_000

    def test_consume_basic(self):
        budget = TokenBudget(max_tokens=200_000)
        budget.consume(input_tokens=1000, output_tokens=200)
        assert budget.total == 1200
        assert budget.remaining() == 200_000 - 1200

    def test_consume_with_cache(self):
        budget = TokenBudget(max_tokens=200_000)
        budget.consume(
            input_tokens=1000,
            output_tokens=200,
            cache_creation_tokens=5000,
            cache_read_tokens=8000,
        )
        assert budget.total == 1000 + 200 + 5000 + 8000

    def test_consume_from_usage_dict(self):
        budget = TokenBudget(max_tokens=200_000)
        budget.consume(usage={
            "input_tokens": 1000,
            "output_tokens": 200,
        })
        assert budget.total == 1200

    def test_needs_compact(self):
        budget = TokenBudget(max_tokens=100_000, warning_threshold=0.8)
        budget.consume(input_tokens=79_000)
        assert not budget.needs_compact()
        
        # consume replaces, so set total to 80_000
        budget.consume(input_tokens=80_000)
        assert budget.needs_compact()

    def test_available_for(self):
        budget = TokenBudget(max_tokens=100_000)
        budget.consume(input_tokens=50_000)
        
        available = budget.available_for(max_output_tokens=4000)
        assert available == 100_000 - 4000 - 50_000

    def test_available_for_with_cache(self):
        budget = TokenBudget(max_tokens=100_000)
        budget.consume(
            input_tokens=10_000,
            cache_read_tokens=40_000,  # Cache doesn't count
        )
        
        available = budget.available_for(max_output_tokens=4000, include_cache=False)
        # Only input counts, not cache
        assert available == 100_000 - 4000 - 10_000

    def test_reset(self):
        budget = TokenBudget(max_tokens=200_000)
        budget.consume(input_tokens=50_000)
        budget.reset()
        assert budget.total == 0

    def test_snapshot(self):
        budget = TokenBudget(max_tokens=200_000, warning_threshold=0.8)
        budget.consume(input_tokens=1000, output_tokens=200)
        
        stats = budget.snapshot()
        assert stats.max_tokens == 200_000
        assert stats.current_tokens == 1200
        assert stats.input_tokens == 1000
        assert stats.output_tokens == 200
        assert stats.usage_ratio == 1200 / 200_000
        assert not stats.is_warning
        assert not stats.is_over


class TestTokenBudgetStats:
    def test_usage_ratio(self):
        stats = TokenBudgetStats(
            max_tokens=100_000,
            current_tokens=50_000,
            warning_threshold=0.8,
        )
        assert stats.usage_ratio == 0.5

    def test_is_warning(self):
        stats = TokenBudgetStats(
            max_tokens=100_000,
            current_tokens=80_000,
            warning_threshold=0.8,
        )
        assert stats.is_warning

    def test_is_over(self):
        stats = TokenBudgetStats(
            max_tokens=100_000,
            current_tokens=100_001,
            warning_threshold=0.8,
        )
        assert stats.is_over


# ─── Context Window Utilities ────────────────────────────────────────────────

class TestModelMaxContext:
    def test_sonnet(self):
        assert model_max_context("claude-3-5-sonnet-20241022") == 200_000
        assert model_max_context("claude-sonnet-4-20250514") == 200_000

    def test_opus(self):
        assert model_max_context("claude-3-opus-20240229") == 200_000

    def test_haiku(self):
        assert model_max_context("claude-3-haiku-20240307") == 200_000

    def test_unknown(self):
        assert model_max_context("unknown-model") == 200_000


class TestOutputTokenBudget:
    def test_basic(self):
        budget = output_token_budget(context_tokens=100_000, max_context=200_000)
        assert budget == 200_000 - 100_000 - 100

    def test_near_limit(self):
        budget = output_token_budget(context_tokens=199_900, max_context=200_000)
        assert budget == 0  # No room for output


# ─── Cost Estimation ──────────────────────────────────────────────────────────

class TestTokenCostConfig:
    def test_default_costs(self):
        config = TokenCostConfig()
        
        # 1M input tokens = $3
        cost = config.estimate_cost(input_tokens=1_000_000)
        assert cost == 3.0

    def test_output_cost(self):
        config = TokenCostConfig()
        
        # 1M output tokens = $15
        cost = config.estimate_cost(output_tokens=1_000_000)
        assert cost == 15.0

    def test_cache_cost(self):
        config = TokenCostConfig()
        
        # 1M cache creation = $3.75
        # 1M cache read = $0.30
        cost = config.estimate_cost(
            cache_creation_tokens=1_000_000,
            cache_read_tokens=1_000_000,
        )
        assert cost == 3.75 + 0.30

    def test_from_usage_dict(self):
        config = TokenCostConfig()
        
        cost = config.estimate_cost(usage={
            "input_tokens": 1_000_000,
            "output_tokens": 500_000,
        })
        assert cost == 3.0 + 7.5

    def test_custom_costs(self):
        config = TokenCostConfig(
            input_cost_per_m=1.0,
            output_cost_per_m=2.0,
        )
        
        cost = config.estimate_cost(input_tokens=1_000_000, output_tokens=1_000_000)
        assert cost == 3.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
