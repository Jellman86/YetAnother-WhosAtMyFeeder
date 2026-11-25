import asyncio
import gc
import hashlib
import weakref
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image
import pytest
import pytest_asyncio

from app.auth import AuthContext
from app.config import settings
from app.database import get_db
from app.repositories.detection_repository import Detection, DetectionRepository
from app.routers import proxy
from app.services import high_quality_snapshot_service as hq_module
from app.services import media_cache as cache_module
from app.services.archive_service import archive_service
from app.services.photo_choice_actions import photo_choice_lock
from app.utils.api_datetime import utc_naive_now


def jpeg(color):
    buffer = BytesIO()
    Image.new("RGB", (200, 200), color).save(buffer, "JPEG")
    return buffer.getvalue()


@pytest_asyncio.fixture
async def photos(tmp_path, monkeypatch):
    event = "photo-action-" + uuid4().hex
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True)
    for name, path in (
        ("CACHE_BASE_DIR", tmp_path),
        ("SNAPSHOTS_DIR", tmp_path / "snapshots"),
        ("CLIPS_DIR", tmp_path / "clips"),
        ("PREVIEWS_DIR", tmp_path / "previews"),
    ):
        monkeypatch.setattr(cache_module, name, path)
    cache = cache_module.MediaCacheService()
    monkeypatch.setattr(cache_module, "media_cache", cache)
    monkeypatch.setattr(hq_module, "media_cache", cache)
    choices = []
    for frame, color, score in ((1, "green", 0.8), (2, "red", 0.99)):
        image = jpeg(color)
        identity = f"{event}__model_crop__f{frame}__1234567890"
        choices.append(
            {
                "candidate_id": identity,
                "frame_index": frame,
                "clip_variant": "event",
                "source_mode": "model_crop",
                "crop_box": [0, 0, 200, 200],
                "detector_box": [40, 40, 120, 120],
                "crop_confidence": 0.9,
                "classifier_label": "House Finch",
                "classifier_score": score,
                "ranking_score": score,
                "image_width": 200,
                "image_height": 200,
                "frame_width": 640,
                "frame_height": 480,
                "image_bytes": image,
                "image_ref": identity + "__image",
                "content_sha256": hashlib.sha256(image).hexdigest(),
                "selected": frame == 1,
                "snapshot_source": f"hq_candidate_{frame}",
            }
        )
        await cache.cache_snapshot(identity + "__image", image, source="snapshot_candidate")
    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.create(
            Detection(
                detection_time=utc_naive_now(),
                detection_index=0,
                score=0.9,
                display_name="House Finch",
                category_name="House Finch",
                frigate_event=event,
                camera_name="test",
            )
        )
        await repo.replace_snapshot_candidates(event, choices)
    await cache.cache_snapshot(event, choices[0]["image_bytes"], source=choices[0]["snapshot_source"])
    status = proxy.SnapshotStatusResponse(
        event_id=event,
        cached=True,
        high_quality_event_snapshots_enabled=True,
        high_quality_bird_crop_enabled=True,
        already_hq_bird_crop=True,
        can_generate_hq_bird_crop=True,
    )
    monkeypatch.setattr(proxy, "_build_snapshot_status", AsyncMock(return_value=status))
    monkeypatch.setattr(proxy, "_build_snapshot_candidates_response", AsyncMock(return_value={}))
    monkeypatch.setattr(archive_service, "refresh_photograph", AsyncMock())
    yield SimpleNamespace(event=event, cache=cache, choices=choices, first=choices[0], second=choices[1])
    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event=?", (event,))
        await db.commit()


def apply(photos):
    return proxy.apply_snapshot_candidate(
        proxy.SnapshotApplyRequest(mode="candidate", candidate_id=photos.second["candidate_id"]),
        event_id=photos.event,
        auth=AuthContext("owner"),
    )


def remove(photos):
    return proxy.dismiss_snapshot_candidate(
        MagicMock(),
        proxy.SnapshotDismissRequest(dismissed=True),
        event_id=photos.event,
        candidate_id=photos.second["candidate_id"],
        auth=AuthContext("owner"),
    )


def test_photo_action_lock_is_reclaimed_after_its_last_holder():
    event = "unused-photo-lock-" + uuid4().hex
    lock = photo_choice_lock(event)
    reference = weakref.ref(lock)
    assert photo_choice_lock(event) is lock
    del lock
    gc.collect()
    assert reference() is None


@pytest.mark.asyncio
async def test_photo_actions_on_other_captures_do_not_wait_for_this_capture():
    entered = asyncio.Event()

    async def other_capture():
        async with photo_choice_lock("independent-photo-" + uuid4().hex):
            entered.set()

    async with photo_choice_lock("busy-photo-" + uuid4().hex):
        task = asyncio.create_task(other_capture())
        try:
            await asyncio.wait_for(entered.wait(), 2)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelling_a_waiting_photo_action_keeps_the_choice_and_releases_its_waiter(photos):
    async with photo_choice_lock(photos.event):
        applying = asyncio.create_task(apply(photos))
        await asyncio.sleep(0)
        applying.cancel()
        result = (await asyncio.gather(applying, return_exceptions=True))[0]
        assert isinstance(result, asyncio.CancelledError)
        assert await photos.cache.get_snapshot(photos.event) == photos.first["image_bytes"]
    assert (await asyncio.wait_for(apply(photos), 2)).applied_candidate_id == photos.second["candidate_id"]
    assert await photos.cache.get_snapshot(photos.event) == photos.second["image_bytes"]


@pytest.mark.asyncio
async def test_removal_waits_for_applied_photo_and_rejects_the_current_choice(photos, monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()

    async def archive(event):
        entered.set()
        await release.wait()

    monkeypatch.setattr(archive_service, "refresh_photograph", archive)
    applying = asyncio.create_task(apply(photos))
    await asyncio.wait_for(entered.wait(), 2)
    assert await photos.cache.get_snapshot(photos.event) == photos.second["image_bytes"]
    removing = asyncio.create_task(remove(photos))
    try:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(removing), 0.1)
    finally:
        release.set()
        await applying
    result = (await asyncio.gather(removing, return_exceptions=True))[0]
    assert isinstance(result, HTTPException) and result.status_code == 409
    async with get_db() as db:
        current = await DetectionRepository(db).get_selected_snapshot_candidate(photos.event)
        assert current["candidate_id"] == photos.second["candidate_id"] and not current["photo_hidden"]


@pytest.mark.asyncio
async def test_cancelling_archive_refresh_keeps_applied_photo_and_selected_row_consistent(photos, monkeypatch):
    entered = asyncio.Event()

    async def archive(event):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(archive_service, "refresh_photograph", archive)
    applying = asyncio.create_task(apply(photos))
    await asyncio.wait_for(entered.wait(), 2)
    applying.cancel()
    result = (await asyncio.gather(applying, return_exceptions=True))[0]
    assert isinstance(result, asyncio.CancelledError)
    assert await photos.cache.get_snapshot(photos.event) == photos.second["image_bytes"]
    async with get_db() as db:
        current = await DetectionRepository(db).get_selected_snapshot_candidate(photos.event)
        assert current["candidate_id"] == photos.second["candidate_id"]
    with pytest.raises(HTTPException) as rejected:
        await asyncio.wait_for(remove(photos), 2)
    assert rejected.value.status_code == 409


@pytest.mark.asyncio
async def test_apply_waits_for_removal_then_rechecks_the_dismissed_choice(photos, monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()

    async def response(*args):
        entered.set()
        await release.wait()
        return {}

    monkeypatch.setattr(proxy, "_build_snapshot_candidates_response", response)
    removing = asyncio.create_task(remove(photos))
    await asyncio.wait_for(entered.wait(), 2)
    applying = asyncio.create_task(apply(photos))
    try:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(applying), 0.1)
    finally:
        release.set()
        await removing
    result = (await asyncio.gather(applying, return_exceptions=True))[0]
    assert isinstance(result, HTTPException) and result.status_code == 409
    assert await photos.cache.get_snapshot(photos.event) == photos.first["image_bytes"]


@pytest.mark.asyncio
@pytest.mark.parametrize("clip_path", [False, True])
async def test_regeneration_and_removal_share_the_photo_action_boundary(photos, monkeypatch, tmp_path, clip_path):
    service = hq_module.HighQualitySnapshotService()
    monkeypatch.setattr(service, "_score_snapshot_candidate", AsyncMock(side_effect=lambda row: dict(row)))
    monkeypatch.setattr(service, "_load_expected_species_labels", AsyncMock(return_value={"House Finch"}))
    monkeypatch.setattr(service, "_detect_count_candidates", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_recheck_weak_count_candidates", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_load_event_data_for_crop", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "_persist_event_hints", AsyncMock())
    monkeypatch.setattr(service, "_apply_classification_refinement", AsyncMock(return_value=False))
    entered, release = asyncio.Event(), asyncio.Event()

    async def generation(*args, **kwargs):
        bundle = await service._score_and_select_snapshot_candidates(photos.event, photos.choices)
        assert bundle["selected_candidate"]["candidate_id"] == photos.second["candidate_id"]
        entered.set()
        await release.wait()
        return bundle

    monkeypatch.setattr(service, "generate_snapshot_candidates_from_clip_bytes", generation)
    monkeypatch.setattr(service, "generate_snapshot_candidates_from_clip_path", generation)
    monkeypatch.setattr(service, "_load_event_clip", AsyncMock(return_value=(b"clip", None)))
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"clip")
    regeneration = asyncio.create_task(
        service.replace_from_clip_path(photos.event, path)
        if clip_path
        else service._process_event_once(photos.event, manual_override=True)
    )
    await asyncio.wait_for(entered.wait(), 2)
    removing = asyncio.create_task(remove(photos))
    try:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(removing), 0.1)
    finally:
        release.set()
        assert await regeneration == "bird_crop_replaced"
    result = (await asyncio.gather(removing, return_exceptions=True))[0]
    assert isinstance(result, HTTPException) and result.status_code == 409
    assert await photos.cache.get_snapshot(photos.event) == photos.second["image_bytes"]


@pytest.mark.asyncio
async def test_dismissing_as_recorded_photo_option_is_reversible_and_blocks_revert_until_restored(photos, monkeypatch):
    monkeypatch.setattr(proxy, "_build_snapshot_candidates_response", proxy._build_snapshot_candidates_response)
    original_bytes = jpeg("blue")
    monkeypatch.setattr(proxy.frigate_client, "get_snapshot", AsyncMock(return_value=original_bytes))
    request = MagicMock()
    request.url_for.side_effect = lambda name, **kwargs: SimpleNamespace(path=f"/api/{name}/{kwargs['candidate_id']}")
    request.headers = {}
    status = proxy.SnapshotStatusResponse(
        event_id=photos.event,
        cached=True,
        source=photos.first["snapshot_source"],
        high_quality_event_snapshots_enabled=True,
        high_quality_bird_crop_enabled=True,
        already_hq_bird_crop=True,
        can_generate_hq_bird_crop=True,
        original_frigate_snapshot_available=True,
    )
    monkeypatch.setattr(proxy, "_build_snapshot_status", AsyncMock(return_value=status))
    # Restore real response builder (fixture monkeypatched it to return {}).
    monkeypatch.undo()
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True)
    monkeypatch.setattr(cache_module, "media_cache", photos.cache)
    monkeypatch.setattr(hq_module, "media_cache", photos.cache)
    monkeypatch.setattr(proxy, "_build_snapshot_status", AsyncMock(return_value=status))
    monkeypatch.setattr(archive_service, "refresh_photograph", AsyncMock())
    monkeypatch.setattr(proxy.frigate_client, "get_snapshot", AsyncMock(return_value=original_bytes))

    dismissed = await proxy.dismiss_snapshot_candidate(
        request,
        proxy.SnapshotDismissRequest(dismissed=True),
        event_id=photos.event,
        candidate_id="as-recorded",
        auth=AuthContext("owner"),
    )
    assert dismissed.as_recorded_dismissed is True

    # Survives regenerating/replacing candidate rows.
    async with get_db() as db:
        await DetectionRepository(db).replace_snapshot_candidates(photos.event, photos.choices)
    listed = await proxy.get_snapshot_candidates(request, event_id=photos.event, auth=AuthContext("owner"))
    assert listed.as_recorded_dismissed is True

    # Applying revert_original is rejected while as-recorded is dismissed.
    with pytest.raises(HTTPException) as blocked:
        await proxy.apply_snapshot_candidate(
            proxy.SnapshotApplyRequest(mode="revert_original"),
            event_id=photos.event,
            auth=AuthContext("owner"),
        )
    assert blocked.value.status_code == 409

    # Restoring (Undo) makes it available again and allows revert_original.
    restored = await proxy.dismiss_snapshot_candidate(
        request,
        proxy.SnapshotDismissRequest(dismissed=False),
        event_id=photos.event,
        candidate_id="as-recorded",
        auth=AuthContext("owner"),
    )
    assert restored.as_recorded_dismissed is False

    applied = await proxy.apply_snapshot_candidate(
        proxy.SnapshotApplyRequest(mode="revert_original"),
        event_id=photos.event,
        auth=AuthContext("owner"),
    )
    assert applied.status == "applied"
    assert await photos.cache.get_snapshot(photos.event) == original_bytes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "current_source",
    [
        "frigate_snapshot",
        "frigate_snapshot_cropped",
        "frigate_snapshot_uncropped",
        "frigate_snapshot_unverified",
        "manual_upload",
        None,
    ],
)
async def test_dismissing_as_recorded_photo_option_is_rejected_while_it_is_the_current_photo(
    photos, monkeypatch, current_source
):
    if current_source is None:
        async with get_db() as db:
            await DetectionRepository(db).mark_selected_snapshot_candidate(photos.event, None)
    status = proxy.SnapshotStatusResponse(
        event_id=photos.event,
        cached=current_source is not None,
        source=current_source,
        high_quality_event_snapshots_enabled=True,
        high_quality_bird_crop_enabled=True,
        already_hq_bird_crop=False,
        can_generate_hq_bird_crop=True,
        original_frigate_snapshot_available=True,
    )
    monkeypatch.setattr(proxy, "_build_snapshot_status", AsyncMock(return_value=status))

    with pytest.raises(HTTPException) as rejected:
        await proxy.dismiss_snapshot_candidate(
            MagicMock(),
            proxy.SnapshotDismissRequest(dismissed=True),
            event_id=photos.event,
            candidate_id="as-recorded",
            auth=AuthContext("owner"),
        )
    assert rejected.value.status_code == 409

    with pytest.raises(HTTPException) as missing:
        await proxy.dismiss_snapshot_candidate(
            MagicMock(),
            proxy.SnapshotDismissRequest(dismissed=True),
            event_id="nonexistent-event-id",
            candidate_id="as-recorded",
            auth=AuthContext("owner"),
        )
    assert missing.value.status_code == 404


@pytest.mark.asyncio
async def test_revert_original_and_as_recorded_dismissal_share_the_photo_action_boundary(photos, monkeypatch):
    original_bytes = jpeg("blue")
    monkeypatch.setattr(proxy.frigate_client, "get_snapshot", AsyncMock(return_value=original_bytes))
    current_source = {"value": photos.first["snapshot_source"]}

    async def dynamic_status(event_id, *, check_original_frigate_snapshot=True):
        return proxy.SnapshotStatusResponse(
            event_id=event_id,
            cached=True,
            source=current_source["value"],
            high_quality_event_snapshots_enabled=True,
            high_quality_bird_crop_enabled=True,
            already_hq_bird_crop=current_source["value"] != "frigate_snapshot",
            can_generate_hq_bird_crop=True,
            original_frigate_snapshot_available=True,
        )

    monkeypatch.setattr(proxy, "_build_snapshot_status", dynamic_status)
    entered, release = asyncio.Event(), asyncio.Event()

    async def archive(event):
        current_source["value"] = "frigate_snapshot"
        entered.set()
        await release.wait()

    monkeypatch.setattr(archive_service, "refresh_photograph", archive)
    reverting = asyncio.create_task(
        proxy.apply_snapshot_candidate(
            proxy.SnapshotApplyRequest(mode="revert_original"),
            event_id=photos.event,
            auth=AuthContext("owner"),
        )
    )
    await asyncio.wait_for(entered.wait(), 2)
    removing = asyncio.create_task(
        proxy.dismiss_snapshot_candidate(
            MagicMock(),
            proxy.SnapshotDismissRequest(dismissed=True),
            event_id=photos.event,
            candidate_id="as-recorded",
            auth=AuthContext("owner"),
        )
    )
    try:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(removing), 0.1)
    finally:
        release.set()
        await reverting
    result = (await asyncio.gather(removing, return_exceptions=True))[0]
    assert isinstance(result, HTTPException) and result.status_code == 409
