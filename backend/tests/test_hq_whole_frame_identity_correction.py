"""An HQ crop consensus corrects a name read from one whole frame, and the photo follows it."""

import sys
from datetime import datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from app.config import settings
from app.database import get_db
from app.models.classification_evidence import ClassificationEvidence
from app.repositories.detection_repository import Detection, DetectionRepository
from app.services import detection_service as detection_module
from app.services import high_quality_snapshot_service as hq_module
from app.services import media_cache as media_cache_module
from app.services import model_manager as model_manager_module
from app.services import notification_orchestrator as notification_module

# Detection 1564's capture time. Each test seeds its own time, so species counts read one visit.
CAPTURED_AT = datetime(2026, 11, 2, 12, 58, 5, 740560)
WHOLE_FRAME_INPUT = ClassificationEvidence(source="frigate_recording_frame", is_cropped=False)
FRAME = (2560, 1440)


def _jpeg(color: str, size: tuple[int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color).save(output, format="JPEG")
    return output.getvalue()


def _crop(name, frame_index, score, confidence, left, top, color):
    return {
        "candidate_id": name,
        "source_mode": "model_crop",
        "clip_variant": "recording",
        "frame_index": frame_index,
        "frame_offset_seconds": frame_index / 29.97,
        "crop_box": [left, top, left + 160, top + 160],
        "detector_box": [left + 30, top + 40, left + 130, top + 120],
        "crop_confidence": confidence,
        "crop_strategy": "detector_supported",
        "classifier_label": "Columba palumbus",
        "classifier_score": score,
        "classifier_index": 2610,
        "ranking_score": score - 0.015,
        "frame_width": FRAME[0],
        "frame_height": FRAME[1],
        "image_width": 160,
        "image_height": 160,
        "image_bytes": _jpeg(color, (160, 160)),
        "snapshot_source": "hq_candidate_model_crop",
    }


def _whole(name, frame_index, score, color):
    return {
        "candidate_id": name,
        "source_mode": "full_frame",
        "clip_variant": "recording",
        "frame_index": frame_index,
        "frame_offset_seconds": frame_index / 29.97,
        "crop_box": None,
        "crop_strategy": "detector_supported",
        "classifier_label": "Pica pica",
        "classifier_score": score,
        "classifier_index": 3775,
        "ranking_score": score + 0.04,
        "frame_width": FRAME[0],
        "frame_height": FRAME[1],
        "image_width": FRAME[0],
        "image_height": FRAME[1],
        "image_bytes": _jpeg(color, (64, 36)),
        "snapshot_source": "hq_candidate_full_frame",
    }


def _visit_1564():
    """Detection 1564's scored candidates: pigeon crops in frames 255 and 510, magpie whole frames."""
    return [
        _crop("crop-f510-c1", 510, 0.977, 0.35, 1996, 1168, "gray"),
        _crop("crop-f510", 510, 0.957, 0.45, 1959, 1352, "silver"),
        _crop("crop-f255", 255, 0.942, 0.85, 1595, 1218, "slategray"),
        _crop("crop-f255-c1", 255, 0.854, 0.80, 1957, 1352, "dimgray"),
        _whole("whole-f765", 765, 0.768, "black"),
        _whole("whole-f510", 510, 0.726, "navy"),
        _whole("whole-f255", 255, 0.462, "maroon"),
    ]


@pytest.fixture
def media(tmp_path, monkeypatch):
    base = tmp_path / "media_cache"
    for name in ("snapshots", "clips", "previews"):
        (base / name).mkdir(parents=True)
    monkeypatch.setattr(media_cache_module, "CACHE_BASE_DIR", base)
    monkeypatch.setattr(media_cache_module, "SNAPSHOTS_DIR", base / "snapshots")
    monkeypatch.setattr(media_cache_module, "CLIPS_DIR", base / "clips")
    monkeypatch.setattr(media_cache_module, "PREVIEWS_DIR", base / "previews")
    cache = media_cache_module.MediaCacheService()
    monkeypatch.setattr(hq_module, "media_cache", cache)
    return cache


@pytest.fixture
def downstream(monkeypatch):
    """The canonical write path runs for real; only its external services are observed."""
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True)
    monkeypatch.setattr(settings.media_cache, "automatic_multi_bird_scan", False)
    monkeypatch.setattr(settings.classification, "threshold", 0.7)
    monkeypatch.setattr(settings.classification, "blocked_labels", [])
    monkeypatch.setattr(settings.classification, "blocked_species", [])
    monkeypatch.setattr(settings.classification, "display_common_names", True)
    monkeypatch.setattr(sys.modules["app.services.classifier_service"], "_classifier_instance", SimpleNamespace())
    monkeypatch.setattr(
        model_manager_module.model_manager,
        "get_active_model_spec",
        lambda: {"model_id": "dinov2_b14_inat21_metadata_336", "recommended_threshold": 0.65},
    )
    monkeypatch.setattr(
        detection_module.taxonomy_service,
        "get_names",
        AsyncMock(
            side_effect=lambda name, db=None: {
                "Columba palumbus": {
                    "scientific_name": "Columba palumbus",
                    "common_name": "Common Wood-Pigeon",
                    "taxa_id": 3048,
                },
            }.get(name, {"scientific_name": name, "common_name": None, "taxa_id": None})
        ),
    )
    from app.services.archive_service import archive_service
    from app.services.audio.audio_service import audio_service

    monkeypatch.setattr(audio_service, "correlate_species", AsyncMock(return_value=(False, None, None)))
    monkeypatch.setattr(archive_service, "refresh_photograph", AsyncMock())
    sse = AsyncMock()
    monkeypatch.setattr(detection_module.broadcaster, "broadcast", sse)
    birdweather = AsyncMock(return_value=True)
    monkeypatch.setattr(detection_module.birdweather_service, "report_detection", birdweather)
    notify = AsyncMock()
    monkeypatch.setattr(notification_module.NotificationOrchestrator, "handle_notifications", notify)
    monkeypatch.setattr(notification_module.notification_service, "send_notification", notify, raising=False)
    return SimpleNamespace(sse=sse, birdweather=birdweather, notify=notify)


def _hq_service(monkeypatch, raw):
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(service, "_load_event_data_for_crop", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "_persist_event_hints", AsyncMock())
    monkeypatch.setattr(service, "_load_preferred_frame_indices", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_load_final_frigate_snapshot_candidates", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_extract_snapshot_candidate_payloads_from_clip_path", lambda *args, **kwargs: raw)
    monkeypatch.setattr(service, "_score_snapshot_candidate", AsyncMock(side_effect=lambda item: dict(item)))
    monkeypatch.setattr(hq_module, "image_quality_score", lambda image: 0.8)
    return service


async def _seed(
    event_id,
    *,
    captured_at=CAPTURED_AT - timedelta(days=1),
    manual_tagged=False,
    classification_input=WHOLE_FRAME_INPUT,
    owner_choice=False,
    hidden=False,
):
    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.create(
            Detection(
                detection_time=captured_at,
                detection_index=3775,
                score=0.7245,
                display_name="Eurasian Magpie",
                category_name="Pica pica",
                scientific_name="Pica pica",
                common_name="Eurasian Magpie",
                frigate_event=event_id,
                camera_name="greenhousecam",
                manual_tagged=manual_tagged,
                is_hidden=hidden,
                classification_input=classification_input,
            )
        )
        if owner_choice:
            await repo.confirm_manual_species_tag(frigate_event=event_id)
        await db.commit()


async def _detection(event_id):
    async with get_db() as db:
        repo = DetectionRepository(db)
        return await repo.get_by_frigate_event(event_id), await repo.list_snapshot_candidates(event_id)


def _clip(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"clip-bytes")
    return path


@pytest.mark.asyncio
@pytest.mark.parametrize("whole_frame_ranks_first", [False, True])
async def test_hq_renames_detection_1564_from_whole_frame_magpie_to_pigeon_crop_consensus(
    tmp_path, monkeypatch, media, downstream, whole_frame_ranks_first
):
    event_id = f"1793624285.74056-6j3htl-{whole_frame_ranks_first}"
    captured_at = CAPTURED_AT + timedelta(minutes=10 * whole_frame_ranks_first)
    await _seed(event_id, captured_at=captured_at)
    raw = _visit_1564()
    if whole_frame_ranks_first:
        # The name is corrected before the photo is chosen, so a magpie whole frame that
        # outranks every crop cannot be shown under the pigeon's name.
        raw = [{**item, "ranking_score": 0.995} if item["candidate_id"] == "whole-f510" else item for item in raw]
    service = _hq_service(monkeypatch, raw)

    outcome = await service.replace_from_clip_path(event_id, _clip(tmp_path), clip_variant="recording")

    detection, rows = await _detection(event_id)
    assert outcome == "bird_crop_replaced"
    assert (detection.display_name, detection.category_name, detection.scientific_name) == (
        "Common Wood-Pigeon",
        "Columba palumbus",
        "Columba palumbus",
    )
    assert detection.score == pytest.approx(0.977)
    assert detection.classification_input == ClassificationEvidence(
        source="hq_candidate_model_crop", is_cropped=True, supporting_frames=2
    )
    # The first classification stays on record as the whole-frame read it was.
    assert detection.initial_classification_input.source == "frigate_recording_frame"
    assert detection.manual_tagged is False
    # The photo and the name agree: a pigeon crop is shown, not a magpie whole frame.
    selected = [row for row in rows if row["selected"]]
    assert [row["source_mode"] for row in selected] == ["model_crop"]
    assert selected[0]["classifier_label"] == "Columba palumbus"
    assert (await media.get_snapshot_metadata(event_id))["source"] == "hq_candidate_model_crop"
    # Downstream: one live update with the new name, no new alert, no second BirdWeather sighting.
    updates = [
        call.args[0]["data"] for call in downstream.sse.await_args_list if call.args[0]["type"] == "detection_updated"
    ]
    assert len(updates) == 1
    assert updates[0]["category_name"] == "Columba palumbus"
    assert updates[0]["classification_input"]["source"] == "hq_candidate_model_crop"
    downstream.notify.assert_not_awaited()
    downstream.birdweather.assert_not_awaited()
    async with get_db() as db:
        counts = await DetectionRepository(db).get_daily_species_counts(
            captured_at - timedelta(seconds=1), captured_at + timedelta(seconds=1)
        )
    assert {row["scientific_name"] for row in counts} == {"Columba palumbus"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "manual_tag",
        "owner_choice",
        "hidden_visit",
        "crop_identity",
        "single_frame",
        "below_bar",
        "blocked",
        "out_of_range",
        "unknown_consensus",
    ],
)
async def test_hq_keeps_a_name_the_correction_may_not_replace(tmp_path, monkeypatch, media, downstream, case):
    event_id = f"whole-frame-kept-{case}"
    raw = _visit_1564()
    seed = {}
    if case == "manual_tag":
        seed["manual_tagged"] = True
    elif case == "owner_choice":
        seed["owner_choice"] = True
    elif case == "hidden_visit":
        seed["hidden"] = True
    elif case == "crop_identity":
        seed["classification_input"] = ClassificationEvidence(source="snapshot_model_crop", is_cropped=True)
    elif case == "single_frame":
        raw = [item for item in raw if item["source_mode"] != "model_crop" or item["frame_index"] == 255]
    elif case == "below_bar":
        # Confident enough to be a photo, not enough to rename against the model's 0.65 bar.
        monkeypatch.setattr(settings.classification, "threshold", 0.6)
        raw = [{**item, "classifier_score": 0.62} if item["source_mode"] == "model_crop" else item for item in raw]
    elif case == "blocked":
        monkeypatch.setattr(settings.classification, "blocked_labels", ["Columba palumbus"])
    elif case == "out_of_range":
        from app.services import range_filter as range_module
        from app.services.range_filter_service import range_filter_service

        monkeypatch.setattr(range_filter_service, "active_list", lambda: object())
        monkeypatch.setattr(range_filter_service, "species_id_for", lambda classification: 3048)
        monkeypatch.setattr(range_module, "species_verdict", lambda active_list, species_id: "out_of_range")
    elif case == "unknown_consensus":
        raw = [
            {**item, "classifier_label": "Unknown Bird"} if item["source_mode"] == "model_crop" else item
            for item in raw
        ]
    await _seed(event_id, **seed)
    before, _ = await _detection(event_id)
    service = _hq_service(monkeypatch, raw)

    await service.replace_from_clip_path(event_id, _clip(tmp_path), clip_variant="recording")

    detection, rows = await _detection(event_id)
    assert (detection.category_name, detection.score, detection.classification_input, detection.manual_tagged) == (
        before.category_name,
        before.score,
        before.classification_input,
        before.manual_tagged,
    )
    downstream.notify.assert_not_awaited()
    selected = [row for row in rows if row["selected"]]
    if case in {"manual_tag", "owner_choice", "hidden_visit", "crop_identity", "blocked", "out_of_range"}:
        # A protected name still decides the photo, and so does a whole-frame name whose
        # crops name a species the bird could never be renamed to: the photo choice is
        # exactly what it was before the correction existed.
        assert [row["classifier_label"] for row in selected] == ["Pica pica"]


@pytest.mark.asyncio
async def test_an_evidence_only_scan_never_renames_the_bird(tmp_path, monkeypatch, media, downstream):
    event_id = "whole-frame-evidence-only-scan"
    await _seed(event_id)
    service = _hq_service(monkeypatch, _visit_1564())

    bundle = await service.generate_snapshot_candidates_from_clip_path(
        event_id, _clip(tmp_path), clip_variant="recording"
    )

    detection, _ = await _detection(event_id)
    assert (detection.category_name, detection.classification_input) == ("Pica pica", WHOLE_FRAME_INPUT)
    downstream.sse.assert_not_awaited()
    # The disputed name still does not decide the photo the scan offers.
    assert bundle["selected_candidate"]["classifier_label"] == "Columba palumbus"


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_action", ["hide", "video_identity", "manual_tag", "delete"])
async def test_correction_refuses_when_the_visit_changes_between_read_and_write(
    tmp_path, monkeypatch, media, downstream, owner_action
):
    """The write itself re-checks eligibility, so a change after the service's read is honoured."""
    event_id = f"whole-frame-race-{owner_action}"
    await _seed(event_id)
    changed_input = '{"source":"full_frame","is_cropped":false,"supporting_frames":6}'

    async def change_the_visit(**_kwargs):
        # Runs inside apply_video_result after the detection was read and before the update.
        async with get_db() as db:
            if owner_action == "hide":
                await db.execute("UPDATE detections SET is_hidden = 1 WHERE frigate_event = ?", (event_id,))
            elif owner_action == "video_identity":
                await db.execute(
                    "UPDATE detections SET classification_input_json = ? WHERE frigate_event = ?",
                    (changed_input, event_id),
                )
            elif owner_action == "manual_tag":
                await db.execute("UPDATE detections SET manual_tagged = 1 WHERE frigate_event = ?", (event_id,))
            else:
                await db.execute("DELETE FROM detections WHERE frigate_event = ?", (event_id,))
            await db.commit()
        return False, None, None

    from app.services.audio.audio_service import audio_service

    monkeypatch.setattr(audio_service, "correlate_species", AsyncMock(side_effect=change_the_visit))
    service = _hq_service(monkeypatch, _visit_1564())

    await service.replace_from_clip_path(event_id, _clip(tmp_path), clip_variant="recording")

    async with get_db() as db:
        async with db.execute(
            "SELECT category_name, score, classification_input_json FROM detections WHERE frigate_event = ?",
            (event_id,),
        ) as cursor:
            row = await cursor.fetchone()
    if owner_action == "delete":
        assert row is None
    else:
        assert (row[0], row[1]) == ("Pica pica", pytest.approx(0.7245))
        if owner_action == "video_identity":
            assert row[2] == changed_input
    assert not [call for call in downstream.sse.await_args_list if call.args[0]["type"] == "detection_updated"]


@pytest.mark.asyncio
async def test_correction_write_guard_is_scoped_to_the_whole_frame_correction():
    """Ordinary automatic writes keep today's behaviour on hidden visits."""
    event_id = "whole-frame-guard-scope"
    await _seed(event_id, hidden=True)
    pigeon = {
        "display_name": "Common Wood-Pigeon",
        "category_name": "Columba palumbus",
        "score": 0.977,
        "detection_index": 2610,
        "scientific_name": "Columba palumbus",
        "common_name": "Common Wood-Pigeon",
        "taxa_id": 3048,
        "audio_confirmed": False,
        "audio_species": None,
        "audio_score": None,
        "manual_override": False,
    }
    async with get_db() as db:
        repo = DetectionRepository(db)
        corrected = await repo.update_primary_classification(
            frigate_event=event_id, whole_frame_correction_of=WHOLE_FRAME_INPUT, **pigeon
        )
        ordinary = await repo.update_primary_classification(frigate_event=event_id, **pigeon)

    assert corrected is False
    assert ordinary is True
