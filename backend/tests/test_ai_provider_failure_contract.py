"""Provider failures never become persisted answers or successful API responses."""

from contextlib import asynccontextmanager, closing
from datetime import datetime, timezone
import asyncio
import base64
import os
import sqlite3

import aiosqlite
import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.main import app
from app.routers import ai
from app.services import ai_service as module
from app.services.ai_service import AIAnalysisError, AIService


def provider_answer(provider):
    if provider == "gemini":
        return {"candidates": [{"content": {"parts": [{"text": "A successful answer."}]}}]}
    if provider == "claude":
        return {"content": [{"type": "text", "text": "A successful answer."}]}
    return {"choices": [{"message": {"content": "A successful answer."}}]}


@pytest.fixture
def provider_boundary(monkeypatch):
    monkeypatch.setattr(settings.llm, "enabled", True)
    monkeypatch.setattr(settings.llm, "api_key", "fixture-provider-secret")
    monkeypatch.setattr(settings.llm, "model", "fixture-model")
    requests = []
    responses = []

    async def handle(request):
        requests.append(request)
        next_response = responses.pop(0)
        if isinstance(next_response, BaseException):
            raise next_response
        status, data = next_response
        return httpx.Response(status, json=data, headers={"Retry-After": "7"}, request=request)

    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(handle)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))
    return requests, responses, original_client


async def invoke(service, feature):
    if feature == "chat":
        return await service.chat_detection("A follow-up question.")
    if feature == "chart":
        return await service.analyze_chart(b"fixture-image", {})
    return await service.analyze_detection("Robin", b"fixture-image", {})


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["gemini", "openai", "claude", "openrouter"])
@pytest.mark.parametrize("feature", ["analysis", "chart", "chat"])
@pytest.mark.parametrize("status", [400, 401, 429, 500, 503])
async def test_all_provider_features_return_marked_http_failures(
    provider_boundary, monkeypatch, provider, feature, status
):
    requests, responses, _client = provider_boundary
    monkeypatch.setattr(settings.llm, "provider", provider)
    responses.append((status, {"error": {"message": "fixture-provider-secret must not be displayed"}}))
    result = await invoke(AIService(), feature)
    assert isinstance(result, AIAnalysisError)
    assert result.retryable is (status in {429, 500, 503})
    assert result.http_status_hint == (status if status in {429, 503} else 400 if status < 500 else 502)
    assert result.retry_after_seconds == 7
    assert "fixture-provider-secret" not in result
    assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["gemini", "openai", "claude", "openrouter"])
@pytest.mark.parametrize("feature", ["analysis", "chart", "chat"])
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": [{"message": {"content": []}}]},
        {"candidates": [{"content": {"parts": [{"text": "   "}]}}]},
        {"content": [{"text": None}]},
    ],
)
async def test_empty_or_malformed_provider_content_is_a_failure(
    provider_boundary, monkeypatch, provider, feature, payload
):
    requests, responses, _client = provider_boundary
    monkeypatch.setattr(settings.llm, "provider", provider)
    responses.append((200, payload))
    result = await invoke(AIService(), feature)
    assert isinstance(result, AIAnalysisError)
    assert result.http_status_hint == 502
    assert result.retryable


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["gemini", "openai", "claude", "openrouter"])
@pytest.mark.parametrize("feature", ["analysis", "chart", "chat"])
async def test_timeouts_are_marked_and_do_not_expose_raw_exception_text(
    provider_boundary, monkeypatch, provider, feature
):
    requests, responses, _client = provider_boundary
    monkeypatch.setattr(settings.llm, "provider", provider)
    responses.append(httpx.ReadTimeout("fixture-provider-secret"))
    result = await invoke(AIService(), feature)
    assert isinstance(result, AIAnalysisError)
    assert result.retryable
    assert "fixture-provider-secret" not in result


@pytest.mark.asyncio
@pytest.mark.parametrize("feature", ["analysis", "chart", "chat"])
@pytest.mark.parametrize("configuration", ["disabled", "missing_key", "unsupported"])
async def test_invalid_configuration_is_not_a_successful_answer(provider_boundary, monkeypatch, feature, configuration):
    requests, _responses, _client = provider_boundary
    if configuration == "disabled":
        monkeypatch.setattr(settings.llm, "enabled", False)
    elif configuration == "missing_key":
        monkeypatch.setattr(settings.llm, "api_key", "")
    else:
        monkeypatch.setattr(settings.llm, "provider", "unsupported")
    result = await invoke(AIService(), feature)
    assert isinstance(result, AIAnalysisError)
    assert result.http_status_hint == 400
    assert not result.retryable
    assert not requests


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["gemini", "openai", "claude", "openrouter"])
async def test_provider_cancellation_propagates(provider_boundary, monkeypatch, provider):
    _requests, responses, _client = provider_boundary
    monkeypatch.setattr(settings.llm, "provider", provider)
    responses.append(asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await invoke(AIService(), "analysis")


@pytest.mark.asyncio
@pytest.mark.parametrize("feature", ["analysis", "chat"])
async def test_gemini_key_is_not_in_request_urls_or_verbose_http_logs(provider_boundary, monkeypatch, caplog, feature):
    import logging

    requests, responses, _client = provider_boundary
    monkeypatch.setattr(settings.llm, "provider", "gemini")
    caplog.set_level(logging.DEBUG)
    responses.append((200, provider_answer("gemini")))
    assert await invoke(AIService(), feature) == "A successful answer."
    assert "fixture-provider-secret" not in caplog.text
    assert requests[0].headers["x-goog-api-key"] == "fixture-provider-secret"
    assert "key=" not in str(requests[0].url)


@pytest_asyncio.fixture
async def provider_api(tmp_path, monkeypatch, provider_boundary):
    path = tmp_path / "history.db"
    with closing(sqlite3.connect(os.environ["DB_PATH"])) as source, closing(sqlite3.connect(path)) as target:
        source.backup(target)
        target.execute("PRAGMA foreign_keys=ON")
        target.execute("DELETE FROM detections")
        target.execute(
            "INSERT INTO detections (detection_time,detection_index,score,display_name,category_name,frigate_event,camera_name) VALUES (?,1,.9,'Robin','Robin','provider-fixture','camera')",
            (datetime.now(timezone.utc).isoformat(),),
        )
        target.commit()

    @asynccontextmanager
    async def database():
        async with aiosqlite.connect(path) as db:
            yield db

    monkeypatch.setattr(ai, "get_db", database)
    monkeypatch.setattr(module, "get_db", database)
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    from unittest.mock import AsyncMock

    monkeypatch.setattr(ai.frigate_client, "get_snapshot", AsyncMock(return_value=b"fixture-image"))
    requests, responses, client_class = provider_boundary
    async with client_class(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        yield client, requests, responses, database


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["gemini", "openai", "claude", "openrouter"])
async def test_analysis_error_is_not_cached_and_retry_can_save_a_real_answer(provider_api, monkeypatch, provider):
    client, requests, responses, database = provider_api
    monkeypatch.setattr(settings.llm, "provider", provider)
    responses.extend([(429, {"error": {"message": "fixture failure"}}), (200, provider_answer(provider)), (503, {})])
    route = "/api/events/provider-fixture/analyze?use_clip=false"
    first = await client.post(route)
    assert first.status_code == 429
    assert first.headers["retry-after"] == "7"
    async with database() as db:
        assert (
            await (
                await db.execute("SELECT ai_analysis FROM detections WHERE frigate_event='provider-fixture'")
            ).fetchone()
        )[0] is None
    second = await client.post(route)
    assert second.status_code == 200
    assert second.json()["analysis"] == "A successful answer."
    assert (await client.post(route)).json() == second.json()
    assert len(requests) == 2
    assert (await client.post(route + "&force=true")).status_code == 503
    assert (await client.post(route)).json() == second.json()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["gemini", "openai", "claude", "openrouter"])
async def test_chat_and_chart_errors_do_not_persist_assistant_answers(provider_api, monkeypatch, provider):
    client, requests, responses, database = provider_api
    monkeypatch.setattr(settings.llm, "provider", provider)
    responses.extend([(429, {}), (503, {})])
    chat = await client.post("/api/events/provider-fixture/conversation", json={"message": "Owner question"})
    assert chat.status_code == 429
    turns = (await client.get("/api/events/provider-fixture/conversation")).json()
    assert [(turn["role"], turn["content"]) for turn in turns] == [("user", "Owner question")]
    chart = await client.post(
        "/api/leaderboard/analyze",
        json={"config": {}, "config_key": "fixture-chart", "image_base64": base64.b64encode(b"fixture-image").decode()},
    )
    assert chart.status_code == 503
    cached = await client.get("/api/leaderboard/analysis", params={"config_key": "fixture-chart"})
    assert cached.status_code == 204
