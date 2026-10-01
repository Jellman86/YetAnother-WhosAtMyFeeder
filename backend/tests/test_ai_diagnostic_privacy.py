"""Provider diagnostics retain safe guidance without echoing external error content."""

import asyncio
import base64
import json
from urllib.parse import quote

import httpx
import pytest
from structlog.testing import capture_logs

from app.services.ai_service import AIService


PROVIDERS = ("gemini", "openai", "claude", "openrouter")
SECRET = "fixture-key/+?=private"
ECHOES = (SECRET, quote(SECRET, safe=""), base64.b64encode(SECRET.encode()).decode())


@pytest.fixture
def diagnostic_client(monkeypatch):
    client_class = httpx.AsyncClient

    def install(handler):
        monkeypatch.setattr(
            "app.services.ai_service.httpx.AsyncClient",
            lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs),
        )

    monkeypatch.setattr(AIService, "_test_probe_frame_b64", staticmethod(lambda: "fixture-frame"))
    return install


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("echo", ECHOES)
@pytest.mark.parametrize("status", (401, 403, 429, 500, 503, 418))
async def test_diagnostic_http_failure_omits_raw_and_encoded_credentials(diagnostic_client, provider, echo, status):
    upstream_detail = f"private-provider-detail {echo} https://private.invalid/path?key={echo}"
    diagnostic_client(
        lambda request: httpx.Response(
            status, json={"error": {"message": upstream_detail}}, headers={"Retry-After": "15"}
        )
    )

    with capture_logs() as logs:
        result = await AIService().test_connection(provider, "fixture-model", SECRET)

    assert result.ok is False
    assert result.http_status_hint == (status if status in (429, 503) else (400 if status < 500 else 502))
    assert result.retryable is (status in (429, 500, 503))
    assert result.retry_after_seconds == 15
    assert result.failure_stage == "provider"
    for output in (json.dumps(logs), result.message):
        assert all(value not in output for value in ECHOES)
        assert "private-provider-detail" not in output
        assert "private.invalid" not in output
    assert logs == [
        {
            "event": "ai_connection_test_failed",
            "provider": provider,
            "status": status,
            "error_type": "HTTPStatusError",
            "failure_stage": "provider",
            "log_level": "error",
        }
    ]
    if status in (401, 403):
        assert "Check the key" in result.message
    elif status == 429:
        assert "rate-limited" in result.message
    elif status == 503:
        assert "retry" in result.message


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("echo", ECHOES)
@pytest.mark.parametrize("error_type", (ValueError, httpx.ConnectError))
async def test_diagnostic_unexpected_failure_omits_exception_messages(diagnostic_client, provider, echo, error_type):
    def fail(request):
        raise error_type(f"private-exception-detail https://private.invalid/?key={echo}")

    diagnostic_client(fail)
    with capture_logs() as logs:
        result = await AIService().test_connection(provider, "fixture-model", SECRET)

    assert result.ok is False
    assert result.http_status_hint == 502
    assert result.retryable is True
    assert "try again" in result.message.lower()
    for output in (json.dumps(logs), result.message):
        assert all(value not in output for value in ECHOES)
        assert "private-exception-detail" not in output
        assert "private.invalid" not in output
    assert logs[0]["error_type"] == error_type.__name__
    assert logs[0]["provider"] == provider
    assert logs[0]["status"] is None
    assert "error" not in logs[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize(
    ("detail", "expected_stage"),
    [("too many images", "multi_frame"), ("unsupported_image", "vision")],
)
async def test_diagnostic_http_failure_preserves_stage_without_exposing_body(
    diagnostic_client, provider, detail, expected_stage
):
    diagnostic_client(lambda request: httpx.Response(400, text=f"{detail} {ECHOES[1]}"))
    with capture_logs() as logs:
        result = await AIService().test_connection(provider, "fixture-model", SECRET)

    assert result.failure_stage == expected_stage
    assert result.http_status_hint == 400
    assert result.retryable is False
    assert ECHOES[1] not in json.dumps(logs)
    assert ECHOES[1] not in result.message
    assert logs[0]["failure_stage"] == expected_stage


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", PROVIDERS)
async def test_diagnostic_cancellation_propagates_without_logging(diagnostic_client, provider):
    def cancel(request):
        raise asyncio.CancelledError()

    diagnostic_client(cancel)
    with capture_logs() as logs, pytest.raises(asyncio.CancelledError):
        await AIService().test_connection(provider, "fixture-model", SECRET)
    assert logs == []
