"""Frigate client failures are logged without the credentials a configured Frigate URL can carry."""

import json

import httpx
import pytest
from structlog.testing import capture_logs

from app.config import settings
from app.services.frigate_client import FrigateClient
from app.services.frigate_readiness import FrigateReadinessGate

SECRET_URLS = {
    "userinfo": ("https://feeder-user:hunter2-pass@frigate.example.test:8443", ("feeder-user", "hunter2-pass")),
    "token_query": ("https://frigate.example.test:8443/?token=query-secret-123", ("query-secret-123",)),
    "token_path": ("https://frigate.example.test:8443/proxy/path-secret-456", ("path-secret-456",)),
}
AUTH_TOKEN = "bearer-secret-789"

CALLS = {
    "get_version": lambda client, tmp_path: client.get_version(),
    "get_snapshot_with_error": lambda client, tmp_path: client.get_snapshot_with_error("event_1"),
    "get_clean_snapshot_with_error": lambda client, tmp_path: client.get_clean_snapshot_with_error("event_1"),
    "get_clip_with_error": lambda client, tmp_path: client.get_clip_with_error("event_1"),
    "download_clip_to_file": lambda client, tmp_path: client.download_clip_to_file("event_1", str(tmp_path / "c.mp4")),
    "get_recording_clip_with_error": lambda client, tmp_path: client.get_recording_clip_with_error("birdcam", 1, 2),
    "get_thumbnail": lambda client, tmp_path: client.get_thumbnail("event_1"),
    "get_event": lambda client, tmp_path: client.get_event("event_1"),
    "get_event_with_error": lambda client, tmp_path: client.get_event_with_error("event_1"),
    "set_sublabel": lambda client, tmp_path: client.set_sublabel("event_1", "Robin"),
    "get_config": lambda client, tmp_path: client.get_config(),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["connection", "unexpected"])
@pytest.mark.parametrize("url_shape", sorted(SECRET_URLS))
@pytest.mark.parametrize("call", sorted(CALLS))
async def test_frigate_client_failure_logs_keep_url_credentials_out(monkeypatch, tmp_path, call, url_shape, failure):
    frigate_url, secrets = SECRET_URLS[url_shape]
    monkeypatch.setattr(settings.frigate, "frigate_url", frigate_url)
    monkeypatch.setattr(settings.frigate, "frigate_auth_token", AUTH_TOKEN)

    def refuse(request: httpx.Request) -> httpx.Response:
        # Both kinds of failure can quote the full request URL and headers in their text.
        text = f"cannot reach {request.url} with {request.headers.get('authorization')}"
        if failure == "connection":
            raise httpx.ConnectError(text, request=request)
        raise RuntimeError(text)

    async def frigate_answers() -> bool:
        return True

    client = FrigateClient()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    # One read failing while Frigate answers is the case that logs the error text. A Frigate
    # that is down altogether is reported once, without it (see test_frigate_readiness.py).
    client.readiness = FrigateReadinessGate(frigate_answers)
    try:
        with capture_logs() as records:
            await CALLS[call](client, tmp_path)
    finally:
        await client.close()

    errors = [record for record in records if record.get("log_level") == "error"]
    assert errors, "A Frigate failure must still be logged"
    rendered = json.dumps(records)
    for secret in (*secrets, AUTH_TOKEN):
        assert secret not in rendered
    assert "frigate.example.test:8443" in rendered


async def _snapshot_answering(status_code: int):
    async def frigate_answers() -> bool:
        return True

    client = FrigateClient()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(status_code)))
    client.readiness = FrigateReadinessGate(frigate_answers)
    try:
        with capture_logs() as records:
            result = await client.get_snapshot_with_error("1794988555.071635-1tgeb3")
    finally:
        await client.close()
    return result, records


@pytest.mark.asyncio
async def test_a_snapshot_frigate_does_not_have_is_an_answer_not_a_warning(monkeypatch):
    """Frigate publishes `new` for objects it later discards; asking for their snapshot gets 404.

    The caller decides what a missing snapshot means and tries its fallbacks, so the client
    reporting every 404 as a warning turned one expected event into three to five warnings.
    """
    monkeypatch.setattr(settings.frigate, "frigate_url", "http://frigate.example.test:5000")

    (snapshot, error), records = await _snapshot_answering(404)

    assert (snapshot, error) == (None, "snapshot_not_found")
    assert [record for record in records if record.get("log_level") in {"warning", "error"}] == []


@pytest.mark.asyncio
async def test_a_snapshot_frigate_fails_to_serve_is_still_a_warning(monkeypatch):
    monkeypatch.setattr(settings.frigate, "frigate_url", "http://frigate.example.test:5000")

    (snapshot, error), records = await _snapshot_answering(500)

    assert (snapshot, error) == (None, "snapshot_http_500")
    assert [record["event"] for record in records if record.get("log_level") == "warning"] == [
        "Failed to fetch snapshot"
    ]
