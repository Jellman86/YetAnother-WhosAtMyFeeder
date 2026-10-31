"""The range rule inside detection admission, event processing, refinement and the API (#696)."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.repositories.range_filter_repository import RangeFilterRepository
from app.services.detection_service import DetectionService
from app.services.event_processor import EventProcessor
from app.services.range_filter import RangeList
from app.services.range_filter_service import range_filter_service

NOW = datetime(2026, 10, 31, 12, 0)
SPECIES = {"Turdus merula": 4, "Turdus migratorius": 1, "Haemorhous mexicanus": 2, "Erithacus rubecula": 5}
SONOMA = RangeList(
    source="ebird",
    region_code="US-CA-097",
    region_codes=("US-CA-097",),
    region_name="Sonoma County, California, US",
    region_level="county",
    location_key="test",
    fetched_at=NOW,
    region_species_total=2,
    in_range=frozenset({1, 2}),
    known=frozenset({1, 2, 4, 5}),
)


def result(label, score, index):
    return {"label": label, "score": score, "index": index}


@pytest.fixture
def admission(monkeypatch):
    monkeypatch.setattr(settings.classification, "threshold", 0.7)
    monkeypatch.setattr(settings.classification, "min_confidence", 0.4)
    monkeypatch.setattr(settings.classification, "trust_frigate_sublabel", False)
    monkeypatch.setattr(settings.classification, "blocked_labels", [])
    monkeypatch.setattr(settings.classification, "blocked_species", [])
    monkeypatch.setattr(range_filter_service, "active_list", lambda: SONOMA)
    monkeypatch.setattr(range_filter_service, "_list", SONOMA)
    monkeypatch.setattr(range_filter_service, "_merged", None)
    monkeypatch.setattr(range_filter_service, "species_id_for", lambda candidate: SPECIES.get(candidate.get("label")))


@pytest_asyncio.fixture
async def database():
    await init_db()
    async with get_db() as db:
        await db.execute("DELETE FROM range_filter_decisions")
        await db.commit()
    yield
    await close_db()


# ── Selection ────────────────────────────────────────────────────────────────


def test_an_in_range_prediction_is_admitted_unchanged(admission):
    top, reason = DetectionService(MagicMock()).select_usable_classification(
        [result("Turdus migratorius", 0.9, 1)], "evt-in-range"
    )

    assert top["label"] == "Turdus migratorius"
    assert "range_fallback" not in top
    assert reason == "threshold_passed"


def test_an_out_of_range_prediction_falls_back_and_keeps_the_models_first_answer(admission):
    top, reason = DetectionService(MagicMock()).select_usable_classification(
        [result("Turdus merula", 0.91, 4), result("Erithacus rubecula", 0.85, 5), result("Turdus migratorius", 0.8, 1)],
        "evt-fallback",
    )

    assert top["label"] == "Turdus migratorius"
    assert top["score"] == 0.8
    assert reason == "threshold_passed"
    assert top["range_fallback"] == {
        "original_label": "Turdus merula",
        "original_score": 0.91,
        "original_species_id": 4,
        "region_code": "US-CA-097",
    }


def test_an_out_of_range_prediction_without_a_qualifying_alternative_is_set_aside(admission):
    top, reason = DetectionService(MagicMock()).select_usable_classification(
        [result("Turdus merula", 0.91, 4), result("Turdus migratorius", 0.5, 1)], "evt-skip"
    )

    assert top is None
    assert reason == "out_of_range"


def test_a_blocked_alternative_is_never_the_fallback(admission, monkeypatch):
    monkeypatch.setattr(settings.classification, "blocked_labels", ["Turdus migratorius"])

    top, reason = DetectionService(MagicMock()).select_usable_classification(
        [result("Turdus merula", 0.91, 4), result("Turdus migratorius", 0.88, 1)], "evt-blocked"
    )

    assert (top, reason) == (None, "out_of_range")


def test_without_an_active_list_admission_is_exactly_as_before(admission, monkeypatch):
    monkeypatch.setattr(range_filter_service, "active_list", lambda: None)

    top, reason = DetectionService(MagicMock()).select_usable_classification(
        [result("Turdus merula", 0.91, 4)], "evt-open"
    )

    assert top["label"] == "Turdus merula"
    assert reason == "threshold_passed"


def test_an_unknown_bird_catch_all_is_not_range_checked(admission):
    top, reason = DetectionService(MagicMock()).select_usable_classification(
        [result("Turdus merula", 0.55, 4)], "evt-unknown"
    )

    assert top["label"] == "Unknown Bird"
    assert reason == "unknown_catchall"


def test_manual_reclassification_follows_the_same_rule(admission):
    service = DetectionService(MagicMock())

    assert service.select_manual_reclassification([result("Turdus merula", 0.95, 4)], "evt-manual") == (
        None,
        "out_of_range",
    )


# ── Event processing ─────────────────────────────────────────────────────────


def _processor(results):
    processor = EventProcessor(MagicMock())
    processor._classify_snapshot = AsyncMock(  # type: ignore[method-assign]
        return_value=(results, b"img", "frigate_snapshot_cropped")
    )
    processor._gather_context_data = AsyncMock(  # type: ignore[method-assign]
        return_value={"audio_match": None, "weather_data": {}}
    )
    processor._correlate_audio = AsyncMock(side_effect=lambda top, *args, **kwargs: top)  # type: ignore[method-assign]
    processor._save_detection = AsyncMock(return_value=(True, True))  # type: ignore[method-assign]
    processor._enqueue_notification_flow = AsyncMock()  # type: ignore[method-assign]
    return processor


def _payload(event_id: str) -> bytes:
    return (
        b'{"type":"new","after":{"id":"'
        + event_id.encode()
        + b'","label":"bird","camera":"feeder","start_time":1700000000}}'
    )


@pytest.mark.asyncio
async def test_an_out_of_range_live_detection_is_saved_as_the_in_range_alternative(admission, database):
    processor = _processor([result("Turdus merula", 0.91, 4), result("Turdus migratorius", 0.8, 1)])

    await processor.process_mqtt_message(_payload("evt-live-fallback"))

    processor._save_detection.assert_awaited_once()
    saved = processor._save_detection.await_args.args[1]
    assert saved["label"] == "Turdus migratorius"
    assert saved["range_fallback"]["original_label"] == "Turdus merula"


@pytest.mark.asyncio
async def test_an_out_of_range_live_detection_is_skipped_with_a_visible_reason(admission, database):
    processor = _processor([result("Turdus merula", 0.91, 4)])

    await processor.process_mqtt_message(_payload("evt-live-skip"))

    processor._save_detection.assert_not_called()
    assert processor.get_status()["drop_reasons"]["filter_out_of_range"] == 1
    async with get_db() as db:
        decision = await RangeFilterRepository(db).get_decision("evt-live-skip")
    assert decision is not None
    assert (decision.outcome, decision.original_label, decision.camera) == ("skipped", "Turdus merula", "feeder")
    assert decision.region_code == "US-CA-097"


# ── Refinement ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_out_of_range_refinement_never_replaces_the_identification(admission, database):
    existing = MagicMock(manual_tagged=False, display_name="American Robin", score=0.8)
    repo = MagicMock()
    repo.get_by_frigate_event = AsyncMock(return_value=existing)
    repo.update_video_classification = AsyncMock()
    repo.update_primary_classification = AsyncMock()
    service = DetectionService(MagicMock())
    service.is_known_nonbird = AsyncMock(return_value=False)  # type: ignore[method-assign]
    service._is_blocked_with_taxonomy = AsyncMock(return_value=False)  # type: ignore[method-assign]

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("app.services.detection_service.DetectionRepository", lambda db: repo)
        applied = await service.apply_video_result(
            frigate_event="evt-video", video_label="Turdus merula", video_score=0.99, video_index=4
        )

    assert applied is False
    repo.update_video_classification.assert_awaited_once()
    repo.update_primary_classification.assert_not_called()


# ── API ──────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client(monkeypatch):
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.mark.asyncio
async def test_skips_and_fallback_evidence_are_readable_by_the_owner_only(admission, database, client, monkeypatch):
    await range_filter_service.record_decision(
        frigate_event="evt-api-skip",
        outcome="skipped",
        original_label="Turdus merula",
        original_score=0.91,
        original_species_id=4,
        chosen_label=None,
        chosen_score=None,
        region_code="US-CA-097",
        camera="feeder",
        detected_at=NOW - timedelta(minutes=5),
    )
    await range_filter_service.record_decision(
        frigate_event="evt-api-fallback",
        outcome="fallback",
        original_label="Turdus merula",
        original_score=0.91,
        original_species_id=4,
        chosen_label="Turdus migratorius",
        chosen_score=0.8,
        region_code="US-CA-097",
        camera="feeder",
        detected_at=NOW,
    )

    skips = (await client.get("/api/range-filter/skips")).json()["items"]
    fallback = (await client.get("/api/range-filter/decisions/evt-api-fallback")).json()["decision"]
    nothing = (await client.get("/api/range-filter/decisions/evt-unchanged")).json()["decision"]

    assert [item["frigate_event"] for item in skips] == ["evt-api-skip"]
    assert skips[0]["label"] == "Turdus merula"
    assert fallback["outcome"] == "fallback"
    assert (fallback["original_label"], fallback["chosen_label"]) == ("Turdus merula", "Turdus migratorius")
    assert nothing is None

    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.public_access, "enabled", True)
    for path in ("/api/range-filter/status", "/api/range-filter/skips", "/api/range-filter/preview"):
        assert (await client.get(path)).status_code in {401, 403}


@pytest.mark.asyncio
async def test_status_names_a_missing_location_without_claiming_to_filter(database, client, monkeypatch):
    monkeypatch.setattr(settings.classification, "range_filter_enabled", True)
    monkeypatch.setattr(settings.location, "latitude", None)
    monkeypatch.setattr(settings.location, "longitude", None)
    monkeypatch.setattr(settings.location, "country", None)

    response = await client.get("/api/range-filter/status")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert (payload["enabled"], payload["filtering"], payload["reason"]) == (True, False, "needs_location")
    assert payload["location_precision"] == "none"
    assert payload["source"] == "ebird"


@pytest.mark.asyncio
async def test_refresh_without_a_key_names_the_missing_key(database, client, monkeypatch):
    monkeypatch.setattr(settings.location, "latitude", 38.31211)
    monkeypatch.setattr(settings.location, "longitude", -122.70442)
    monkeypatch.setattr(settings.ebird, "api_key", None)

    payload = (await client.post("/api/range-filter/refresh")).json()

    assert (payload["filtering"], payload["reason"]) == (False, "needs_ebird_key")


@pytest.mark.asyncio
async def test_settings_round_trip_the_range_filter_switch_and_region_level(database, client, monkeypatch):
    monkeypatch.setattr(settings.classification, "range_filter_enabled", False)
    monkeypatch.setattr(settings.classification, "range_filter_region_level", "county")
    before = (await client.get("/api/settings")).json()
    assert (before["range_filter_enabled"], before["range_filter_region_level"]) == (False, "county")

    response = await client.post(
        "/api/settings",
        json={
            "frigate_url": before["frigate_url"],
            "mqtt_server": before["mqtt_server"],
            "classification_threshold": before["classification_threshold"],
            "range_filter_enabled": True,
            "range_filter_region_level": "state",
        },
    )
    assert response.status_code == 200, response.text
    after = (await client.get("/api/settings")).json()
    assert (after["range_filter_enabled"], after["range_filter_region_level"]) == (True, "state")

    rejected = await client.post(
        "/api/settings",
        json={
            "frigate_url": before["frigate_url"],
            "mqtt_server": before["mqtt_server"],
            "range_filter_region_level": "planet",
        },
    )
    assert rejected.status_code == 422
