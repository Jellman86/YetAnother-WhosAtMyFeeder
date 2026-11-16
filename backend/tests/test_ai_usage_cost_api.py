"""`/api/stats/ai/usage` reports cost only for usage that has a price, and says what it left out."""

import json

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import get_db
from app.repositories.ai_usage_repository import AIUsageRepository


@pytest_asyncio.fixture
async def client():
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def recorded_usage():
    async with get_db() as db:
        await db.execute("DELETE FROM ai_usage_log")
        repo = AIUsageRepository(db)
        await repo.record_usage("gemini", "gemini-2.5-flash", "analysis", 1_000_000, 0)
        await repo.record_usage("claude", "claude-opus", "analysis", 500_000, 20_000)
        await repo.record_usage("claude", "claude-opus", "chat", 100_000, 5_000)
    yield
    async with get_db() as db:
        await db.execute("DELETE FROM ai_usage_log")
        await db.commit()


@pytest.mark.asyncio
async def test_an_unpriced_model_reports_no_cost_and_the_total_states_its_coverage(client, recorded_usage, monkeypatch):
    monkeypatch.setattr(
        settings.classification,
        "ai_pricing_json",
        json.dumps([{"provider": "google", "model": "gemini-2.5-flash", "inputPer1M": 0.30, "outputPer1M": 2.50}]),
    )

    response = await client.get("/api/stats/ai/usage")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["estimated_cost_usd"] == pytest.approx(0.30)
    assert (body["priced_calls"], body["unpriced_calls"]) == (1, 2)
    assert body["unpriced_models"] == ["claude/claude-opus"]
    by_model = {(item["model"], item["feature"]): item for item in body["breakdown"]}
    assert by_model[("gemini-2.5-flash", "analysis")]["estimated_cost_usd"] == pytest.approx(0.30)
    assert by_model[("claude-opus", "chat")]["estimated_cost_usd"] is None
    assert by_model[("claude-opus", "chat")]["priced"] is False
    assert all("estimated_cost_usd" not in day for day in body["daily"])


@pytest.mark.asyncio
async def test_usage_with_no_prices_at_all_has_no_total(client, recorded_usage, monkeypatch):
    monkeypatch.setattr(settings.classification, "ai_pricing_json", "[]")

    body = (await client.get("/api/stats/ai/usage")).json()

    assert body["estimated_cost_usd"] is None
    assert body["pricing_configured"] is False
    assert body["unpriced_calls"] == 3
