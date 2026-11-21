"""Repeats of one diagnostic are kept as one entry with a count, not as N rows."""

import httpx
import pytest

from app.config import settings
from app.main import app
from app.services.error_diagnostics import ErrorDiagnosticsHistory, error_diagnostics_history


def _record(history: ErrorDiagnosticsHistory, **overrides):
    fields = {
        "source": "video",
        "component": "auto_video_classifier",
        "reason_code": "event_http_500",
        "message": "Frigate event precheck failed for 1794744156.868423-xnt7px",
        "severity": "warning",
        "timestamp": "2026-11-15T12:21:24+00:00",
    }
    fields.update(overrides)
    return history.record(**fields)


def test_identical_events_become_one_entry_with_count_first_seen_and_last_seen():
    history = ErrorDiagnosticsHistory()

    first = _record(history, event_id="evt-1", timestamp="2026-11-15T12:21:24+00:00")
    _record(history, event_id="evt-2", timestamp="2026-11-15T12:21:25+00:00")
    last = _record(history, event_id="evt-3", timestamp="2026-11-15T12:21:27+00:00")

    snapshot = history.snapshot()
    assert snapshot["total_events"] == 1
    assert snapshot["total_occurrences"] == 3
    (entry,) = snapshot["events"]
    assert entry["count"] == 3
    assert entry["first_seen"] == "2026-11-15T12:21:24+00:00"
    assert entry["last_seen"] == "2026-11-15T12:21:27+00:00"
    assert entry["timestamp"] == entry["last_seen"]
    assert entry["id"] == first["id"] == last["id"], "the entry keeps one identity as it repeats"
    assert entry["event_id"] == "evt-3", "the newest occurrence supplies the details"


def test_messages_that_differ_only_in_identifiers_share_a_template():
    history = ErrorDiagnosticsHistory()

    _record(history, message="Frigate event precheck failed for 1794744156.868423-xnt7px")
    _record(history, message="Frigate event precheck failed for 1794744149.039949-uqixtw")

    assert history.snapshot()["events"][0]["count"] == 2


@pytest.mark.parametrize(
    "difference",
    [
        {"source": "backfill"},
        {"component": "event_processor"},
        {"reason_code": "event_timeout"},
        {"message": "Clip could not be decoded"},
        {"severity": "error"},
    ],
)
def test_a_different_source_component_reason_message_or_severity_is_a_separate_entry(difference):
    history = ErrorDiagnosticsHistory()

    _record(history)
    _record(history, **difference)

    snapshot = history.snapshot()
    assert snapshot["total_events"] == 2
    assert [event["count"] for event in snapshot["events"]] == [1, 1]


def test_a_repeat_moves_its_entry_to_the_front():
    history = ErrorDiagnosticsHistory()

    _record(history, reason_code="older")
    _record(history, reason_code="newer")
    _record(history, reason_code="older")

    assert [event["reason_code"] for event in history.snapshot()["events"]] == ["older", "newer"]


def test_a_flood_of_one_fault_does_not_push_other_faults_out_of_the_history():
    history = ErrorDiagnosticsHistory(max_events=3)

    _record(history, reason_code="rare_fault")
    for n in range(100):
        _record(history, event_id=f"evt-{n}")

    snapshot = history.snapshot()
    assert {event["reason_code"] for event in snapshot["events"]} == {"rare_fault", "event_http_500"}
    assert snapshot["total_occurrences"] == 101


def test_the_oldest_entry_is_dropped_at_capacity():
    history = ErrorDiagnosticsHistory(max_events=2)

    _record(history, reason_code="first")
    _record(history, reason_code="second")
    _record(history, reason_code="third")

    assert [event["reason_code"] for event in history.snapshot()["events"]] == ["third", "second"]


@pytest.mark.asyncio
async def test_the_api_carries_count_first_seen_and_last_seen():
    original_auth, original_public = settings.auth.enabled, settings.public_access.enabled
    settings.auth.enabled = False
    settings.public_access.enabled = False
    error_diagnostics_history.clear()
    try:
        for n in range(4):
            _record(error_diagnostics_history, event_id=f"evt-{n}", timestamp=f"2026-11-15T12:21:2{n}+00:00")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/diagnostics/errors")
    finally:
        error_diagnostics_history.clear()
        settings.auth.enabled = original_auth
        settings.public_access.enabled = original_public

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total_events"] == 1
    assert payload["total_occurrences"] == 4
    assert payload["events"][0]["count"] == 4
    assert payload["events"][0]["first_seen"] == "2026-11-15T12:21:20+00:00"
    assert payload["events"][0]["last_seen"] == "2026-11-15T12:21:23+00:00"
