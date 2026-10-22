"""Error handling retains useful status without retaining dummy credentials."""

import asyncio
from datetime import datetime
import json
import logging
from urllib.parse import quote, unquote

import httpx
import pytest
from structlog.testing import capture_logs

from app.config import settings
from app.services import notification_service as module
from app.services import notification_dispatcher as dispatcher_module
from app.services.error_diagnostics import ErrorDiagnosticsHistory


@pytest.mark.asyncio
@pytest.mark.parametrize("photo", [False, True])
@pytest.mark.parametrize("failure", [401, 429, 500, "timeout", "unexpected", "success"])
async def test_telegram_errors_and_verbose_requests_never_log_credentials(monkeypatch, caplog, photo, failure):
    token = "123456:DUMMY-TELEGRAM-CREDENTIAL"
    monkeypatch.setattr(settings.notifications.telegram, "bot_token", token)
    monkeypatch.setattr(settings.notifications.telegram, "chat_id", "fixture-chat")
    monkeypatch.setattr(settings.notifications.telegram, "include_snapshot", photo)
    requests = []

    def answer(request):
        requests.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout(f"Timeout accessing {request.url}", request=request)
        if failure == "unexpected":
            raise RuntimeError(f"Provider failure {token}")
        return httpx.Response(200 if failure == "success" else failure, json={"ok": failure == "success"})

    service = module.NotificationService()
    await service.client.aclose()
    service.client = httpx.AsyncClient(transport=httpx.MockTransport(answer))
    caplog.set_level(logging.DEBUG, logger="httpx")
    try:
        with capture_logs() as logs:
            sent = await service._send_telegram(
                species="Robin",
                confidence=0.9,
                camera="fixture",
                timestamp=datetime(2026, 1, 1),
                snapshot_url="https://example.invalid/photo.jpg",
                snapshot_data=b"fixture" if photo else None,
                lang="en",
            )
        assert sent is (failure == "success")
        assert len(requests) == 1 and token in unquote(str(requests[0].url))
        rendered = json.dumps(logs) + caplog.text
        assert token not in unquote(rendered)
        assert quote(token, safe="") not in rendered
        if isinstance(failure, int):
            error = next(row for row in logs if row.get("log_level") == "error")
            assert error["error_type"] == "HTTPStatusError" and error["status_code"] == failure
        if isinstance(failure, int) or failure == "success":
            assert caplog.records, "Keep useful HTTP logging rather than disabling it"
    finally:
        await service.client.aclose()


@pytest.mark.asyncio
async def test_dispatcher_records_safe_error_type_without_raw_exception_or_traceback(monkeypatch):
    token = "DUMMY-UNSTRUCTURED-EXCEPTION-CREDENTIAL"
    history = ErrorDiagnosticsHistory()
    monkeypatch.setattr(dispatcher_module, "error_diagnostics_history", history)
    dispatcher = dispatcher_module.NotificationDispatcher()
    dispatcher._running = True
    dispatcher._queue = asyncio.Queue()

    async def fail():
        dispatcher._running = False
        raise RuntimeError(f"Provider response contained {token}")

    await dispatcher._queue.put(("fixture-job", fail))
    with capture_logs() as logs:
        await dispatcher._worker_loop(0)
    rendered = json.dumps(logs) + json.dumps(history.snapshot())
    assert token not in rendered
    assert "RuntimeError" in rendered
    assert not any(row.get("exc_info") for row in logs)


def test_diagnostic_history_redacts_nested_keys_known_values_and_credential_urls():
    token = "DUMMY-known+credential"
    history = ErrorDiagnosticsHistory(secret_provider=lambda: [token])
    source = {
        "nested": [{"API-Key": token}],
        "url": "https://user:password@example.invalid/path?access_token=unknown-secret",
        "telegram": "https://api.telegram.org/bot123456:unknown-secret/sendMessage",
        "raw": f"Unlabelled {quote(token, safe='')}",
    }
    history.record(
        source="fixture",
        component="fixture",
        reason_code="fixture_failure",
        message=f"Provider returned {token}",
        context=source,
    )
    source["nested"][0]["API-Key"] = "mutation-should-not-be-retained"
    result = history.snapshot()
    rendered = json.dumps(result)
    for secret in [token, quote(token, safe=""), "unknown-secret", "password", "mutation-should-not-be-retained"]:
        assert secret not in rendered
    assert result["events"][0]["reason_code"] == "fixture_failure"
    assert "REDACTED" in rendered


def test_diagnostic_values_are_bounded_and_do_not_retain_mutable_return_values():
    history = ErrorDiagnosticsHistory()
    original = {"rows": ["x" * 10000] * 1000}
    saved = history.record(
        source="fixture", component="fixture", reason_code="bounded", message="x" * 10000, context=original
    )
    assert len(saved["message"]) <= 2048
    assert len(saved["context"]["rows"]) <= 65
    saved["context"]["rows"][0] = "mutated-return"
    assert "mutated-return" not in json.dumps(history.snapshot())


def test_redaction_is_idempotent_and_keeps_event_metadata_after_nested_truncation():
    from app.utils.diagnostic_redaction import redact_text

    value = "https://api.telegram.org/bot123456:unknown-secret/sendMessage?token=second-secret"
    assert redact_text(redact_text(value)) == redact_text(value)
    history = ErrorDiagnosticsHistory()
    context = {"nested": [["large"] * 64 for _ in range(64)]}
    history.record(
        source="fixture",
        component="fixture",
        reason_code="bounded",
        message="Useful error",
        context=context,
        job_id="fixture-job",
        snapshot_ref="fixture-snapshot",
    )
    event = history.snapshot()["events"][0]
    assert event["job_id"] == "fixture-job" and event["snapshot_ref"] == "fixture-snapshot"


def test_secret_provider_failure_drops_details_instead_of_leaking_or_breaking_the_pipeline():
    def unavailable():
        raise RuntimeError("DUMMY-config-failure")

    history = ErrorDiagnosticsHistory(secret_provider=unavailable)
    history.record(
        source="fixture",
        component="fixture",
        reason_code="safe-failure",
        message="DUMMY-unredacted-detail",
        context={"details": "DUMMY-unredacted-detail"},
    )
    result = history.snapshot()
    assert "DUMMY" not in json.dumps(result)
    assert result["events"][0]["reason_code"] == "safe-failure"


def test_configured_words_cannot_corrupt_machine_severity_or_reason_codes():
    history = ErrorDiagnosticsHistory(secret_provider=lambda: ["error", "fixture", "bounded"])
    history.record(
        source="fixture", component="fixture", reason_code="bounded", severity="error", message="Provider detail error"
    )
    result = history.snapshot()["events"][0]
    assert result["severity"] == "error" and result["reason_code"] == "bounded"
    assert result["source"] == "fixture"
    assert result["message"] == "Provider detail ***REDACTED***"


@pytest.mark.parametrize(
    "name", ["httpcore.connection", "httpcore.http11", "httpcore.http2", "httpcore.proxy", "httpcore.socks"]
)
def test_verbose_transport_children_redact_credentials_without_muting_logs(caplog, name):
    caplog.set_level(logging.DEBUG, logger=name)
    logging.getLogger(name).debug(
        "Request failed at %s", "https://api.telegram.org/bot123456:DUMMY-child-token/sendMessage"
    )
    assert "DUMMY-child-token" not in caplog.text
    assert "REDACTED" in caplog.text and "Request failed" in caplog.text


def test_transport_tracebacks_cannot_append_an_unredacted_bot_token(monkeypatch, caplog):
    token = "123456:DUMMY-TRACEBACK-CREDENTIAL"
    monkeypatch.setattr(settings.notifications.telegram, "bot_token", token)
    caplog.set_level(logging.DEBUG, logger="httpcore.connection")
    try:
        raise RuntimeError(f"Provider failed at https://api.telegram.org/bot{token}/sendMessage")
    except RuntimeError:
        logging.getLogger("httpcore.connection").error("Transport failure", exc_info=True)
    assert token not in caplog.text
    assert "RuntimeError" in caplog.text and "REDACTED" in caplog.text


def test_short_configured_values_cannot_hide_a_stale_credential_url_from_redaction():
    from app.utils.diagnostic_redaction import redact_text

    url = "https://api.telegram.org/bot123456:DUMMY-STALE-CREDENTIAL/sendMessage"
    result = redact_text(url, ("telegram", "REDACTED"))
    assert "DUMMY-STALE-CREDENTIAL" not in result
    assert "***REDACTED***" in result
    assert redact_text(result, ("telegram", "REDACTED")) == result
