"""Video analysis and "Analyse all unknowns" never delete a capture on YA-WAMF's own failures (#1096).

Only Frigate saying that an event or its clip is gone may apply the missing-media policy.
An unexpected worker failure or a local clip read or decode failure is not evidence of
missing media. A maintenance run that names an unknown capture may join it to a
neighbouring visit, which lowers the visit count but keeps the capture.
"""

import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.database import get_db
from app.repositories.bird_observation_repository import BirdObservationRepository
from app.repositories.detection_repository import Detection, DetectionRepository
from app.repositories.visit_repository import VisitRepository
from app.services import auto_video_classifier_service as auto_video_module
from app.services import detection_service as detection_module
from app.services import model_manager as model_manager_module
from app.services import notification_orchestrator as notification_module
from app.services.bird_observation_selection import BirdObservation, BirdObservationSelection

CAMERA = "issue1096cam"
# Each test seeds its own day of the shared suite database, so its counts are its own.
FIRST_DAY = datetime(2025, 3, 14, 6, 0, 0)
ROBIN = {"label": "Erithacus rubecula", "score": 0.92, "index": 1}


@pytest.fixture(autouse=True)
def missing_media_settings(monkeypatch):
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", False)
    monkeypatch.setattr(settings.media_cache, "automatic_multi_bird_scan", False)


@pytest.fixture
def downstream(monkeypatch):
    """The canonical identification write runs for real; only external services are stubbed."""
    monkeypatch.setattr(settings.classification, "threshold", 0.7)
    monkeypatch.setattr(settings.classification, "blocked_labels", [])
    monkeypatch.setattr(settings.classification, "blocked_species", [])
    monkeypatch.setattr(sys.modules["app.services.classifier_service"], "_classifier_instance", SimpleNamespace())
    monkeypatch.setattr(
        model_manager_module.model_manager,
        "get_active_model_spec",
        lambda: {"model_id": "issue1096-model", "recommended_threshold": 0.65},
    )
    monkeypatch.setattr(
        detection_module.taxonomy_service,
        "get_names",
        AsyncMock(side_effect=lambda name, db=None: {"scientific_name": name, "common_name": None, "taxa_id": None}),
    )
    from app.services.archive_service import archive_service
    from app.services.audio.audio_service import audio_service

    monkeypatch.setattr(audio_service, "correlate_species", AsyncMock(return_value=(False, None, None)))
    monkeypatch.setattr(archive_service, "refresh_photograph", AsyncMock())
    monkeypatch.setattr(detection_module.broadcaster, "broadcast", AsyncMock())
    monkeypatch.setattr(detection_module.birdweather_service, "report_detection", AsyncMock(return_value=True))
    monkeypatch.setattr(notification_module.NotificationOrchestrator, "handle_notifications", AsyncMock())
    monkeypatch.setattr(notification_module.notification_service, "send_notification", AsyncMock(), raising=False)


async def _seed_capture(event_id: str, *, name: str, at: datetime) -> None:
    """One visible capture with one counted bird, as an earlier scan left it."""
    async with get_db() as db:
        await DetectionRepository(db).create(
            Detection(
                detection_time=at,
                detection_index=1,
                score=0.4,
                display_name=name,
                category_name=name,
                scientific_name=None if name == "Unknown Bird" else name,
                frigate_event=event_id,
                camera_name=CAMERA,
            )
        )
        await db.commit()
        selection = BirdObservationSelection(
            "event",
            3,
            "whole",
            (BirdObservation(f"{event_id}-bird", (10, 10, 60, 60), 0.9, name, name, 0.4),),
        )
        assert await BirdObservationRepository(db).replace_generated(event_id, selection)


def _captured_at(day: int) -> datetime:
    return FIRST_DAY + timedelta(days=day, hours=2)


async def _history(event_id: str, day: int) -> dict:
    start = FIRST_DAY + timedelta(days=day)
    end = start + timedelta(hours=12)
    async with get_db() as db:
        detection = await DetectionRepository(db).get_by_frigate_event(event_id)
        counts = await BirdObservationRepository(db).count_visible_between(start, end)
        _visits, visit_total = await VisitRepository(db).list_visits(start=start, end=end, camera=CAMERA)
        (birds,) = await (
            await db.execute("SELECT COUNT(*) FROM bird_observations WHERE frigate_event=?", (event_id,))
        ).fetchone()
    return {
        "detection": detection,
        "birds": counts["birds"],
        "captures": counts["captures"],
        "visits": visit_total,
        "bird_rows": birds,
    }


def _maintenance_service(
    classify: AsyncMock, clip: tuple = (True, None, "event", None)
) -> auto_video_module.AutoVideoClassifierService:
    service = auto_video_module.AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._classifier.classify_video_async = classify
    service._load_preferred_clip = AsyncMock(return_value=clip)
    service._persist_video_top_frames = AsyncMock()
    return service


async def _run_maintenance(service, event_id: str, *, fallback_to_snapshot: bool = True) -> AsyncMock:
    """Run one "Analyse all unknowns" job; returns the photo reconciliation it awaited."""
    reconcile = AsyncMock(side_effect=_empty_rescan)
    with (
        patch.object(
            auto_video_module.frigate_client,
            "get_event_with_error",
            new=AsyncMock(return_value=({"has_clip": True}, None)),
        ),
        patch.object(auto_video_module.broadcaster, "broadcast", new=AsyncMock()),
        patch.object(auto_video_module, "replace_video_snapshot", new=AsyncMock(return_value="replaced")),
        patch.object(
            auto_video_module,
            "load_snapshot_classification_input",
            new=AsyncMock(
                return_value=(None, auto_video_module.ClassificationInputProvenance("frigate_snapshot", False))
            ),
        ),
        patch.object(auto_video_module, "reconcile_snapshot_identity", new=reconcile),
        # No copy of the photo: the legacy delete policy would remove the record outright.
        patch.object(auto_video_module.media_cache, "get_snapshot_path", new=AsyncMock(return_value=None)),
    ):
        await service._process_event(
            event_id, CAMERA, skip_delay=True, fallback_to_snapshot=fallback_to_snapshot, source="maintenance"
        )
    return reconcile


# A rescan of the same frame that found no bird: valid clip and frame, no birds.
EMPTY_RESCAN = BirdObservationSelection("event", 3, "whole", ())


async def _empty_rescan(frigate_event: str, **_kwargs) -> str:
    """The photo rescan found no bird this time; it writes its empty result like the real one."""
    async with get_db() as db:
        await BirdObservationRepository(db).replace_generated(frigate_event, EMPTY_RESCAN)
    return "matching_photo_preserved"


def _delete_without_photo(monkeypatch) -> None:
    """The most destructive configuration: legacy auto-delete with the delete policy."""
    monkeypatch.setattr(settings.maintenance, "auto_delete_missing_clips", True)
    monkeypatch.setattr(settings.maintenance, "frigate_missing_behavior", "delete")


def _assert_kept(before: dict, after: dict) -> None:
    assert after["detection"] is not None
    assert after["detection"].is_hidden is False
    assert after["detection"].frigate_status != "missing"
    assert after["bird_rows"] == before["bird_rows"] == 1
    assert after["birds"] == before["birds"] == 1
    assert after["captures"] == before["captures"] == 1


def test_only_errors_that_affirm_frigate_lost_the_media_qualify_for_the_missing_media_policy():
    assert auto_video_module.MISSING_UPSTREAM_MEDIA_ERRORS == {
        "event_not_found",
        "clip_not_retained",
        "clip_unavailable",
    }


@pytest.mark.asyncio
async def test_an_unexpected_video_failure_never_applies_the_missing_media_policy(history_pool, monkeypatch):
    _delete_without_photo(monkeypatch)
    event_id = "issue1096-video-exception"
    await _seed_capture(event_id, name="Unknown Bird", at=_captured_at(0))
    before = await _history(event_id, 0)
    service = _maintenance_service(AsyncMock(side_effect=RuntimeError("worker crashed")))

    await _run_maintenance(service, event_id)

    after = await _history(event_id, 0)
    _assert_kept(before, after)
    assert after["detection"].video_classification_error == "video_exception"


@pytest.mark.asyncio
@pytest.mark.parametrize("day,clip_error", [(4, "clip_decode_failed"), (5, "clip_invalid")])
async def test_a_clip_that_fails_to_read_locally_never_applies_the_missing_media_policy(
    history_pool, monkeypatch, day, clip_error
):
    _delete_without_photo(monkeypatch)
    event_id = f"issue1096-local-{clip_error}"
    await _seed_capture(event_id, name="Unknown Bird", at=_captured_at(day))
    before = await _history(event_id, day)
    classify = AsyncMock()
    service = _maintenance_service(classify, clip=(False, clip_error, "event", None))

    await _run_maintenance(service, event_id, fallback_to_snapshot=False)

    classify.assert_not_awaited()
    after = await _history(event_id, day)
    _assert_kept(before, after)
    assert after["detection"].video_classification_error == clip_error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        "video_exception",
        "clip_decode_failed",
        "clip_invalid",
        "clip_not_found",
        "clip_timeout",
        "clip_http_500",
        "clip_request_error",
    ],
)
async def test_the_missing_media_policy_ignores_errors_that_do_not_affirm_frigate_lost_the_media(
    history_pool, monkeypatch, error
):
    _delete_without_photo(monkeypatch)
    event_id = f"issue1096-policy-{error}"
    await _seed_capture(event_id, name="Unknown Bird", at=_captured_at(1))
    service = auto_video_module.AutoVideoClassifierService()

    with patch.object(auto_video_module.media_cache, "get_snapshot_path", new=AsyncMock(return_value=None)):
        await service._auto_delete_if_missing(event_id, error)

    detection = (await _history(event_id, 1))["detection"]
    assert detection is not None and detection.frigate_status != "missing"


@pytest.mark.asyncio
@pytest.mark.parametrize("error", sorted(auto_video_module.MISSING_UPSTREAM_MEDIA_ERRORS))
async def test_an_error_that_affirms_frigate_lost_the_media_applies_the_policy(history_pool, monkeypatch, error):
    monkeypatch.setattr(settings.maintenance, "auto_delete_missing_clips", True)
    monkeypatch.setattr(settings.maintenance, "frigate_missing_behavior", "mark_missing")
    event_id = f"issue1096-affirmed-{error}"
    await _seed_capture(event_id, name="Unknown Bird", at=_captured_at(1))

    await auto_video_module.AutoVideoClassifierService()._auto_delete_if_missing(event_id, error)

    detection = (await _history(event_id, 1))["detection"]
    assert detection is not None and detection.frigate_status == "missing"


@pytest.mark.asyncio
async def test_a_record_the_owner_added_never_applies_the_missing_media_policy(history_pool, monkeypatch):
    # Frigate never held this record's media, so "no clip" says nothing about Frigate.
    _delete_without_photo(monkeypatch)
    event_id = "manual_issue1096-owner-added"
    await _seed_capture(event_id, name="Unknown Bird", at=_captured_at(1))

    with patch.object(auto_video_module.media_cache, "get_snapshot_path", new=AsyncMock(return_value=None)):
        await auto_video_module.AutoVideoClassifierService()._auto_delete_if_missing(event_id, "clip_unavailable")

    assert (await _history(event_id, 1))["detection"] is not None


@pytest.mark.asyncio
async def test_an_empty_rescan_of_the_same_frame_keeps_the_counted_birds(history_pool):
    event_id = "issue1096-empty-boundary"
    await _seed_capture(event_id, name="Unknown Bird", at=_captured_at(6))
    before = await _history(event_id, 6)

    async with get_db() as db:
        changed = await BirdObservationRepository(db).replace_generated(event_id, EMPTY_RESCAN)

    assert changed is False
    _assert_kept(before, await _history(event_id, 6))


@pytest.mark.asyncio
async def test_an_empty_maintenance_rescan_keeps_every_capture(history_pool):
    event_id = "issue1096-empty-rescan"
    await _seed_capture(event_id, name="Unknown Bird", at=_captured_at(2))
    before = await _history(event_id, 2)
    service = _maintenance_service(AsyncMock(return_value=[]))

    reconcile = await _run_maintenance(service, event_id)

    # The photo rescan really ran for this capture and wrote its empty result.
    reconcile.assert_awaited()
    assert {call.args[0] for call in reconcile.await_args_list} == {event_id}
    _assert_kept(before, await _history(event_id, 2))


@pytest.mark.asyncio
async def test_naming_an_unknown_capture_folds_its_visit_but_keeps_the_capture(history_pool, downstream):
    neighbour = "issue1096-named-neighbour"
    unknown = "issue1096-unknown-renamed"
    await _seed_capture(neighbour, name=ROBIN["label"], at=_captured_at(3) - timedelta(seconds=60))
    await _seed_capture(unknown, name="Unknown Bird", at=_captured_at(3))
    before = await _history(unknown, 3)
    assert before["visits"] == 2
    service = _maintenance_service(AsyncMock(return_value=[ROBIN]))

    await _run_maintenance(service, unknown)

    after = await _history(unknown, 3)
    assert after["detection"] is not None and after["detection"].is_hidden is False
    assert after["detection"].category_name == ROBIN["label"]
    # The renamed capture joins the robin's visit: one fewer visit, the same captures and birds.
    assert after["visits"] == 1
    assert after["captures"] == before["captures"] == 2
    assert after["birds"] == before["birds"] == 2
    assert after["bird_rows"] == 1
