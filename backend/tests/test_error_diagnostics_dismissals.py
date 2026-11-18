"""Dismissing a Health warning hides it for everyone on the install until it happens again."""

from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.main import app
from app.services.error_diagnostics import ErrorDiagnosticsHistory, error_diagnostics_history


def _record(history: ErrorDiagnosticsHistory, *, at: str, reason_code: str = "stage_timeout") -> dict:
    return history.record(
        source="event_pipeline",
        component="event_processor",
        reason_code=reason_code,
        message="Stage classify_snapshot timed out after 30s",
        severity="error",
        timestamp=at,
    )


def _events_by_id(history: ErrorDiagnosticsHistory) -> dict[str, dict]:
    return {event["id"]: event for event in history.snapshot()["events"]}


def test_a_dismissed_entry_is_marked_dismissed_and_kept():
    history = ErrorDiagnosticsHistory()
    entry = _record(history, at="2026-11-18T07:00:00+00:00")

    result = history.dismiss([(entry["id"], entry["last_seen"])], now="2026-11-18T07:05:00+00:00")

    assert result.missing == []
    assert [(item["id"], item["component"], item["reason_code"]) for item in result.dismissed] == [
        (entry["id"], "event_processor", "stage_timeout")
    ]
    assert result.dismissed[0]["dismissed_through"] == "2026-11-18T07:00:00+00:00"
    event = _events_by_id(history)[entry["id"]]
    assert event["dismissed"] is True
    assert event["dismissal"] == {
        "dismissed_through": "2026-11-18T07:00:00+00:00",
        "dismissed_at": "2026-11-18T07:05:00+00:00",
    }
    snapshot = history.snapshot()
    assert snapshot["total_events"] == 1 and snapshot["dismissed_events"] == 1


def test_a_new_occurrence_after_the_dismissal_shows_the_entry_again():
    history = ErrorDiagnosticsHistory()
    entry = _record(history, at="2026-11-18T07:00:00+00:00")
    history.dismiss([(entry["id"], entry["last_seen"])], now="2026-11-18T07:05:00+00:00")

    repeat = _record(history, at="2026-11-18T07:10:00+00:00")

    assert repeat["id"] == entry["id"]
    event = _events_by_id(history)[entry["id"]]
    assert event["dismissed"] is False
    assert event["count"] == 2
    assert history.snapshot()["dismissed_events"] == 0


def test_an_occurrence_the_owner_had_not_seen_yet_is_not_dismissed_with_the_older_ones():
    """The owner dismissed what the page showed; a repeat recorded meanwhile was never seen."""
    history = ErrorDiagnosticsHistory()
    seen = _record(history, at="2026-11-18T07:00:00+00:00")
    _record(history, at="2026-11-18T07:01:00+00:00")

    history.dismiss([(seen["id"], seen["last_seen"])], now="2026-11-18T07:02:00+00:00")

    assert _events_by_id(history)[seen["id"]]["dismissed"] is False


def test_a_different_fault_is_never_hidden_by_another_ones_dismissal():
    history = ErrorDiagnosticsHistory()
    timeout = _record(history, at="2026-11-18T07:00:00+00:00")
    failure = _record(history, at="2026-11-18T07:00:00+00:00", reason_code="stage_failure")

    history.dismiss([(timeout["id"], timeout["last_seen"])], now="2026-11-18T07:05:00+00:00")

    events = _events_by_id(history)
    assert events[timeout["id"]]["dismissed"] is True
    assert events[failure["id"]]["dismissed"] is False


def test_restore_shows_a_dismissed_entry_again():
    history = ErrorDiagnosticsHistory()
    entry = _record(history, at="2026-11-18T07:00:00+00:00")
    history.dismiss([(entry["id"], entry["last_seen"])], now="2026-11-18T07:05:00+00:00")

    assert history.restore([entry["id"], "diag:gone"]) == [entry["id"]]
    assert _events_by_id(history)[entry["id"]]["dismissed"] is False
    assert history.restore([entry["id"]]) == []


def test_an_entry_no_longer_in_the_history_is_reported_missing_not_dismissed():
    history = ErrorDiagnosticsHistory()

    result = history.dismiss([("diag:1:1", "2026-11-18T07:00:00+00:00")], now="2026-11-18T07:05:00+00:00")

    assert result.dismissed == [] and result.missing == ["diag:1:1"]


def test_clear_error_history_removes_dismissals_with_everything_else():
    history = ErrorDiagnosticsHistory()
    entry = _record(history, at="2026-11-18T07:00:00+00:00")
    history.dismiss([(entry["id"], entry["last_seen"])], now="2026-11-18T07:05:00+00:00")

    history.clear()
    fresh = _record(history, at="2026-11-18T07:10:00+00:00")

    assert _events_by_id(history)[fresh["id"]]["dismissed"] is False
    assert history.restore([entry["id"]]) == []


def test_dismissing_and_restoring_move_the_revision_so_other_pages_read_again():
    history = ErrorDiagnosticsHistory()
    entry = _record(history, at="2026-11-18T07:00:00+00:00")
    before = history.revision

    history.dismiss([(entry["id"], entry["last_seen"])], now="2026-11-18T07:05:00+00:00")
    dismissed = history.revision
    history.restore([entry["id"]])

    assert before < dismissed < history.revision


def test_a_dismissal_leaves_with_the_entry_it_covers():
    history = ErrorDiagnosticsHistory(max_events=1)
    entry = _record(history, at="2026-11-18T07:00:00+00:00")
    history.dismiss([(entry["id"], entry["last_seen"])], now="2026-11-18T07:05:00+00:00")

    _record(history, at="2026-11-18T07:06:00+00:00", reason_code="stage_failure")

    assert history.restore([entry["id"]]) == []


@pytest.fixture(autouse=True)
def unavailable_media_sample(monkeypatch):
    monkeypatch.setattr(
        "app.routers.diagnostics.collect_video_sample_diagnostic",
        AsyncMock(return_value={"available": False, "codec_tag": None, "safari_compatible": None, "note": ""}),
    )


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def owner_access():
    original = (settings.auth.enabled, settings.public_access.enabled)
    settings.auth.enabled = False
    settings.public_access.enabled = False
    error_diagnostics_history.clear()
    yield
    error_diagnostics_history.clear()
    settings.auth.enabled, settings.public_access.enabled = original


@pytest.mark.asyncio
async def test_the_owner_dismisses_and_restores_a_warning_through_the_api(client, owner_access):
    entry = _record(error_diagnostics_history, at="2026-11-18T07:00:00+00:00")

    dismissed = await client.post(
        "/api/diagnostics/dismissals", json={"entries": [{"id": entry["id"], "last_seen": entry["last_seen"]}]}
    )
    assert dismissed.status_code == 200, dismissed.text
    body = dismissed.json()
    assert body["missing"] == []
    assert body["dismissed"][0]["id"] == entry["id"]
    assert body["dismissed"][0]["reason_code"] == "stage_timeout"

    errors = (await client.get("/api/diagnostics/errors")).json()
    assert errors["events"][0]["dismissed"] is True and errors["dismissed_events"] == 1

    restored = await client.post("/api/diagnostics/dismissals/restore", json={"ids": [entry["id"]]})
    assert restored.status_code == 200, restored.text
    assert restored.json() == {"restored": [entry["id"]]}
    assert (await client.get("/api/diagnostics/errors")).json()["events"][0]["dismissed"] is False


@pytest.mark.asyncio
async def test_the_export_bundle_keeps_dismissed_warnings_marked_as_dismissed(client, owner_access):
    entry = _record(error_diagnostics_history, at="2026-11-18T07:00:00+00:00")
    await client.post(
        "/api/diagnostics/dismissals", json={"entries": [{"id": entry["id"], "last_seen": entry["last_seen"]}]}
    )

    bundle = (await client.get("/api/diagnostics/bundle")).json()

    events = bundle["backend_diagnostics"]["events"]
    assert [(event["id"], event["dismissed"]) for event in events] == [(entry["id"], True)]
    assert bundle["summary"]["dismissed_events"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/diagnostics/dismissals", {"entries": [{"id": "diag:1:1", "last_seen": "2026-11-18T07:00:00Z"}]}),
        ("/api/diagnostics/dismissals/restore", {"ids": ["diag:1:1"]}),
    ],
)
async def test_only_the_owner_can_dismiss_or_restore(client, path, body):
    original = (settings.auth.enabled, settings.public_access.enabled)
    settings.auth.enabled = True
    settings.public_access.enabled = True
    try:
        response = await client.post(path, json=body)
    finally:
        settings.auth.enabled, settings.public_access.enabled = original

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_a_dismissal_names_at_least_one_entry_and_a_real_time(client, owner_access):
    assert (await client.post("/api/diagnostics/dismissals", json={"entries": []})).status_code == 422
    bad_time = {"entries": [{"id": "diag:1:1", "last_seen": "yesterday"}]}
    assert (await client.post("/api/diagnostics/dismissals", json=bad_time)).status_code == 422
