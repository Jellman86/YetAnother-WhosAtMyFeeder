"""Video analysis and "Analyse all unknowns" never remove a capture from bird history (#1096).

Only Frigate saying that an event or its clip is gone may apply the missing-media policy.
An unexpected failure inside YA-WAMF is not evidence of missing media, and a maintenance
run that names an unknown capture may fold it into a neighbouring visit but keeps it.
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
        "captures": counts["captures"],
        "visits": visit_total,
        "bird_rows": birds,
    }


def _maintenance_service(classify: AsyncMock) -> auto_video_module.AutoVideoClassifierService:
    service = auto_video_module.AutoVideoClassifierService()
    service._classifier = MagicMock()
    service._classifier.classify_video_async = classify
    service._load_preferred_clip = AsyncMock(return_value=(True, None, "event", None))
    service._persist_video_top_frames = AsyncMock()
    return service


async def _run_maintenance(service, event_id: str) -> None:
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
        patch.object(auto_video_module, "reconcile_snapshot_identity", new=AsyncMock(side_effect=_empty_rescan)),
        # No copy of the photo: the legacy delete policy would remove the record outright.
        patch.object(auto_video_module.media_cache, "get_snapshot_path", new=AsyncMock(return_value=None)),
    ):
        await service._process_event(event_id, CAMERA, skip_delay=True, fallback_to_snapshot=True, source="maintenance")


async def _empty_rescan(frigate_event: str, **_kwargs) -> str:
    """The photo rescan found no bird this time; it writes its empty result like the real one."""
    async with get_db() as db:
        await BirdObservationRepository(db).replace_generated(
            frigate_event, BirdObservationSelection(None, None, None, ())
        )
    return "matching_photo_preserved"


@pytest.mark.asyncio
async def test_an_unexpected_video_failure_never_applies_the_missing_media_policy(history_pool, monkeypatch):
    monkeypatch.setattr(settings.maintenance, "auto_delete_missing_clips", True)
    monkeypatch.setattr(settings.maintenance, "frigate_missing_behavior", "delete")
    event_id = "issue1096-video-exception"
    await _seed_capture(event_id, name="Unknown Bird", at=_captured_at(0))
    before = await _history(event_id, 0)
    service = _maintenance_service(AsyncMock(side_effect=RuntimeError("worker crashed")))

    await _run_maintenance(service, event_id)

    after = await _history(event_id, 0)
    assert after["detection"] is not None
    assert after["detection"].is_hidden is False
    assert after["detection"].frigate_status != "missing"
    assert after["detection"].video_classification_error == "video_exception"
    assert after["bird_rows"] == before["bird_rows"] == 1
    assert after["captures"] == before["captures"]


@pytest.mark.asyncio
async def test_the_missing_media_policy_ignores_an_unexpected_video_failure(history_pool, monkeypatch):
    monkeypatch.setattr(settings.maintenance, "auto_delete_missing_clips", True)
    monkeypatch.setattr(settings.maintenance, "frigate_missing_behavior", "delete")
    event_id = "issue1096-policy-direct"
    await _seed_capture(event_id, name="Unknown Bird", at=_captured_at(1))
    service = auto_video_module.AutoVideoClassifierService()

    with patch.object(auto_video_module.media_cache, "get_snapshot_path", new=AsyncMock(return_value=None)):
        await service._auto_delete_if_missing(event_id, "video_exception")

    assert (await _history(event_id, 1))["detection"] is not None


@pytest.mark.asyncio
async def test_an_empty_maintenance_rescan_keeps_every_capture(history_pool):
    event_id = "issue1096-empty-rescan"
    await _seed_capture(event_id, name="Unknown Bird", at=_captured_at(2))
    before = await _history(event_id, 2)
    service = _maintenance_service(AsyncMock(return_value=[]))

    await _run_maintenance(service, event_id)

    after = await _history(event_id, 2)
    assert after["detection"] is not None and after["detection"].is_hidden is False
    assert after["bird_rows"] == before["bird_rows"] == 1
    assert after["captures"] == before["captures"]


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
    # The renamed capture joins the robin's visit: one fewer visit, the same captures.
    assert after["visits"] == 1
    assert after["captures"] == before["captures"] == 2
    assert after["bird_rows"] == 1
