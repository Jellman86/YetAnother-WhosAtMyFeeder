from fastapi import APIRouter, Depends, Request, Query
from datetime import datetime, timedelta
from typing import List, Literal, Dict
import json
import structlog
from pydantic import BaseModel

from app.database import get_db
from app.repositories.ai_usage_repository import AIUsageRepository
from app.config import settings
from app.auth import AuthContext, require_owner
from app.services.ai_cost import cost_summary

router = APIRouter()
log = structlog.get_logger()


class AIUsageBreakdown(BaseModel):
    provider: str
    model: str
    feature: str
    calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    # None when the pricing registry holds no rate for this model: not estimated, never zero.
    estimated_cost_usd: float | None = None
    priced: bool = False


class AIUsageDaily(BaseModel):
    day: str
    calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int


class AIUsageResponse(BaseModel):
    span: str
    from_date: str
    to_date: str
    calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    # The cost of the priced usage only; None when there was usage and none of it had a price.
    estimated_cost_usd: float | None = None
    pricing_configured: bool = False
    # How much of the usage the estimate covers, so a total is never read as the whole bill.
    priced_calls: int = 0
    unpriced_calls: int = 0
    priced_tokens: int = 0
    unpriced_tokens: int = 0
    unpriced_models: List[str] = []
    breakdown: List[AIUsageBreakdown]
    daily: List[AIUsageDaily]


class AIUsageClearResponse(BaseModel):
    status: str
    deleted_count: int


def _parse_pricing() -> Dict[str, Dict[str, float]]:
    """Parse ai_pricing_json into a lookup map."""
    try:
        data = json.loads(settings.classification.ai_pricing_json)
        rates = {}
        for entry in data:
            provider = entry.get("provider", "").lower()
            if provider == "anthropic":
                provider = "claude"
            elif provider == "google":
                provider = "gemini"
            model = entry.get("model", "").lower()
            if provider and model:
                rates[f"{provider}|{model}"] = {
                    "input": entry.get("inputPer1M", 0.0),
                    "output": entry.get("outputPer1M", 0.0),
                }
        return rates
    except Exception:
        return {}


@router.get("/stats/ai/usage", response_model=AIUsageResponse)
async def get_ai_usage(
    request: Request,
    span: Literal["24h", "7d", "30d", "90d"] = Query("30d"),
    auth: AuthContext = Depends(require_owner),
):
    """Get summarized AI API usage and estimated costs."""
    now = datetime.utcnow()
    if span == "24h":
        start_date = now - timedelta(hours=24)
    elif span == "7d":
        start_date = now - timedelta(days=7)
    elif span == "90d":
        start_date = now - timedelta(days=90)
    else:
        start_date = now - timedelta(days=30)

    async with get_db() as db:
        repo = AIUsageRepository(db)
        raw_summary = await repo.get_summary(start_date, now)

    rates = _parse_pricing()
    pricing_configured = len(rates) > 0

    costs = cost_summary(raw_summary["breakdown"], rates)
    daily_stats = [AIUsageDaily(**item) for item in raw_summary["daily"]]

    return AIUsageResponse(
        span=span,
        from_date=start_date.isoformat(),
        to_date=now.isoformat(),
        calls=raw_summary["calls"],
        input_tokens=raw_summary["input_tokens"],
        output_tokens=raw_summary["output_tokens"],
        total_tokens=raw_summary["total_tokens"],
        estimated_cost_usd=costs.estimated_cost_usd,
        pricing_configured=pricing_configured,
        priced_calls=costs.priced_calls,
        unpriced_calls=costs.unpriced_calls,
        priced_tokens=costs.priced_tokens,
        unpriced_tokens=costs.unpriced_tokens,
        unpriced_models=costs.unpriced_models,
        breakdown=[AIUsageBreakdown(**item) for item in costs.items],
        daily=daily_stats,
    )


@router.delete("/stats/ai/usage", response_model=AIUsageClearResponse)
async def clear_ai_usage(_auth: AuthContext = Depends(require_owner)) -> AIUsageClearResponse:
    """Clear AI usage history logs. Owner only."""
    async with get_db() as db:
        repo = AIUsageRepository(db)
        count = await repo.clear_history()

    return AIUsageClearResponse(status="ok", deleted_count=count)
