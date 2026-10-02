"""Final Frigate stills must retain the same ownership as video candidates."""

from io import BytesIO
import json

from PIL import Image
import pytest

from app.services import media_cache as cache
from app.services import media_storage_service as storage
from app.services.high_quality_snapshot_service import high_quality_snapshot_service
from test_full_visit_budget_eviction import budget_visit_history as budget_visit_history


@pytest.mark.asyncio
@pytest.mark.parametrize("source_mode", ["full_frame", "model_crop", "frigate_hint_crop", "frigate_region_crop"])
@pytest.mark.parametrize("crop_index", [0, 2])
@pytest.mark.parametrize("metadata_mode", ["current", "legacy", "absent"])
async def test_live_final_candidates_survive_orphan_recovery(
    budget_visit_history, monkeypatch, source_mode, crop_index, metadata_mode
):
    _, media, _ = budget_visit_history
    monkeypatch.setattr(storage.settings.media_cache, "per_species_maximum", 0)
    event_id = "budget-new"
    image_bytes = await media.get_snapshot(event_id)
    with Image.open(BytesIO(image_bytes)) as image:
        payload = high_quality_snapshot_service._build_final_snapshot_candidate_payload(
            event_id, image, source_mode=source_mode, crop_index=crop_index
        )
    image_path = await media.cache_snapshot(payload["image_ref"], payload["image_bytes"], source="snapshot_candidate")
    thumbnail_path = await media.cache_thumbnail(
        payload["thumbnail_ref"], payload["thumbnail_bytes"], source="snapshot_candidate"
    )
    paths = [image_path, thumbnail_path]
    for path, ref in zip(paths, [payload["image_ref"], payload["thumbnail_ref"]]):
        if metadata_mode == "absent":
            path.with_suffix(".jpg.meta.json").unlink()
        elif metadata_mode == "legacy":
            # Earlier versions wrote the generated cache key as owner. Keep those files too.
            path.with_suffix(".jpg.meta.json").write_text(json.dumps({"event_id": ref}))
    result = await storage.MediaStorageService().enforce_limits()
    assert all(path.exists() for path in paths), "live final candidate mistaken for orphaned media"
    assert result["bytes_freed"] == 0
    assert all(cache.cache_file_event_id(path) == event_id for path in paths)
    assert media._media_write_owner(payload["image_ref"]) == event_id
    assert media._media_write_owner(payload["thumbnail_ref"]) == event_id


@pytest.mark.asyncio
async def test_deleted_final_candidate_is_removed_with_its_real_parent(budget_visit_history):
    database, media, _ = budget_visit_history
    from app.repositories.detection_repository import DetectionRepository

    payload = high_quality_snapshot_service._build_final_snapshot_candidate_payload(
        "budget-old", Image.new("RGB", (300, 300)), source_mode="full_frame"
    )
    path = await media.cache_snapshot(payload["image_ref"], payload["image_bytes"])
    async with database() as db:
        await DetectionRepository(db).delete_by_frigate_event("budget-old")
    await storage.MediaStorageService().enforce_limits()
    assert not path.exists()
    assert await media.get_snapshot("budget-new") is not None


@pytest.mark.parametrize("mode,digest", [("frigate_region_crop", "a" * 10), ("retained_snapshot", "b" * 12)])
@pytest.mark.parametrize("part", ["image", "thumb", "thumb_thumb"])
def test_saved_video_and_earlier_photos_belong_to_their_visit(tmp_path, mode, digest, part):
    import json

    from app.services import media_cache as cache

    event_id = "1790873029.831402-46oads"
    moment = "f2__" if mode == "frigate_region_crop" else ""
    ref = f"{event_id}__{mode}__{moment}{digest}__{part}"
    path = tmp_path / f"{ref}.jpg"
    path.write_bytes(b"photo")
    assert cache.media_cache._media_write_owner(ref) == event_id
    assert cache.cache_file_event_id(path) == event_id
    # Older sidecars may themselves have recorded the unresolved candidate key.
    path.with_suffix(".jpg.meta.json").write_text(json.dumps({"event_id": ref}))
    assert cache.cache_file_event_id(path) == event_id
