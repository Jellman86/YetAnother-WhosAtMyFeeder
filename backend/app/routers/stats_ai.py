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
from app.auth_legacy import get_auth_context_with_legacy

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
    estimated_cost_usd: float = 0.0

class AIUsageDaily(BaseModel):
    day: str
    calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float = 0.0

class AIUsageResponse(BaseModel):
    span: str
    from_date: str
    to_date: str
    calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float = 0.0
    pricing_configured: bool = False
    breakdown: List[AIUsageBreakdown]
    daily: List[AIUsageDaily]

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
                    "output": entry.get("outputPer1M", 0.0)
                }
        return rates
    except Exception:
        return {}

def _calculate_cost(input_tokens: int, output_tokens: int, provider: str, model: str, rates: Dict) -> float:
    key = f"{provider.lower()}|{model.lower()}"
    rate = rates.get(key)
    if not rate:
        # Try wildcard for model
        rate = rates.get(f"{provider.lower()}|*")
    
    if not rate:
        return 0.0
    
    cost = (input_tokens / 1_000_000.0) * rate["input"] + (output_tokens / 1_000_000.0) * rate["output"]
    return cost

@router.get("/stats/ai/usage", response_model=AIUsageResponse)
async def get_ai_usage(
    request: Request,
    span: Literal["24h", "7d", "30d", "90d"] = Query("30d"),
    auth: AuthContext = Depends(get_auth_context_with_legacy)
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
    
    # Enrich breakdown with costs
    enriched_breakdown = []
    total_cost = 0.0
    for item in raw_summary["breakdown"]:
        cost = _calculate_cost(item["input_tokens"], item["output_tokens"], item["provider"], item["model"], rates)
        total_cost += cost
        enriched_breakdown.append(AIUsageBreakdown(
            **item,
            estimated_cost_usd=cost
        ))
    
    # Enrich daily with costs (this is tricky because we need provider/model per day to be accurate)
    # For now, we'll do a best-effort daily cost if possible, or skip it if repo summary doesn't have it.
    # Actually, let's update repo to provide daily breakdown if we want accurate daily costs.
    # Given HarborWatch has it, let's just use total daily stats for now and simplify.
    
    daily_stats = []
    for item in raw_summary["daily"]:
        # Note: accurate daily cost requires provider/model grouping per day.
        # For simplicity in this first pass, we'll just return the tokens.
        daily_stats.append(AIUsageDaily(**item))

    return AIUsageResponse(
        span=span,
        from_date=start_date.isoformat(),
        to_date=now.isoformat(),
        calls=raw_summary["calls"],
        input_tokens=raw_summary["input_tokens"],
        output_tokens=raw_summary["output_tokens"],
        total_tokens=raw_summary["total_tokens"],
        estimated_cost_usd=total_cost,
        pricing_configured=pricing_configured,
        breakdown=enriched_breakdown,
        daily=daily_stats
    )

@router.delete("/stats/ai/usage")
async def clear_ai_usage(
    auth: AuthContext = Depends(require_owner)
):
    """Clear AI usage history logs. Owner only."""
    async with get_db() as db:
        repo = AIUsageRepository(db)
        count = await repo.clear_history()
    
    return {"status": "ok", "deleted_count": count}
