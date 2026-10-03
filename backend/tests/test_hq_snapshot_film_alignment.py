"""Only a known final still can bind a retained crop to a recording moment."""

import hashlib
from io import BytesIO
from unittest.mock import AsyncMock

from PIL import Image
import pytest

from app.config import settings
from app.database import get_db
from app.repositories.detection_repository import Detection, DetectionRepository
from app.services import high_quality_snapshot_service as hq
from app.services import media_cache as cache
from app.services import video_snapshot_service as video
from app.utils.api_datetime import utc_naive_now


@pytest.fixture
def boundary(tmp_path, monkeypatch):
    for field, folder in (("SNAPSHOTS_DIR", "snapshots"), ("CLIPS_DIR", "clips"), ("PREVIEWS_DIR", "previews")):
        directory = tmp_path / folder
        directory.mkdir()
        monkeypatch.setattr(cache, field, directory)
    monkeypatch.setattr(cache, "CACHE_BASE_DIR", tmp_path)
    media = cache.MediaCacheService()
    monkeypatch.setattr(hq, "media_cache", media)
    monkeypatch.setattr(video, "media_cache", media)
    monkeypatch.setattr(settings.media_cache, "enabled", True)
    monkeypatch.setattr(settings.media_cache, "cache_snapshots", True)
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True)
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", False)
    image = Image.new("RGB", (600, 400), "green")
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    monkeypatch.setattr(
        hq.frigate_client, "get_clean_snapshot_with_error", AsyncMock(return_value=(buffer.getvalue(), None))
    )
    monkeypatch.setattr(hq.frigate_client, "get_snapshot_with_error", AsyncMock(return_value=(buffer.getvalue(), None)))
    service = hq.HighQualitySnapshotService()
    monkeypatch.setattr(service, "_bird_crop_model_available", lambda: False)
    monkeypatch.setattr(service, "_expand_hint_box", lambda box, size: box)
    return service, media


def _event(kind="mqtt"):
    event = {"start_time": 100.0, "end_time": 105.0, "camera": "birdcam"}
    if kind == "mqtt":
        event["snapshot"] = {"frame_time": 103.5, "box": [60, 40, 180, 120]}
    else:
        event["data"] = {"snapshot_frame_time": 103.5, "box": [0.1, 0.1, 0.2, 0.2]}
    return event


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["mqtt", "rest"])
async def test_final_clean_snapshot_binds_its_actual_crop_and_encoded_bytes(boundary, kind):
    service, _ = boundary
    candidates = await service._load_final_frigate_snapshot_candidates("film-final", _event(kind))
    crop = next(item for item in candidates if item["source_mode"] == "frigate_hint_crop")
    assert crop["film_alignment"] == {
        "frame_time": 103.5,
        "box": [0.1, 0.1, 0.2, 0.2],
        "image_sha256": hashlib.sha256(crop["image_bytes"]).hexdigest(),
    }
    assert crop["frame_index"] == 0
    assert crop["frame_offset_seconds"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "uncertainty", ["no_moment", "outside_visit", "conflicting_moments", "regular_snapshot", "live"]
)
async def test_uncertain_final_snapshot_has_no_recording_alignment(boundary, monkeypatch, uncertainty):
    service, _ = boundary
    event = _event()
    if uncertainty == "no_moment":
        event["snapshot"].pop("frame_time")
    elif uncertainty == "outside_visit":
        event["snapshot"]["frame_time"] = 110.0
    elif uncertainty == "conflicting_moments":
        event["data"] = {"snapshot_frame_time": 104.0}
    elif uncertainty == "regular_snapshot":
        monkeypatch.setattr(
            hq.frigate_client, "get_clean_snapshot_with_error", AsyncMock(return_value=(None, "missing"))
        )
    else:
        event["end_time"] = None
    candidates = await service._load_final_frigate_snapshot_candidates("film-unknown", event)
    assert all(not item.get("film_alignment") for item in candidates)


@pytest.mark.asyncio
@pytest.mark.parametrize("apply_path", ["no_clip", "clip_bundle", "unknown_video"])
async def test_auto_hq_copies_only_bound_candidate_proof_to_the_selected_photo(
    boundary, monkeypatch, apply_path, tmp_path
):
    service, media = boundary
    event_id = f"film-auto-{apply_path}"
    async with get_db() as db:
        await DetectionRepository(db).create(
            Detection(
                detection_time=utc_naive_now(),
                detection_index=0,
                score=0.9,
                display_name="Dunnock",
                category_name="Prunella modularis",
                frigate_event=event_id,
                camera_name="birdcam",
            )
        )
    candidates = await service._load_final_frigate_snapshot_candidates(event_id, _event())
    selected = next(item for item in candidates if item["source_mode"] == "frigate_hint_crop")
    if apply_path == "unknown_video":
        for item in candidates:
            item.pop("film_alignment", None)
            item.update(clip_variant="event", frame_offset_seconds=0.0)
        old_photo = b"previous aligned photo"
        await media.cache_snapshot(
            event_id,
            old_photo,
            source="hq_candidate_model_crop",
            film_alignment={
                "frame_time": 101.0,
                "box": [0.7, 0.6, 0.1, 0.1],
                "image_sha256": hashlib.sha256(old_photo).hexdigest(),
            },
        )
    for item in candidates:
        item["selected"] = item is selected
    bundle = {"candidates": candidates, "selected_candidate": selected}
    monkeypatch.setattr(service, "_load_event_data_for_crop", AsyncMock(return_value=_event()))
    monkeypatch.setattr(service, "_apply_classification_refinement", AsyncMock(return_value=False))
    from app.services.archive_service import archive_service

    monkeypatch.setattr(archive_service, "refresh_photograph", AsyncMock())
    if apply_path == "no_clip":
        monkeypatch.setattr(service, "_load_event_clip", AsyncMock(return_value=(None, "clip_not_found")))
        monkeypatch.setattr(service, "_load_recording_clip_bytes", AsyncMock(return_value=None))
        monkeypatch.setattr(service, "_score_and_select_snapshot_candidates", AsyncMock(return_value=bundle))
        result = await service._process_event_once(event_id)
    else:
        clip = tmp_path / "clip.mp4"
        clip.write_bytes(b"clip-boundary")
        monkeypatch.setattr(service, "generate_snapshot_candidates_from_clip_path", AsyncMock(return_value=bundle))
        result = await service.replace_from_clip_path(event_id, clip)
    assert result == "bird_crop_replaced"
    alignment = selected.get("film_alignment")
    async with get_db() as db:
        stored = await DetectionRepository(db).list_snapshot_candidates(event_id)
    stored_crop = next(item for item in stored if item["candidate_id"] == selected["candidate_id"])
    assert (await media.get_snapshot_metadata(stored_crop["image_ref"])).get("film_alignment") == alignment
    assert (await media.get_snapshot_metadata(event_id)).get("film_alignment") == alignment
    assert await media.get_snapshot(event_id) == selected["image_bytes"]


@pytest.mark.asyncio
async def test_two_birds_in_one_final_scene_keep_their_own_film_boxes(boundary, monkeypatch):
    service, _ = boundary
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", True)
    monkeypatch.setattr(service, "_bird_crop_model_available", lambda: True)
    monkeypatch.setattr(
        service,
        "_model_crop_images_for_frame",
        lambda image, **kwargs: [
            ("model_crop", image.crop(box), {"box": box}) for box in ((60, 40, 180, 120), (360, 200, 480, 280))
        ],
    )
    candidates = await service._load_final_frigate_snapshot_candidates("film-two-birds", _event())
    crops = [item for item in candidates if item["source_mode"] == "model_crop"]
    assert [item["film_alignment"]["box"] for item in crops] == [[0.1, 0.1, 0.2, 0.2], [0.6, 0.5, 0.2, 0.2]]
    assert all(item["film_alignment"]["frame_time"] == 103.5 for item in crops)
    assert all(
        item["film_alignment"]["image_sha256"] == hashlib.sha256(item["image_bytes"]).hexdigest() for item in crops
    )


@pytest.mark.parametrize("variant", ["event", "recording", "retained_snapshot"])
def test_frame_zero_and_offsets_do_not_establish_an_absolute_snapshot_moment(variant):
    candidate = {
        "clip_variant": variant,
        "frame_index": 0,
        "frame_offset_seconds": 0.0,
        "crop_box": [60, 40, 180, 120],
        "image_bytes": b"photo",
    }
    assert hq.final_snapshot_film_alignment(_event(), candidate, (600, 400)) is None
