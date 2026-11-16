"""The status snapshot over the live stream and over HTTP: owners get it, guests never do, and it carries no secret."""

import asyncio
import json

import httpx
import pytest
from starlette.requests import Request

from app.auth import AuthContext, AuthLevel, StreamAuth
from app.config import settings
from app.main import app, sse_endpoint
from app.services.broadcaster import broadcaster

MQTT_SECRET = "fixture-mqtt-password-7731"
FRIGATE_SECRET = "fixture-frigate-password-7731"


def _stream_request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/api/sse", "headers": [], "query_string": b""})


def _frame(raw: str) -> dict:
    return json.loads(raw.removeprefix("data: "))


@pytest.fixture
def configured_secrets(monkeypatch):
    monkeypatch.setattr(settings.frigate, "mqtt_password", MQTT_SECRET)
    monkeypatch.setattr(settings.frigate, "mqtt_server", f"owner:{MQTT_SECRET}@broker")
    monkeypatch.setattr(settings.frigate, "frigate_url", f"http://owner:{FRIGATE_SECRET}@frigate:5000")


@pytest.mark.asyncio
async def test_an_owner_stream_opens_with_the_status_snapshot_and_no_secret(configured_secrets):
    response = await sse_endpoint(_stream_request(), StreamAuth(AuthContext(AuthLevel.OWNER), None))
    try:
        assert _frame(await response.body_iterator.__anext__())["type"] == "connected"
        raw = await asyncio.wait_for(response.body_iterator.__anext__(), 10)
    finally:
        await response.body_iterator.aclose()

    status = _frame(raw)
    assert status["type"] == "status"
    snapshot = status["data"]
    assert {verdict["key"] for verdict in snapshot["subsystems"]} == {
        "mqtt",
        "frigate",
        "classifier",
        "finder",
        "audio",
        "storage",
        "notifications",
    }
    assert snapshot["overall"]["state"] in {"ok", "degraded", "unknown"}
    assert MQTT_SECRET not in raw
    assert FRIGATE_SECRET not in raw


@pytest.mark.asyncio
async def test_a_guest_stream_never_carries_the_status_snapshot(monkeypatch):
    monkeypatch.setattr(settings.public_access, "enabled", True)
    response = await sse_endpoint(_stream_request(), StreamAuth(AuthContext(AuthLevel.GUEST), None))
    try:
        await response.body_iterator.__anext__()
        await broadcaster.broadcast({"type": "status", "data": {"overall": {"state": "degraded"}}})
        await broadcaster.broadcast({"type": "detection", "data": {"frigate_event": "x"}})
        frame = await asyncio.wait_for(response.body_iterator.__anext__(), 1)
        assert _frame(frame) == {"type": "public_history_changed"}
    finally:
        await response.body_iterator.aclose()


@pytest.mark.asyncio
async def test_the_status_endpoint_is_for_the_owner(configured_secrets, monkeypatch):
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/status")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["jobs_summary"] == {"running": 0, "queued": 0, "progress": None}
    assert body["model"]["revision"]
    assert MQTT_SECRET not in response.text
    assert FRIGATE_SECRET not in response.text


@pytest.mark.asyncio
async def test_a_guest_is_refused_the_status_endpoint(monkeypatch):
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.public_access, "enabled", True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/status")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_a_stream_the_broadcaster_drops_for_backpressure_is_closed_so_the_page_reconnects(monkeypatch):
    monkeypatch.setattr(settings.system, "broadcaster_max_queue_size", 1)
    monkeypatch.setattr(settings.system, "broadcaster_max_consecutive_full", 1)
    response = await sse_endpoint(_stream_request(), StreamAuth(AuthContext(AuthLevel.OWNER), None))
    try:
        assert _frame(await response.body_iterator.__anext__())["type"] == "connected"
        assert _frame(await asyncio.wait_for(response.body_iterator.__anext__(), 10))["type"] == "status"
        # The page stops reading: the queue fills and the broadcaster gives up on this subscriber.
        await broadcaster.broadcast({"type": "detection_updated", "data": {"frigate_event": "a"}})
        await broadcaster.broadcast({"type": "detection_updated", "data": {"frigate_event": "b"}})
        await broadcaster.broadcast({"type": "detection_updated", "data": {"frigate_event": "c"}})
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(response.body_iterator.__anext__(), 2)
    finally:
        await response.body_iterator.aclose()
