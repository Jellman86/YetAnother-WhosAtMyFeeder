"""A cost is an estimate only where a price exists.

The AI usage view printed `$0.00` for a model with no rate in the pricing
registry: an absent price presented as a measured cost of nothing. A model is
priced or it is not, the total covers only the priced usage, and the response
says how much usage that leaves out.
"""

from app.services.ai_cost import cost_summary, rate_for

RATES = {
    "gemini|gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "openai|*": {"input": 1.00, "output": 4.00},
    "ollama|llava": {"input": 0.0, "output": 0.0},
}


def usage(provider: str, model: str, calls: int, input_tokens: int, output_tokens: int) -> dict:
    return {
        "provider": provider,
        "model": model,
        "feature": "analysis",
        "calls": calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


def test_a_model_takes_its_own_rate_then_its_providers_wildcard():
    assert rate_for("Gemini", "Gemini-2.5-Flash", RATES) == {"input": 0.30, "output": 2.50}
    assert rate_for("openai", "gpt-5", RATES) == {"input": 1.00, "output": 4.00}
    assert rate_for("claude", "claude-opus", RATES) is None


def test_usage_with_a_price_is_costed_from_its_tokens():
    summary = cost_summary([usage("gemini", "gemini-2.5-flash", 4, 1_000_000, 100_000)], RATES)

    assert summary.items[0]["estimated_cost_usd"] == 0.30 + 0.25
    assert summary.items[0]["priced"] is True
    assert summary.estimated_cost_usd == 0.55
    assert (summary.priced_calls, summary.unpriced_calls) == (4, 0)
    assert summary.unpriced_models == []


def test_a_model_without_a_price_has_no_cost_rather_than_a_cost_of_zero():
    summary = cost_summary([usage("claude", "claude-opus", 3, 500_000, 20_000)], RATES)

    assert summary.items[0]["estimated_cost_usd"] is None
    assert summary.items[0]["priced"] is False
    assert summary.estimated_cost_usd is None
    assert (summary.priced_calls, summary.unpriced_calls) == (0, 3)
    assert summary.unpriced_models == ["claude/claude-opus"]


def test_a_total_covers_only_the_priced_usage_and_says_what_it_leaves_out():
    summary = cost_summary(
        [
            usage("gemini", "gemini-2.5-flash", 4, 1_000_000, 0),
            usage("claude", "claude-opus", 3, 500_000, 20_000),
            usage("claude", "claude-opus", 2, 100_000, 5_000),
        ],
        RATES,
    )

    assert summary.estimated_cost_usd == 0.30
    assert (summary.priced_calls, summary.unpriced_calls) == (4, 5)
    assert (summary.priced_tokens, summary.unpriced_tokens) == (1_000_000, 625_000)
    # Named once, however many features used it.
    assert summary.unpriced_models == ["claude/claude-opus"]


def test_a_price_of_zero_the_owner_entered_is_a_price():
    summary = cost_summary([usage("ollama", "llava", 9, 2_000_000, 300_000)], RATES)

    assert summary.items[0]["estimated_cost_usd"] == 0.0
    assert summary.items[0]["priced"] is True
    assert summary.estimated_cost_usd == 0.0
    assert summary.unpriced_calls == 0


def test_no_usage_costs_nothing_and_leaves_nothing_out():
    summary = cost_summary([], RATES)

    assert summary.estimated_cost_usd == 0.0
    assert (summary.priced_calls, summary.unpriced_calls) == (0, 0)
