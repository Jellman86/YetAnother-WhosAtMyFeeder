"""Estimated cost of AI usage, and how much of the usage the estimate covers.

A model with no rate in the pricing registry has no estimated cost. That is
different from a cost of zero, which is what the usage view used to print for
it, so each item says whether it was priced and the total says what it leaves
out.
"""

from __future__ import annotations

from dataclasses import dataclass, field

Rate = dict[str, float]


def rate_for(provider: str, model: str, rates: dict[str, Rate]) -> Rate | None:
    """The model's own rate, else its provider's wildcard, else None: no price is known."""
    provider_key = provider.lower()
    return rates.get(f"{provider_key}|{model.lower()}") or rates.get(f"{provider_key}|*")


@dataclass(frozen=True)
class CostSummary:
    """Usage rows with their cost where one could be estimated, and the coverage of the total."""

    items: list[dict] = field(default_factory=list)
    # None when there was usage and none of it had a price: there is nothing to total.
    estimated_cost_usd: float | None = 0.0
    priced_calls: int = 0
    unpriced_calls: int = 0
    priced_tokens: int = 0
    unpriced_tokens: int = 0
    unpriced_models: list[str] = field(default_factory=list)


def cost_summary(breakdown: list[dict], rates: dict[str, Rate]) -> CostSummary:
    """Cost each usage row that has a rate and total only those, counting what is left out."""
    items: list[dict] = []
    total = 0.0
    priced_calls = unpriced_calls = priced_tokens = unpriced_tokens = 0
    unpriced_models: list[str] = []
    for row in breakdown:
        rate = rate_for(str(row["provider"]), str(row["model"]), rates)
        if rate is None:
            unpriced_calls += int(row["calls"])
            unpriced_tokens += int(row["total_tokens"])
            name = f"{row['provider']}/{row['model']}"
            if name not in unpriced_models:
                unpriced_models.append(name)
            items.append({**row, "estimated_cost_usd": None, "priced": False})
            continue
        cost = (int(row["input_tokens"]) / 1_000_000.0) * rate["input"] + (
            int(row["output_tokens"]) / 1_000_000.0
        ) * rate["output"]
        total += cost
        priced_calls += int(row["calls"])
        priced_tokens += int(row["total_tokens"])
        items.append({**row, "estimated_cost_usd": cost, "priced": True})
    return CostSummary(
        items=items,
        estimated_cost_usd=None if unpriced_calls and not priced_calls else total,
        priced_calls=priced_calls,
        unpriced_calls=unpriced_calls,
        priced_tokens=priced_tokens,
        unpriced_tokens=unpriced_tokens,
        unpriced_models=unpriced_models,
    )
