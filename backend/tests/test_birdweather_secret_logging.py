"""BirdWeather credentials in URL paths must never reach application logs."""

import json
import logging
from urllib.parse import quote, unquote

import httpx
import pytest
from structlog.testing import capture_logs

from app.services import birdweather_service as module


def test_birdweather_log_redaction_preserves_unrelated_request_logs():
    record = logging.LogRecord(
        "httpx", logging.INFO, __file__, 1, "HTTP Request: %s %s", ("GET", "https://fixture/stations/public"), None
    )
    assert module._StationCredentialLogFilter().filter(record)
    assert record.args == ("GET", "https://fixture/stations/public")
    assert record.getMessage() == "HTTP Request: GET https://fixture/stations/public"


@pytest.mark.asyncio
@pytest.mark.parametrize("token", ["DUMMY-STATION-CREDENTIAL", "DUMMY station+credential"])
@pytest.mark.parametrize("failure", [401, 403, 429, 500, "timeout", "connection", "unexpected"])
async def test_birdweather_failures_do_not_log_raw_or_encoded_station_tokens(monkeypatch, caplog, token, failure):
    real_client = httpx.AsyncClient

    def answer(request):
        if failure == "timeout":
            raise httpx.ReadTimeout(f"timeout accessing {request.url}", request=request)
        if failure == "connection":
            raise httpx.ConnectError(f"connection failed at {request.url}", request=request)
        if failure == "unexpected":
            raise RuntimeError(f"untrusted failure includes {token}")
        return httpx.Response(failure, json={"error": "fixture failure"})

    def fixture_client(*args, **kwargs):
        return real_client(*args, transport=httpx.MockTransport(answer), **kwargs)

    monkeypatch.setattr(module.httpx, "AsyncClient", fixture_client)
    caplog.set_level(logging.DEBUG, logger="httpx")
    with capture_logs() as records:
        sent = await module.birdweather_service.report_detection("Erithacus rubecula", token=token)
    assert sent is False
    errors = [record for record in records if record.get("log_level") == "error"]
    assert len(errors) == 1
    rendered = json.dumps(records, ensure_ascii=False) + caplog.text
    assert token not in rendered
    assert token not in unquote(rendered)
    assert quote(token, safe="") not in rendered
    assert errors[0]["error_type"]
    if isinstance(failure, int):
        assert errors[0]["status_code"] == failure
        assert caplog.records, "HTTP client logging must be redacted, not silently disabled"


@pytest.mark.asyncio
async def test_successful_birdweather_requests_keep_credentials_out_of_verbose_http_logs(monkeypatch, caplog):
    token = "DUMMY success+credential"
    requests = []
    real_client = httpx.AsyncClient

    def answer(request):
        requests.append(request)
        return httpx.Response(201, json={"success": True})

    monkeypatch.setattr(
        module.httpx,
        "AsyncClient",
        lambda *args, **kwargs: real_client(*args, transport=httpx.MockTransport(answer), **kwargs),
    )
    caplog.set_level(logging.DEBUG, logger="httpx")
    assert await module.birdweather_service.report_detection("Erithacus rubecula", token=token)
    assert len(requests) == 1
    assert requests[0].url.path == f"/api/v1/stations/{token}/detections"
    assert token not in caplog.text
    assert token not in unquote(caplog.text)
    assert quote(token, safe="") not in caplog.text
    assert "201" in caplog.text
