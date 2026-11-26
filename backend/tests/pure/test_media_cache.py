import asyncio
import errno
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.services import media_cache as media_cache_module


def _make_service(tmp_path, monkeypatch):
    cache_base = tmp_path / "media_cache"
    snapshots = cache_base / "snapshots"
    clips = cache_base / "clips"
    previews = cache_base / "previews"
    snapshots.mkdir(parents=True, exist_ok=True)
    clips.mkdir(parents=True, exist_ok=True)
    previews.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(media_cache_module, "CACHE_BASE_DIR", cache_base)
    monkeypatch.setattr(media_cache_module, "SNAPSHOTS_DIR", snapshots)
    monkeypatch.setattr(media_cache_module, "CLIPS_DIR", clips)
    monkeypatch.setattr(media_cache_module, "PREVIEWS_DIR", previews)

    return media_cache_module.MediaCacheService(), snapshots


def _without_detection_history(service, monkeypatch) -> None:
    """Age cleanup's database boundary, for tests about its file rules: no parent is favourited or confirmed."""
    monkeypatch.setattr(service, "_cached_media_visit_rows", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_settle_staged_age_group", AsyncMock(return_value=[]))


@pytest.mark.asyncio
async def test_replace_snapshot_overwrites_cached_snapshot_atomically(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    event_id = "evt_replace"

    original_path = await service.cache_snapshot(event_id, b"old-bytes")
    assert original_path == snapshots / f"{event_id}.jpg"

    replaced_path = await service.replace_snapshot(event_id, b"new-bytes")

    assert replaced_path == original_path
    assert await service.get_snapshot(event_id) == b"new-bytes"
    assert list(snapshots.glob("*.tmp")) == []


@pytest.mark.asyncio
async def test_replace_snapshot_preserves_original_when_swap_fails(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    event_id = "evt_replace_failure"

    original_path = await service.cache_snapshot(event_id, b"old-bytes")
    assert original_path == snapshots / f"{event_id}.jpg"

    original_replace = Path.replace

    def fail_replace(self, target):
        if self.name.endswith(".tmp"):
            raise OSError("swap failed")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_replace)

    replaced_path = await service.replace_snapshot(event_id, b"new-bytes")

    assert replaced_path is None
    assert await service.get_snapshot(event_id) == b"old-bytes"
    assert list(snapshots.glob("*.tmp")) == []


@pytest.mark.asyncio
async def test_failed_owner_choice_sidecar_never_publishes_unprotected_chosen_pixels(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    event_id = "evt-choice-sidecar-failure"
    await service.cache_snapshot(event_id, b"automatic-photo")
    sidecar = snapshots / f"{event_id}.jpg.meta.json"
    original_replace = Path.replace

    def fail_sidecar_swap(self, target):
        if Path(target) == sidecar:
            raise OSError("sidecar disk full")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_sidecar_swap)
    assert await service.replace_snapshot(event_id, b"chosen", manual_selection=True) is None
    monkeypatch.setattr(Path, "replace", original_replace)

    # The choice did not happen, so the next automatic write may still replace the old photo.
    assert await service.get_snapshot(event_id) == b"automatic-photo"
    assert not (await service.get_snapshot_metadata(event_id)).get("manual_selection")


@pytest.mark.asyncio
async def test_failed_owner_choice_image_restores_the_previous_sidecar(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    event_id = "evt-choice-image-failure"
    await service.cache_snapshot(event_id, b"automatic-photo")
    before = (snapshots / f"{event_id}.jpg.meta.json").read_bytes()
    photo = snapshots / f"{event_id}.jpg"
    original_replace = Path.replace

    def fail_photo_swap(self, target):
        if Path(target) == photo:
            raise OSError("photo disk full")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_photo_swap)
    assert await service.replace_snapshot(event_id, b"chosen", manual_selection=True) is None
    monkeypatch.setattr(Path, "replace", original_replace)

    assert await service.get_snapshot(event_id) == b"automatic-photo"
    assert (snapshots / f"{event_id}.jpg.meta.json").read_bytes() == before


@pytest.mark.asyncio
async def test_owner_choice_sidecar_protects_the_new_pixels_before_they_are_published(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    event_id = "evt-choice-order"
    await service.cache_snapshot(event_id, b"automatic-photo")
    photo = snapshots / f"{event_id}.jpg"
    original_replace = Path.replace
    seen_at_publication: list[dict] = []

    def observe_photo_swap(self, target):
        if Path(target) == photo:
            sidecar = media_cache_module.json.loads((snapshots / f"{event_id}.jpg.meta.json").read_text())
            seen_at_publication.append(sidecar)
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", observe_photo_swap)
    assert await service.replace_snapshot(event_id, b"chosen", manual_selection=True, manual_candidate_id="c1")

    # A process that dies at this instant leaves the new pixels already marked as the owner's choice.
    assert seen_at_publication[0]["manual_selection"] is True
    assert seen_at_publication[0]["manual_candidate_id"] == "c1"
    assert seen_at_publication[0]["image_sha256"] == media_cache_module.image_sha256_hex(b"chosen")


@pytest.mark.asyncio
async def test_replace_snapshot_uses_unique_temp_file_per_write(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    event_id = "evt_unique_tmp"

    original_path = await service.cache_snapshot(event_id, b"old-bytes")
    assert original_path == snapshots / f"{event_id}.jpg"

    created_tmp_names: list[str] = []
    original_replace = Path.replace

    def track_replace(self, target):
        created_tmp_names.append(self.name)
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", track_replace)

    replaced_path = await service.replace_snapshot(event_id, b"new-bytes")

    assert replaced_path == original_path
    assert created_tmp_names
    assert created_tmp_names[0] != f"{event_id}.jpg.tmp"
    assert created_tmp_names[0].endswith(".tmp")


@pytest.mark.asyncio
async def test_replace_snapshot_invalidates_cached_thumbnail(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    event_id = "evt_replace_thumbnail"

    original_snapshot = await service.cache_snapshot(event_id, b"old-snapshot")
    thumbnail_path = await service.cache_thumbnail(event_id, b"old-thumbnail")

    assert original_snapshot == snapshots / f"{event_id}.jpg"
    assert thumbnail_path == snapshots / f"{event_id}_thumb.jpg"
    assert await service.get_thumbnail(event_id) == b"old-thumbnail"

    replaced_path = await service.replace_snapshot(event_id, b"new-snapshot")

    assert replaced_path == original_snapshot
    assert await service.get_snapshot(event_id) == b"new-snapshot"
    assert await service.get_thumbnail(event_id) is None
    assert not thumbnail_path.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("paused_step", ["sidecar", "thumbnail"])
async def test_cancelled_snapshot_replacement_finishes_publication_under_the_lock(tmp_path, monkeypatch, paused_step):
    service, _ = _make_service(tmp_path, monkeypatch)
    event_id = "evt-cancelled-choice"
    await service.cache_snapshot(event_id, b"old-snapshot")
    thumbnail = await service.cache_thumbnail(event_id, b"old-thumbnail")
    entered, release = asyncio.Event(), asyncio.Event()
    method_name = "_write_snapshot_metadata" if paused_step == "sidecar" else "delete_thumbnail"
    original = getattr(service, method_name)

    async def pause_publication(*args, **kwargs):
        entered.set()
        await release.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(service, method_name, pause_publication)
    owner = asyncio.create_task(
        service.replace_snapshot(event_id, b"chosen", manual_selection=True, manual_candidate_id="candidate")
    )
    automatic = None
    try:
        await asyncio.wait_for(entered.wait(), 2)
        # The protecting sidecar is written before the chosen pixels are published.
        assert await service.get_snapshot(event_id) == (b"old-snapshot" if paused_step == "sidecar" else b"chosen")
        owner.cancel()
        automatic = asyncio.create_task(service.replace_snapshot(event_id, b"automatic", automatic=True))
        await asyncio.sleep(0)
        owner.cancel()
        assert not owner.done()
        assert service._snapshot_commit_lock(event_id).locked()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await owner
        if automatic is not None:
            await automatic
    assert await service.get_snapshot(event_id) == b"chosen"
    metadata = await service.get_snapshot_metadata(event_id)
    assert metadata["manual_selection"] is True
    assert metadata["manual_candidate_id"] == "candidate"
    assert not thumbnail.exists()
    assert await service.get_thumbnail_metadata(event_id) is None


@pytest.mark.asyncio
async def test_cache_snapshot_invalidates_cached_thumbnail(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    event_id = "evt_cache_thumbnail"

    thumbnail_path = await service.cache_thumbnail(event_id, b"old-thumbnail", source="snapshot_derived")
    assert thumbnail_path == snapshots / f"{event_id}_thumb.jpg"
    assert await service.get_thumbnail(event_id) == b"old-thumbnail"

    snapshot_path = await service.cache_snapshot(event_id, b"new-snapshot")

    assert snapshot_path == snapshots / f"{event_id}.jpg"
    assert await service.get_snapshot(event_id) == b"new-snapshot"
    assert await service.get_thumbnail(event_id) is None
    assert await service.get_thumbnail_metadata(event_id) is None
    assert not thumbnail_path.exists()


@pytest.mark.asyncio
async def test_thumbnail_metadata_tracks_source_and_is_removed_with_thumbnail(tmp_path, monkeypatch):
    service, _snapshots = _make_service(tmp_path, monkeypatch)
    event_id = "evt_thumbnail_metadata"

    await service.cache_thumbnail(event_id, b"thumbnail-bytes", source="snapshot_derived")
    cached_metadata = await service.get_thumbnail_metadata(event_id)

    assert cached_metadata is not None
    assert cached_metadata["source"] == "snapshot_derived"
    assert cached_metadata["updated_at"].endswith("Z")

    assert await service.delete_thumbnail(event_id) is True
    assert await service.get_thumbnail(event_id) is None
    assert await service.get_thumbnail_metadata(event_id) is None


@pytest.mark.asyncio
async def test_snapshot_metadata_tracks_source_and_is_removed_with_snapshot(tmp_path, monkeypatch):
    service, _snapshots = _make_service(tmp_path, monkeypatch)
    event_id = "evt_snapshot_metadata"

    await service.cache_snapshot(event_id, b"frigate-bytes")
    cached_metadata = await service.get_snapshot_metadata(event_id)

    assert cached_metadata is not None
    assert cached_metadata["source"] == "frigate_snapshot"
    assert cached_metadata["updated_at"].endswith("Z")

    await service.replace_snapshot(event_id, b"hq-bytes", source="high_quality_bird_crop")
    replaced_metadata = await service.get_snapshot_metadata(event_id)

    assert replaced_metadata is not None
    assert replaced_metadata["source"] == "high_quality_bird_crop"

    await service.cache_thumbnail(event_id, b"thumbnail-bytes", source="snapshot_derived")
    assert await service.get_thumbnail(event_id) == b"thumbnail-bytes"

    assert await service.delete_snapshot(event_id) is True
    assert await service.get_snapshot(event_id) is None
    assert await service.get_snapshot_metadata(event_id) is None
    assert await service.get_thumbnail(event_id) is None
    assert await service.get_thumbnail_metadata(event_id) is None


@pytest.mark.asyncio
async def test_snapshot_metadata_preserves_event_hints_across_replacements(tmp_path, monkeypatch):
    service, _snapshots = _make_service(tmp_path, monkeypatch)
    event_id = "evt_ephemeral_hints"
    event_hints = {
        "start_time": 100.0,
        "end_time": 105.0,
        "data": {"box": [10, 20, 30, 40]},
        "position_changes": 0,
        "has_snapshot": False,
        "has_clip": False,
    }

    await service.cache_snapshot(
        event_id,
        b"frigate-bytes",
        source="frigate_snapshot_cropped",
        event_hints=event_hints,
    )
    await service.replace_snapshot(event_id, b"hq-bytes", source="high_quality_bird_crop")

    metadata = await service.get_snapshot_metadata(event_id)
    assert metadata is not None
    assert metadata["source"] == "high_quality_bird_crop"
    assert metadata["event_hints"] == event_hints


@pytest.mark.asyncio
async def test_snapshot_event_hints_can_be_refreshed_without_rewriting_image(tmp_path, monkeypatch):
    service, _snapshots = _make_service(tmp_path, monkeypatch)
    event_id = "evt_final_hints"
    await service.cache_snapshot(event_id, b"original", source="frigate_snapshot_cropped")

    updated = await service.update_snapshot_event_hints(
        event_id,
        {"end_time": 105.0, "position_changes": 0, "has_snapshot": False, "has_clip": False},
    )

    assert updated is True
    assert await service.get_snapshot(event_id) == b"original"
    metadata = await service.get_snapshot_metadata(event_id)
    assert metadata is not None
    assert metadata["source"] == "frigate_snapshot_cropped"
    assert metadata["event_hints"]["position_changes"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "refined_source",
    ["high_quality_bird_crop", "hq_candidate_full_frame", "video_evidence_crop", "video_evidence_full_frame"],
)
async def test_late_frigate_snapshot_preserves_refined_photo_and_thumbnail(tmp_path, monkeypatch, refined_source):
    service, _ = _make_service(tmp_path, monkeypatch)
    event_id = "evt-late-frigate"
    await service.replace_snapshot(event_id, b"identified-bird", source=refined_source)
    await service.cache_thumbnail(event_id, b"identified-thumb")
    await service.cache_snapshot(
        event_id,
        b"empty-branch",
        event_hints={"end_time": 105.0},
        recording_alignment={"frame_time": 106.0, "box": [0.1, 0.2, 0.3, 0.4]},
    )
    assert await service.get_snapshot(event_id) == b"identified-bird"
    assert await service.get_thumbnail(event_id) == b"identified-thumb"
    metadata = await service.get_snapshot_metadata(event_id)
    assert metadata["source"] == refined_source
    assert metadata["event_hints"] == {"end_time": 105.0}
    assert "recording_alignment" not in metadata


@pytest.mark.asyncio
async def test_late_frigate_snapshot_recovers_missing_automatic_refined_photo(tmp_path, monkeypatch):
    service, _ = _make_service(tmp_path, monkeypatch)
    path = await service.replace_snapshot("evt-missing-refined", b"old", source="high_quality_bird_crop")
    path.unlink()
    await service.cache_snapshot("evt-missing-refined", b"recovered")
    assert await service.get_snapshot("evt-missing-refined") == b"recovered"
    assert (await service.get_snapshot_metadata("evt-missing-refined"))["source"] == "frigate_snapshot"


@pytest.mark.asyncio
async def test_recording_clip_cache_uses_distinct_key_from_event_clip(tmp_path, monkeypatch):
    service, _snapshots = _make_service(tmp_path, monkeypatch)
    event_id = "evt_recording"
    monkeypatch.setattr(media_cache_module, "_clip_duration_seconds", lambda _path: 30.0)

    clip_path = await service.cache_clip(event_id, b"a" * 600)
    recording_path = await service.cache_recording_clip(event_id, b"b" * 700)

    assert clip_path is not None
    assert recording_path is not None
    assert clip_path.name == f"{event_id}.mp4"
    assert recording_path.name == f"{event_id}_recording.mp4"
    assert clip_path != recording_path
    assert service.get_clip_path(event_id) == clip_path
    assert service.get_recording_clip_path(event_id) == recording_path


@pytest.mark.asyncio
async def test_cache_recording_clip_emits_listener_on_success(tmp_path, monkeypatch):
    service, _snapshots = _make_service(tmp_path, monkeypatch)
    calls: list[str] = []
    monkeypatch.setattr(media_cache_module, "_clip_duration_seconds", lambda _path: 30.0)

    async def listener(event_id: str) -> None:
        calls.append(event_id)

    monkeypatch.setattr(
        media_cache_module,
        "create_background_task",
        lambda coro, name=None: asyncio.create_task(coro),
        raising=False,
    )
    service.register_recording_clip_listener(listener)

    recording_path = await service.cache_recording_clip("evt_listener_success", b"b" * 700)
    await asyncio.sleep(0)

    assert recording_path is not None
    assert calls == ["evt_listener_success"]


@pytest.mark.asyncio
async def test_cache_recording_clip_does_not_emit_on_stub(tmp_path, monkeypatch):
    service, _snapshots = _make_service(tmp_path, monkeypatch)
    calls: list[str] = []

    async def listener(event_id: str) -> None:
        calls.append(event_id)

    service.register_recording_clip_listener(listener)

    recording_path = await service.cache_recording_clip("evt_listener_stub", b"x" * 64)

    assert recording_path is None
    assert calls == []


@pytest.mark.asyncio
async def test_cache_recording_clip_streaming_emits_only_on_validated_size(tmp_path, monkeypatch):
    service, _snapshots = _make_service(tmp_path, monkeypatch)
    calls: list[str] = []

    async def listener(event_id: str) -> None:
        calls.append(event_id)

    service.register_recording_clip_listener(listener)

    async def chunks():
        yield b"x" * 64

    recording_path = await service.cache_recording_clip_streaming("evt_listener_stream_stub", chunks())

    assert recording_path is None
    assert calls == []


@pytest.mark.asyncio
async def test_recording_stream_keeps_longer_existing_clip_when_candidate_is_shorter(tmp_path, monkeypatch):
    service, _snapshots = _make_service(tmp_path, monkeypatch)
    event_id = "evt_keep_longer"
    recording_path = service._recording_clip_path(event_id)
    recording_path.write_bytes(b"a" * 2048)

    monkeypatch.setattr(
        media_cache_module,
        "_clip_duration_seconds",
        lambda path: 30.0 if path.read_bytes().startswith(b"a") else 20.0,
    )

    async def chunks():
        yield b"b" * 2048

    resolved = await service.cache_recording_clip_streaming(event_id, chunks())

    assert resolved == recording_path
    assert recording_path.read_bytes() == b"a" * 2048
    assert list(recording_path.parent.glob("*.tmp.mp4")) == []


@pytest.mark.asyncio
async def test_recording_stream_preserves_existing_clip_when_atomic_swap_fails(tmp_path, monkeypatch):
    service, _snapshots = _make_service(tmp_path, monkeypatch)
    event_id = "evt_atomic_failure"
    recording_path = service._recording_clip_path(event_id)
    recording_path.write_bytes(b"a" * 2048)
    monkeypatch.setattr(
        media_cache_module,
        "_clip_duration_seconds",
        lambda path: 20.0 if path.read_bytes().startswith(b"a") else 30.0,
    )

    def fail_replace(self, target):
        raise OSError("swap failed")

    monkeypatch.setattr(Path, "replace", fail_replace)

    async def chunks():
        yield b"b" * 2048

    resolved = await service.cache_recording_clip_streaming(event_id, chunks())

    assert resolved is None
    assert recording_path.read_bytes() == b"a" * 2048
    assert list(recording_path.parent.glob("*.tmp.mp4")) == []


@pytest.mark.asyncio
async def test_concurrent_recording_commits_cannot_replace_a_longer_clip_with_a_shorter_one(tmp_path, monkeypatch):
    service, _snapshots = _make_service(tmp_path, monkeypatch)
    event_id = "evt_concurrent_upgrade"
    recording_path = service._recording_clip_path(event_id)
    short_replace_started = threading.Event()
    release_short_replace = threading.Event()
    original_replace = Path.replace

    monkeypatch.setattr(
        media_cache_module,
        "_clip_duration_seconds",
        lambda path: 30.0 if path.read_bytes().startswith(b"a") else 20.0,
    )

    def controlled_replace(self: Path, target: Path):
        if self.read_bytes().startswith(b"b"):
            short_replace_started.set()
            assert release_short_replace.wait(timeout=2.0)
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", controlled_replace)

    async def long_chunks():
        yield b"a" * 2048

    async def short_chunks():
        yield b"b" * 2048

    short_task = asyncio.create_task(service.cache_recording_clip_streaming(event_id, short_chunks()))
    assert await asyncio.to_thread(short_replace_started.wait, 2.0)
    long_task = asyncio.create_task(service.cache_recording_clip_streaming(event_id, long_chunks()))
    await asyncio.sleep(0.05)
    assert long_task.done() is False

    release_short_replace.set()
    await asyncio.gather(short_task, long_task)

    assert recording_path.read_bytes() == b"a" * 2048


def test_get_recording_clip_path_retains_usable_partial_recording_and_preview_assets(tmp_path, monkeypatch):
    service, _snapshots = _make_service(tmp_path, monkeypatch)
    event_id = "evt_short_recording"

    recording_path = service._recording_clip_path(event_id)
    preview_sprite_path = service._preview_sprite_path(event_id)
    preview_manifest_path = service._preview_manifest_path(event_id)
    recording_path.write_bytes(b"x" * 2048)
    preview_sprite_path.write_bytes(b"sprite")
    preview_manifest_path.write_text('{"duration":6.0}')

    monkeypatch.setattr(media_cache_module, "_clip_duration_seconds", lambda _path: 6.0)

    resolved = service.get_recording_clip_path(event_id, min_duration_seconds=18.0)

    assert resolved is None
    assert recording_path.exists()
    assert preview_sprite_path.exists()
    assert preview_manifest_path.exists()
    assert service.get_recording_clip_path(event_id) == recording_path


def test_get_recording_clip_duration_rejects_unmeasurable_clip(tmp_path, monkeypatch):
    service, _snapshots = _make_service(tmp_path, monkeypatch)
    event_id = "evt_unmeasurable_recording"
    service._recording_clip_path(event_id).write_bytes(b"x" * 2048)
    monkeypatch.setattr(media_cache_module, "_clip_duration_seconds", lambda _path: None)

    assert service.get_recording_clip_duration_seconds(event_id) is None


def test_get_recording_clip_path_reuses_cached_duration_for_unchanged_file(tmp_path, monkeypatch):
    service, _snapshots = _make_service(tmp_path, monkeypatch)
    event_id = "evt_duration_cache"

    recording_path = service._recording_clip_path(event_id)
    recording_path.write_bytes(b"x" * 4096)

    calls = {"count": 0}

    def fake_duration(_path):
        calls["count"] += 1
        return 28.0

    monkeypatch.setattr(media_cache_module, "_clip_duration_seconds", fake_duration)

    resolved_first = service.get_recording_clip_path(event_id, min_duration_seconds=27.0)
    resolved_second = service.get_recording_clip_path(event_id, min_duration_seconds=27.0)

    assert resolved_first == recording_path
    assert resolved_second == recording_path
    assert calls["count"] == 1


def test_get_recording_clip_path_invalidates_cached_duration_when_file_changes(tmp_path, monkeypatch):
    service, _snapshots = _make_service(tmp_path, monkeypatch)
    event_id = "evt_duration_cache_invalidate"

    recording_path = service._recording_clip_path(event_id)
    recording_path.write_bytes(b"x" * 4096)

    calls = {"count": 0}

    def fake_duration(_path):
        calls["count"] += 1
        return 28.0

    monkeypatch.setattr(media_cache_module, "_clip_duration_seconds", fake_duration)

    resolved_first = service.get_recording_clip_path(event_id, min_duration_seconds=27.0)
    recording_path.write_bytes(b"y" * 8192)
    resolved_second = service.get_recording_clip_path(event_id, min_duration_seconds=27.0)

    assert resolved_first == recording_path
    assert resolved_second == recording_path
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_thumbnail_cache_uses_distinct_key_from_snapshot_cache(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    event_id = "evt_thumb_split"

    snapshot_path = await service.cache_snapshot(event_id, b"snapshot-bytes")
    thumbnail_path = await service.cache_thumbnail(event_id, b"thumbnail-bytes")

    assert snapshot_path == snapshots / f"{event_id}.jpg"
    assert thumbnail_path == snapshots / f"{event_id}_thumb.jpg"
    assert await service.get_snapshot(event_id) == b"snapshot-bytes"
    assert await service.get_thumbnail(event_id) == b"thumbnail-bytes"


@pytest.mark.parametrize(
    "hostile_event_id",
    [
        "../escape",
        "..",
        "a/../../b",
        "/etc/passwd",
        "..\\windows",
        ".hidden",
        "",
    ],
)
def test_every_cache_path_helper_contains_hostile_ids(tmp_path, monkeypatch, hostile_event_id):
    """Media identifiers are attacker-influenced; every path helper must either
    refuse a hostile identifier or neutralise it into a single filename that
    stays inside its own cache directory (#305)."""
    service, _snapshots = _make_service(tmp_path, monkeypatch)
    cache_base = tmp_path / "media_cache"
    helpers = [
        service._snapshot_path,
        service._thumbnail_path,
        service._clip_path,
        service._recording_clip_path,
        service._preview_sprite_path,
        service._preview_manifest_path,
    ]
    for helper in helpers:
        try:
            path = helper(hostile_event_id)
        except ValueError:
            continue
        assert path.parent.is_relative_to(cache_base), path
        assert "/" not in path.name and "\\" not in path.name
        assert ".." not in path.name.split(".")  # no bare parent reference survives


def test_cache_path_helpers_contain_benign_ids(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    path = service._snapshot_path("evt-1234.ok_id")
    assert path == snapshots / "evt-1234.ok_id.jpg"
    assert str(path).startswith(str(snapshots))


@pytest.mark.asyncio
async def test_recording_alignment_survives_hint_update_but_never_another_photograph(tmp_path, monkeypatch):
    service, _ = _make_service(tmp_path, monkeypatch)
    alignment = {"frame_time": 105.25, "box": [0.25, 0.2, 0.1, 0.15]}
    await service.cache_snapshot(
        "evt-align", b"first", source="frigate_recording_snapshot", recording_alignment=alignment
    )
    assert (await service.get_snapshot_metadata("evt-align"))["recording_alignment"] == alignment
    await service.update_snapshot_event_hints("evt-align", {"data": {"box": [0.8, 0.1, 0.1, 0.1]}})
    assert (await service.get_snapshot_metadata("evt-align"))["recording_alignment"] == alignment
    await service.replace_snapshot("evt-align", b"second", source="hq_candidate_full_frame")
    assert "recording_alignment" not in await service.get_snapshot_metadata("evt-align")
    await service.cache_snapshot("evt-align", b"third", source="frigate_recording_snapshot")
    assert "recording_alignment" not in await service.get_snapshot_metadata("evt-align")


@pytest.mark.asyncio
async def test_photo_alignment_is_bound_to_bytes_preserved_on_hint_refresh_and_cleared_on_replacement(
    tmp_path, monkeypatch
):
    import hashlib

    service, _ = _make_service(tmp_path, monkeypatch)
    photo = b"chosen-snapshot-crop"
    alignment = {"frame_time": 101, "box": [0.1, 0.2, 0.3, 0.4], "image_sha256": hashlib.sha256(photo).hexdigest()}
    await service.cache_snapshot(
        "aligned",
        photo,
        source="hq_candidate_model_crop",
        film_alignment=alignment,
        event_hints={"snapshot": {"frame_time": 101}},
    )
    first = await service.get_snapshot_metadata("aligned")
    assert first["film_alignment"] == alignment
    assert first["snapshot_photo_hints"]["event_hints"]["snapshot"]["frame_time"] == 101
    await service.update_snapshot_event_hints("aligned", {"snapshot": {"frame_time": 999}})
    refreshed = await service.get_snapshot_metadata("aligned")
    assert refreshed["film_alignment"] == alignment
    assert refreshed["snapshot_photo_hints"] == first["snapshot_photo_hints"]
    # A supplied alignment for the prior bytes cannot be re-sealed onto another photo.
    await service.replace_snapshot(
        "aligned", b"different-photo", source="hq_candidate_model_crop", film_alignment=alignment
    )
    replaced = await service.get_snapshot_metadata("aligned")
    assert replaced["film_alignment"] is None and replaced["snapshot_photo_hints"] is None
    await service.replace_snapshot("aligned", photo, film_alignment=alignment, manual_selection=True)
    assert (await service.get_snapshot_metadata("aligned"))["film_alignment"] == alignment
    await service.replace_snapshot("aligned", b"unproven-photo", manual_selection=True)
    assert (await service.get_snapshot_metadata("aligned"))["film_alignment"] is None


@pytest.mark.parametrize(
    "bad",
    [
        {"frame_time": float("nan")},
        {"frame_time": 0},
        {"frame_time": True},
        {"box": [0.9, 0.9, 0.5, 0.5]},
        {"box": [0, 0, 0, 1]},
        {"box": [1, 2, 3, 4]},
        {"image_sha256": "another-photo"},
    ],
)
def test_invalid_photo_alignment_is_never_accepted(bad):
    import hashlib

    alignment = {"frame_time": 101, "box": [0.1, 0.2, 0.3, 0.4], "image_sha256": hashlib.sha256(b"photo").hexdigest()}
    alignment.update(bad)
    assert media_cache_module.validate_film_alignment(alignment, b"photo") is None


@pytest.mark.asyncio
async def test_stale_manual_selection_sidecar_without_jpeg_does_not_block_recaching(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    await service.replace_snapshot("evt-stale", b"first-photo", source="hq_candidate_model_crop", manual_selection=True)
    # Simulate a missing JPEG while its sidecar survived.
    (snapshots / "evt-stale.jpg").unlink()

    assert not media_cache_module.has_manual_snapshot_selection("evt-stale")
    written = await service.cache_snapshot("evt-stale", b"recovered-photo", source="frigate_snapshot_unverified")
    assert written is not None
    assert await service.get_snapshot("evt-stale") == b"recovered-photo"
    meta = await service.get_snapshot_metadata("evt-stale") or {}
    assert not meta.get("manual_selection")


@pytest.mark.asyncio
async def test_stale_manual_selection_sidecar_without_jpeg_does_not_block_automatic_replace(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    await service.replace_snapshot("evt-auto", b"first-photo", source="hq_candidate_model_crop", manual_selection=True)
    (snapshots / "evt-auto.jpg").unlink()

    written = await service.replace_snapshot("evt-auto", b"hq-photo", source="high_quality_bird_crop", automatic=True)
    assert written is not None
    assert await service.get_snapshot("evt-auto") == b"hq-photo"
    meta = await service.get_snapshot_metadata("evt-auto") or {}
    assert not meta.get("manual_selection")


@pytest.mark.asyncio
async def test_empty_file_cleanup_removes_orphaned_sidecar_and_derived_thumbnail(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    await service.replace_snapshot("evt-empty", b"photo", source="hq_candidate_model_crop", manual_selection=True)
    await service.cache_thumbnail("evt-empty", b"thumb", source="snapshot_derived")
    (snapshots / "evt-empty.jpg").write_bytes(b"")

    stats = await service.cleanup_empty_files()
    assert stats["snapshots_deleted"] == 1
    assert not (snapshots / "evt-empty.jpg").exists()
    assert not (snapshots / "evt-empty.jpg.meta.json").exists()
    assert not (snapshots / "evt-empty_thumb.jpg").exists()
    assert not (snapshots / "evt-empty_thumb.jpg.meta.json").exists()


@pytest.mark.asyncio
async def test_empty_file_cleanup_preserves_event_hints_and_non_derived_thumbnail(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    await service.cache_snapshot(
        "evt-hints",
        b"photo",
        source="frigate_snapshot",
        event_hints={"snapshot": {"frame_time": 123.4, "box": [0.1, 0.2, 0.3, 0.4]}},
    )
    await service.replace_snapshot("evt-hints", b"chosen", source="hq_candidate_model_crop", manual_selection=True)
    await service.cache_thumbnail("evt-hints", b"frigate-thumb", source="frigate_thumbnail")
    (snapshots / "evt-hints.jpg").write_bytes(b"")

    stats = await service.cleanup_empty_files()
    assert stats["snapshots_deleted"] == 1
    assert not (snapshots / "evt-hints.jpg").exists()
    # Event hints survive while stale manual_selection is stripped.
    meta = await service.get_snapshot_metadata("evt-hints") or {}
    assert meta.get("event_hints") == {"snapshot": {"frame_time": 123.4, "box": [0.1, 0.2, 0.3, 0.4]}}
    assert "manual_selection" not in meta
    # Independent Frigate thumbnail is not deleted as a derived thumbnail.
    assert (snapshots / "evt-hints_thumb.jpg").exists()
    assert (snapshots / "evt-hints_thumb.jpg.meta.json").exists()


@pytest.mark.asyncio
async def test_empty_file_cleanup_serializes_with_concurrent_owner_save(tmp_path, monkeypatch):
    import asyncio

    service, snapshots = _make_service(tmp_path, monkeypatch)
    (snapshots / "evt-race.jpg").write_bytes(b"")
    (snapshots / "evt-race.jpg.meta.json").write_text('{"event_id": "evt-race"}', encoding="utf-8")

    # Hold the snapshot commit lock so cleanup discovers the zero-byte file first,
    # then a concurrent owner save replaces it before cleanup runs under the lock.
    async with service._snapshot_commit_lock("evt-race"):
        cleanup_task = asyncio.create_task(service.cleanup_empty_files())
        await asyncio.sleep(0.05)
        (snapshots / "evt-race.jpg").write_bytes(b"new-owner-photo")
        (snapshots / "evt-race.jpg.meta.json").write_text(
            '{"event_id": "evt-race", "manual_selection": true}', encoding="utf-8"
        )

    stats = await cleanup_task
    assert stats["snapshots_deleted"] == 0
    assert (snapshots / "evt-race.jpg").read_bytes() == b"new-owner-photo"
    assert media_cache_module.has_manual_snapshot_selection("evt-race") is True


@pytest.mark.asyncio
async def test_has_manual_snapshot_selection_fails_closed_on_io_error_and_corrupt_sidecar(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    await service.replace_snapshot("evt-corrupt", b"photo", source="hq_candidate_model_crop", manual_selection=True)
    (snapshots / "evt-corrupt.jpg.meta.json").write_text("{not-json", encoding="utf-8")
    assert media_cache_module.has_manual_snapshot_selection("evt-corrupt") is True

    original_stat = media_cache_module.Path.stat

    def _boom_stat(self, *args, **kwargs):
        if self.name == "evt-corrupt.jpg":
            raise PermissionError("transient io error")
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(media_cache_module.Path, "stat", _boom_stat)
    assert media_cache_module.has_manual_snapshot_selection("evt-corrupt") is True


@pytest.mark.asyncio
@pytest.mark.parametrize("sidecar", ["{not-json", "[]"])
async def test_unreadable_selection_sidecar_protects_photo_from_automatic_writes(tmp_path, monkeypatch, sidecar):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    await service.replace_snapshot("evt-choice", b"chosen", manual_selection=True)
    (snapshots / "evt-choice.jpg.meta.json").write_text(sidecar, encoding="utf-8")

    await service.cache_snapshot("evt-choice", b"new Frigate photo")
    await service.replace_snapshot("evt-choice", b"new automatic photo", automatic=True)

    assert media_cache_module.has_manual_snapshot_selection("evt-choice")
    assert await service.get_snapshot("evt-choice") == b"chosen"


@pytest.mark.asyncio
async def test_age_cleanup_only_locks_groups_with_expired_files(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    await service.cache_snapshot("fresh", b"fresh")
    await service.cache_snapshot("old", b"old")
    old_time = (datetime.now() - timedelta(days=5)).timestamp()
    os.utime(snapshots / "old.jpg", (old_time, old_time))
    checked = []
    age = service._age_media_group

    async def record_group(**kwargs):
        checked.append(kwargs["event_id"])
        return await age(**kwargs)

    monkeypatch.setattr(service, "_age_media_group", record_group)
    _without_detection_history(service, monkeypatch)
    stats = await service.cleanup_old_media(1)

    assert checked == ["old"]
    assert stats["snapshots_deleted"] == 1
    assert await service.get_snapshot("fresh") == b"fresh"


@pytest.mark.asyncio
async def test_has_live_manual_selection_requires_nonempty_snapshot_and_fails_closed_on_io_error(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    await service.replace_snapshot("evt-live", b"photo", source="hq_candidate_model_crop", manual_selection=True)
    assert await service.has_live_manual_selection("evt-live") is True

    (snapshots / "evt-live.jpg").unlink()
    assert await service.has_live_manual_selection("evt-live") is False

    async def _boom_stat(_path):
        raise PermissionError("transient io error")

    monkeypatch.setattr(media_cache_module.aiofiles.os, "stat", _boom_stat)
    assert await service.has_live_manual_selection("evt-live") is True


@pytest.mark.asyncio
async def test_clear_all_removes_metadata_sidecars(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    await service.replace_snapshot("evt-clear", b"photo", source="hq_candidate_model_crop", manual_selection=True)

    await service.clear_all()
    assert list(snapshots.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("sidecar", [b"{bad-json", b"[]"])
async def test_hint_refresh_preserves_unreadable_owner_photo_metadata(tmp_path, monkeypatch, sidecar):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    await service.replace_snapshot("hint-choice", b"chosen", manual_selection=True)
    metadata = snapshots / "hint-choice.jpg.meta.json"
    metadata.write_bytes(sidecar)

    assert not await service.update_snapshot_event_hints("hint-choice", {"snapshot": {"frame_time": 1.5}})
    assert metadata.read_bytes() == sidecar
    await service.cache_snapshot("hint-choice", b"automatic")
    assert await service.get_snapshot("hint-choice") == b"chosen"


@pytest.mark.asyncio
async def test_thumbnail_invalidation_and_cache_writes_preserve_literal_snapshot(tmp_path, monkeypatch):
    service, _ = _make_service(tmp_path, monkeypatch)
    await service.replace_snapshot("literal_thumb", b"chosen", manual_selection=True)

    await service.cache_snapshot("literal", b"other capture")
    # Caching "literal" invalidates its thumbnail slot, which is "literal_thumb"'s own photo.
    assert await service.get_snapshot("literal_thumb") == b"chosen"
    assert await service.get_snapshot_metadata("literal_thumb")
    assert await service.cache_thumbnail("literal", b"thumbnail") is None
    assert await service.get_thumbnail("literal") is None
    assert await service.get_thumbnail_path("literal") is None
    assert await service.get_cached_image_version("literal", thumbnail=True) is None
    assert await service.get_snapshot("literal_thumb") == b"chosen"
    assert await service.has_live_manual_selection("literal_thumb")


@pytest.mark.asyncio
@pytest.mark.parametrize("event_id", ["live", "live_recording"])
async def test_empty_file_cleanup_leaves_streaming_clips_until_writes_finish(tmp_path, monkeypatch, event_id):
    service, _ = _make_service(tmp_path, monkeypatch)
    opened = asyncio.Event()
    send = asyncio.Event()
    data = b"clip" * 256

    async def chunks():
        opened.set()
        await send.wait()
        yield data

    writer = asyncio.create_task(service.cache_clip_streaming(event_id, chunks()))
    await asyncio.wait_for(opened.wait(), 2)
    try:
        stats = await service.cleanup_empty_files()
        assert stats["clips_deleted"] == 0
    finally:
        send.set()
        path = await writer
    assert path is not None
    assert path.read_bytes() == data


@pytest.mark.asyncio
async def test_empty_file_cleanup_leaves_a_streaming_recording_clip_until_its_write_finishes(tmp_path, monkeypatch):
    service, _ = _make_service(tmp_path, monkeypatch)
    opened, send = asyncio.Event(), asyncio.Event()
    data = b"clip" * 4096

    async def chunks():
        opened.set()
        await send.wait()
        yield data

    async def commit(event_id, *, path, tmp_path, total_size):
        # Duration probing needs a real video; this test is about the hidden file staying put.
        tmp_path.replace(path)
        return path

    monkeypatch.setattr(service, "_commit_recording_clip_candidate", commit)
    writer = asyncio.create_task(service.cache_recording_clip_streaming("live", chunks()))
    await asyncio.wait_for(opened.wait(), 2)
    try:
        # The recording is written through a hidden temporary file that is empty until the first chunk.
        assert [path.name.startswith(".live_recording.") for path in media_cache_module.CLIPS_DIR.iterdir()] == [True]
        stats = await service.cleanup_empty_files()
        assert stats["clips_deleted"] == 0
    finally:
        send.set()
        path = await writer
    assert path is not None
    assert path.read_bytes() == data


@pytest.mark.asyncio
async def test_empty_file_cleanup_removes_an_abandoned_hidden_recording_file(tmp_path, monkeypatch):
    service, _ = _make_service(tmp_path, monkeypatch)
    abandoned = media_cache_module.CLIPS_DIR / f".gone_recording.{'a' * 32}.tmp.mp4"
    abandoned.touch()

    assert (await service.cleanup_empty_files())["clips_deleted"] == 1
    assert not abandoned.exists()


@pytest.mark.asyncio
async def test_empty_file_cleanup_skips_previews_during_publication(tmp_path, monkeypatch):
    service, _ = _make_service(tmp_path, monkeypatch)
    path = service._preview_sprite_path("live-preview")
    async with service._media_write_lease("live-preview"):
        path.touch()
        assert (await service.cleanup_empty_files())["previews_deleted"] == 0
        assert path.exists()
    assert (await service.cleanup_empty_files())["previews_deleted"] == 1
    assert not path.exists()


@pytest.mark.asyncio
async def test_age_cleanup_waits_for_the_storage_sweep_before_staging_anything(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    _without_detection_history(service, monkeypatch)
    await service.cache_snapshot("aged", b"aged-photo")
    old_time = (datetime.now() - timedelta(days=5)).timestamp()
    for path in snapshots.iterdir():
        os.utime(path, (old_time, old_time))
    waiting = asyncio.Event()

    class ObservedLock(asyncio.Lock):
        async def acquire(self) -> bool:
            if self.locked():
                waiting.set()
            return await super().acquire()

    service.housekeeping_lock = ObservedLock()
    async with service.housekeeping_lock:
        cleanup = asyncio.create_task(service.cleanup_old_media(1))
        await asyncio.wait_for(waiting.wait(), 2)
        # While the sweep holds the lock, age cleanup has staged nothing.
        assert (snapshots / "aged.jpg").exists()
        assert not [path for path in snapshots.iterdir() if path.name.startswith(".")]
    stats = await cleanup
    assert stats["snapshots_deleted"] == 1
    assert not (snapshots / "aged.jpg").exists()


@pytest.mark.asyncio
async def test_age_cleanup_lets_a_waiting_storage_sweep_run_between_visits(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    _without_detection_history(service, monkeypatch)
    for event_id in ("aged-one", "aged-two"):
        await service.cache_snapshot(event_id, b"aged-photo")
    old_time = (datetime.now() - timedelta(days=5)).timestamp()
    for path in snapshots.iterdir():
        os.utime(path, (old_time, old_time))
    order: list[str] = []
    sweeps: list[asyncio.Task] = []
    original_age = service._age_media_group

    async def sweep() -> None:
        async with service.housekeeping_lock:
            order.append("sweep")

    async def age_group(**kwargs):
        order.append(kwargs["event_id"])
        if not sweeps:
            # The five-minute sweep arrives while the first visit is being aged.
            sweeps.append(asyncio.create_task(sweep()))
            await asyncio.sleep(0)
        return await original_age(**kwargs)

    monkeypatch.setattr(service, "_age_media_group", age_group)
    await service.cleanup_old_media(1)
    await sweeps[0]
    # asyncio.Lock is first come, first served, so the waiting sweep goes before the next visit.
    assert order[1] == "sweep" and sorted(order[::2]) == ["aged-one", "aged-two"]


def _leave_age_staged(service, path: Path) -> Path:
    """The state an age cleanup leaves when the process dies after staging a file."""
    [(_original, staged)] = service._stage_paths_sync([path], media_cache_module._AGE_STAGED_SUFFIX)
    return staged


@pytest.mark.asyncio
async def test_returning_a_left_over_file_never_overwrites_an_owner_choice_published_meanwhile(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    await service.cache_snapshot("x", b"old-automatic-photo")
    photo = snapshots / "x.jpg"
    _leave_age_staged(service, photo)
    loop = asyncio.get_running_loop()
    about_to_move, published = asyncio.Event(), threading.Event()
    original_link = os.link

    def link_after_the_owner_publishes(source, target, *args, **kwargs):
        if Path(target) == photo and not published.is_set():
            # The owner's Apply lands between any check and the move.
            loop.call_soon_threadsafe(about_to_move.set)
            assert published.wait(5)
        return original_link(source, target, *args, **kwargs)

    monkeypatch.setattr(media_cache_module.os, "link", link_after_the_owner_publishes)
    returning = asyncio.create_task(service.return_age_staged_files())
    await asyncio.wait_for(about_to_move.wait(), 5)
    await service.replace_snapshot("x", b"owner-chosen-photo", manual_selection=True)
    published.set()
    assert await returning == 0

    assert await service.get_snapshot("x") == b"owner-chosen-photo"
    assert (await service.get_snapshot_metadata("x"))["manual_selection"] is True
    assert not [path for path in snapshots.iterdir() if path.name.endswith(".ageing.tmp")]
    # The owner's photo, proved by its sidecar's hash, replaces the stale copy outright.
    assert not [path for path in snapshots.iterdir() if path.name.endswith(".kept.tmp")]


@pytest.mark.asyncio
@pytest.mark.parametrize("hard_links", [True, False])
async def test_a_left_over_file_whose_name_holds_an_automatic_file_is_kept_beside_it(tmp_path, monkeypatch, hard_links):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    if not hard_links:
        monkeypatch.setattr(media_cache_module.os, "link", _no_hard_links)
    await service.cache_snapshot("back", b"kept-photo")
    await service.cache_snapshot("newer", b"old-photo")
    _leave_age_staged(service, snapshots / "back.jpg")
    _leave_age_staged(service, snapshots / "newer.jpg")
    # Something wrote the name meanwhile, and nothing says it was the owner.
    (snapshots / "newer.jpg").write_bytes(b"newer-photo")

    assert await service.return_age_staged_files() == 1
    assert await service.get_snapshot("back") == b"kept-photo"
    assert await service.get_snapshot("newer") == b"newer-photo"
    # Neither copy is deleted: the set-aside one is kept under a recovery name.
    [kept] = [path for path in snapshots.iterdir() if path.name.endswith(".kept.tmp")]
    assert kept.name.startswith(".newer.jpg.") and kept.read_bytes() == b"old-photo"
    assert not [path for path in snapshots.iterdir() if path.name.endswith(".ageing.tmp")]
    assert service.set_aside_pending_count == 0


def _no_hard_links(*args, **kwargs):
    raise PermissionError(errno.EPERM, "hard links are not supported on this volume")


@pytest.mark.asyncio
@pytest.mark.parametrize("hard_links", [True, False])
async def test_a_stuck_left_over_photo_is_never_lost_to_an_automatic_recache(tmp_path, monkeypatch, hard_links):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    await service.cache_snapshot("conf", b"owner-confirmed-hq-photo")
    staged = _leave_age_staged(service, snapshots / "conf.jpg")
    original_link = os.link
    disk_full = True

    def link(source, target, *args, **kwargs):
        if disk_full:
            raise OSError(errno.ENOSPC, "No space left on device")
        if not hard_links:
            return _no_hard_links()
        return original_link(source, target, *args, **kwargs)

    monkeypatch.setattr(media_cache_module.os, "link", link)
    original_rename_back = service._rename_age_staged_file_back_sync

    def rename_back(path):
        if disk_full:
            raise OSError(errno.ENOSPC, "No space left on device")
        return original_rename_back(path)

    monkeypatch.setattr(service, "_rename_age_staged_file_back_sync", rename_back)
    assert await service.return_age_staged_files() == 0
    assert staged.read_bytes() == b"owner-confirmed-hq-photo"
    assert service.set_aside_pending_count == 1
    # The record and card routes re-cache Frigate's photo while it is set aside: they must leave it alone.
    disk_full = False
    assert await service.cache_snapshot("conf", b"frigate-recache", source="frigate_snapshot_unverified") is None
    assert await service.cache_thumbnail("conf", b"frigate-thumb") is None
    assert await service.replace_snapshot("conf", b"automatic", automatic=True) is None
    assert await service.return_age_staged_files() == 1
    assert await service.get_snapshot("conf") == b"owner-confirmed-hq-photo"
    assert service.set_aside_pending_count == 0


@pytest.mark.asyncio
async def test_a_file_that_came_back_but_left_its_set_aside_name_behind_counts_as_returned(tmp_path, monkeypatch):
    from app.services.error_diagnostics import error_diagnostics_history

    error_diagnostics_history.clear()
    service, snapshots = _make_service(tmp_path, monkeypatch)
    await service.cache_snapshot("dup", b"the-photo")
    staged = _leave_age_staged(service, snapshots / "dup.jpg")
    original_unlink = Path.unlink

    def unlink_fails_for_the_set_aside_name(self, *args, **kwargs):
        if self == staged:
            raise OSError(errno.EIO, "Input/output error")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink_fails_for_the_set_aside_name)
    assert await service.return_age_staged_files() == 1
    assert await service.get_snapshot("dup") == b"the-photo"
    assert service.set_aside_pending_count == 0
    assert not [
        e for e in error_diagnostics_history.snapshot()["events"] if e["reason_code"] == "media_set_aside_unreturned"
    ]
    monkeypatch.setattr(Path, "unlink", original_unlink)
    # The next pass sees the same file under both names and only removes the stray one.
    assert await service.return_age_staged_files() == 0
    assert not staged.exists()
    assert await service.get_snapshot("dup") == b"the-photo"
    assert not [path for path in snapshots.iterdir() if path.name.endswith(".kept.tmp")]


@pytest.mark.asyncio
async def test_without_hard_links_a_left_over_file_is_renamed_back_under_its_visit_locks(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    await service.cache_snapshot("nolink", b"kept-photo")
    _leave_age_staged(service, snapshots / "nolink.jpg")

    def no_hard_links(*args, **kwargs):
        raise PermissionError(errno.EPERM, "hard links are not supported on this volume")

    monkeypatch.setattr(media_cache_module.os, "link", no_hard_links)
    original_rename_back = service._rename_age_staged_file_back_sync
    locked_during_rename: list[bool] = []

    def rename_back(staged):
        locked_during_rename.append(service._snapshot_commit_lock("nolink").locked())
        return original_rename_back(staged)

    monkeypatch.setattr(service, "_rename_age_staged_file_back_sync", rename_back)
    assert await service.return_age_staged_files() == 1
    assert await service.get_snapshot("nolink") == b"kept-photo"
    assert locked_during_rename and all(locked_during_rename)


class _ObservedLock(asyncio.Lock):
    """A lock that says when a second caller has to wait for it."""

    def __init__(self) -> None:
        super().__init__()
        self.contended = asyncio.Event()

    async def acquire(self) -> bool:
        if self.locked():
            self.contended.set()
        return await super().acquire()


@pytest.mark.asyncio
@pytest.mark.parametrize("capture_id", ["x", "lit_thumb", "lit_recording", "lit_preview"])
async def test_without_hard_links_a_left_over_file_never_overwrites_an_owner_choice(tmp_path, monkeypatch, capture_id):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    await service.cache_snapshot(capture_id, b"old-automatic-photo")
    photo = snapshots / f"{capture_id}.jpg"
    _leave_age_staged(service, photo)

    def no_hard_links(*args, **kwargs):
        raise PermissionError(errno.EPERM, "hard links are not supported on this volume")

    monkeypatch.setattr(media_cache_module.os, "link", no_hard_links)
    # The owner's Apply takes this capture's own commit lock, whatever its ID ends with.
    owner_lock = _ObservedLock()
    service._snapshot_commit_locks[capture_id] = owner_lock
    loop = asyncio.get_running_loop()
    checked, release = asyncio.Event(), threading.Event()
    original_exists = Path.exists

    def exists_then_wait(self, *args, **kwargs):
        result = original_exists(self, *args, **kwargs)
        if self == photo and not release.is_set():
            loop.call_soon_threadsafe(checked.set)
            assert release.wait(5)
        return result

    monkeypatch.setattr(Path, "exists", exists_then_wait)
    returning = asyncio.create_task(service.return_age_staged_files())
    await asyncio.wait_for(checked.wait(), 5)
    apply = asyncio.create_task(service.replace_snapshot(capture_id, b"owner-chosen-photo", manual_selection=True))
    contended = asyncio.create_task(owner_lock.contended.wait())
    # Either the Apply publishes inside the check-then-rename window, or it waits for the return.
    await asyncio.wait({apply, contended}, return_when=asyncio.FIRST_COMPLETED)
    contended.cancel()
    release.set()
    await returning
    await apply

    assert (await service.get_snapshot_metadata(capture_id))["manual_selection"] is True
    assert await service.get_snapshot(capture_id) == b"owner-chosen-photo"


@pytest.mark.asyncio
async def test_a_left_over_file_that_cannot_be_returned_does_not_stop_the_others(tmp_path, monkeypatch):
    from app.services.error_diagnostics import error_diagnostics_history

    error_diagnostics_history.clear()
    service, snapshots = _make_service(tmp_path, monkeypatch)
    await service.cache_snapshot("stuck", b"stuck-photo")
    await service.cache_snapshot("fine", b"fine-photo")
    stuck = _leave_age_staged(service, snapshots / "stuck.jpg")
    _leave_age_staged(service, snapshots / "fine.jpg")
    original_link = os.link

    def failing_disk(source, target, *args, **kwargs):
        if Path(target).name == "stuck.jpg":
            raise OSError(errno.EIO, "Input/output error")
        return original_link(source, target, *args, **kwargs)

    monkeypatch.setattr(media_cache_module.os, "link", failing_disk)
    assert await service.return_age_staged_files() == 1

    assert await service.get_snapshot("fine") == b"fine-photo"
    # The stuck file stays set aside, unharmed, for the next try.
    assert stuck.read_bytes() == b"stuck-photo"
    [diagnostic] = [
        event
        for event in error_diagnostics_history.snapshot()["events"]
        if event["reason_code"] == "media_set_aside_unreturned"
    ]
    assert diagnostic["component"] == "media_cache"
    assert diagnostic["context"] == {"files": 1}
    error_diagnostics_history.clear()


def _disk_errors_for(monkeypatch, *, stat: set[Path] = frozenset(), read: set[Path] = frozenset()) -> None:
    """EIO from stat or read for the given paths only, as a flaky volume gives."""
    original_stat, original_read = Path.stat, Path.read_text

    def failing_stat(self, *args, **kwargs):
        if self in stat:
            raise OSError(errno.EIO, "Input/output error")
        return original_stat(self, *args, **kwargs)

    def failing_read(self, *args, **kwargs):
        if self in read:
            raise OSError(errno.EIO, "Input/output error")
        return original_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", failing_stat)
    monkeypatch.setattr(Path, "read_text", failing_read)


@pytest.mark.asyncio
async def test_a_failed_restore_holds_every_set_aside_name_even_when_the_disk_cannot_be_read(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    await service.cache_snapshot("conf", b"owner-confirmed-hq-photo")
    pairs = service._stage_paths_sync(
        [snapshots / "conf.jpg", snapshots / "conf.jpg.meta.json"], media_cache_module._AGE_STAGED_SUFFIX
    )

    def restore_fails(staged):
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(service, "_restore_staged_deletion_sync", restore_fails)
    with monkeypatch.context() as disk:
        _disk_errors_for(disk, stat={target for _original, target in pairs})
        with pytest.raises(OSError):
            await service._put_back_or_hold(pairs)
    assert service.set_aside_pending_count == 2
    assert await service.cache_snapshot("conf", b"frigate-recache", source="frigate_snapshot_unverified") is None


@pytest.mark.asyncio
async def test_a_staging_rollback_that_fails_holds_the_names_it_left_set_aside(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    for event_id in ("one", "two"):
        await service.cache_snapshot(event_id, b"photo")
    original_rename = Path.rename

    def rename(self, target):
        # Staging "two" fails, and so does putting "one" back.
        if self.name == "two.jpg" or (self.name.endswith(".ageing.tmp") and Path(target).name == "one.jpg"):
            raise OSError(errno.EIO, "Input/output error")
        return original_rename(self, target)

    monkeypatch.setattr(Path, "rename", rename)
    with pytest.raises(OSError):
        service._stage_paths_sync([snapshots / "one.jpg", snapshots / "two.jpg"], media_cache_module._AGE_STAGED_SUFFIX)
    assert service.set_aside_pending_count == 1
    assert service._snapshot_set_aside("one")


@pytest.mark.asyncio
@pytest.mark.parametrize("sidecar", ["unreadable", "stale_hash", "no_hash", "not_an_object"])
async def test_a_taken_name_drops_the_set_aside_copy_only_for_a_proved_owner_choice(tmp_path, monkeypatch, sidecar):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    await service.cache_snapshot("conf", b"owner-confirmed-hq-photo")
    _leave_age_staged(service, snapshots / "conf.jpg")
    _leave_age_staged(service, snapshots / "conf.jpg.meta.json")
    photo, meta = snapshots / "conf.jpg", snapshots / "conf.jpg.meta.json"
    photo.write_bytes(b"frigate-recache")
    meta_text = {
        "unreadable": '{"manual_selection": true}',
        "stale_hash": '{"manual_selection": true, "image_sha256": "%s"}' % ("0" * 64),
        "no_hash": '{"manual_selection": true}',
        "not_an_object": "[]",
    }[sidecar]
    meta.write_text(meta_text)
    if sidecar == "unreadable":
        _disk_errors_for(monkeypatch, read={meta})

    await service.return_age_staged_files()

    # Nothing proves the photo at the name is the owner's, so the set-aside one is kept.
    survivors = [p for p in snapshots.iterdir() if p.is_file() and p.read_bytes() == b"owner-confirmed-hq-photo"]
    assert survivors, "the set-aside photo was deleted"
    assert [p for p in snapshots.iterdir() if p.name.endswith(".kept.tmp")]


@pytest.mark.asyncio
async def test_the_whole_chain_of_disk_errors_never_deletes_a_confirmed_photo(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    await service.cache_snapshot("conf", b"owner-confirmed-hq-photo")
    pairs = service._stage_paths_sync(
        [snapshots / "conf.jpg", snapshots / "conf.jpg.meta.json"], media_cache_module._AGE_STAGED_SUFFIX
    )

    def restore_fails(staged):
        raise OSError(errno.EIO, "Input/output error")

    with monkeypatch.context() as disk:
        disk.setattr(service, "_restore_staged_deletion_sync", restore_fails)
        _disk_errors_for(disk, stat={target for _original, target in pairs})
        with pytest.raises(OSError):
            await service._put_back_or_hold(pairs)
    # The card route tries to re-cache Frigate's photo, then the next sweep cannot read the sidecar.
    await service.cache_snapshot("conf", b"frigate-recache", source="frigate_snapshot_unverified")
    with monkeypatch.context() as disk:
        _disk_errors_for(disk, read={snapshots / "conf.jpg.meta.json"})
        await service.return_age_staged_files()
    survivors = [p for p in snapshots.iterdir() if p.is_file() and p.read_bytes() == b"owner-confirmed-hq-photo"]
    assert survivors, "the owner-confirmed photo was deleted"


@pytest.mark.asyncio
async def test_clip_recording_and_preview_writers_leave_a_held_name_alone(tmp_path, monkeypatch):
    service, _ = _make_service(tmp_path, monkeypatch)
    clip = service._clip_path("held")
    recording = service._recording_clip_path("held")
    sprite, manifest = service._preview_sprite_path("held"), service._preview_manifest_path("held")
    monkeypatch.setattr(service, "_set_aside_pending", {clip, recording, sprite, manifest})
    data = b"\x00\x00\x00\x18ftypmp42" + b"a" * 1024

    async def chunks():
        yield data

    monkeypatch.setattr(media_cache_module, "_clip_duration_seconds", lambda _path: 5.0)
    assert await service.cache_clip("held", data) is None
    assert await service.cache_clip_streaming("held", chunks()) is None
    assert await service.cache_recording_clip("held", data) is None
    assert await service.cache_preview_assets("held", b"sprite", "{}") is False
    assert list(media_cache_module.CLIPS_DIR.iterdir()) == []
    assert list(media_cache_module.PREVIEWS_DIR.iterdir()) == []


@pytest.mark.asyncio
async def test_the_hint_refresh_leaves_a_held_sidecar_alone(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    await service.cache_snapshot("hinted", b"photo")
    sidecar = snapshots / "hinted.jpg.meta.json"
    before = sidecar.read_bytes()
    monkeypatch.setattr(service, "_set_aside_pending", {sidecar})
    assert not await service.update_snapshot_event_hints("hinted", {"snapshot": {"frame_time": 2.0}})
    assert sidecar.read_bytes() == before


@pytest.mark.asyncio
async def test_age_cleanup_leaves_a_visit_alone_while_part_of_it_is_set_aside(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    _without_detection_history(service, monkeypatch)
    await service.cache_snapshot("partly", b"aged-photo")
    old_time = (datetime.now() - timedelta(days=5)).timestamp()
    for path in snapshots.iterdir():
        os.utime(path, (old_time, old_time))
    # Its thumbnail could not go back yet, so the visit is judged only once it has.
    monkeypatch.setattr(service, "_set_aside_pending", {snapshots / "partly_thumb.jpg"})
    await service.cleanup_old_media(1)
    assert await service.get_snapshot("partly") == b"aged-photo"


@pytest.mark.asyncio
async def test_an_owner_apply_or_regeneration_still_writes_a_held_name(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    photo = snapshots / "held.jpg"
    monkeypatch.setattr(service, "_set_aside_pending", {photo})
    assert await service.replace_snapshot("held", b"owner-chosen", manual_selection=True)
    assert await service.get_snapshot("held") == b"owner-chosen"
    assert await service.replace_snapshot(
        "held",
        b"regenerated",
        clear_manual_selection=True,
        expected_manual_selection_updated_at=(await service.get_snapshot_metadata("held"))["updated_at"],
    )
    assert await service.get_snapshot("held") == b"regenerated"


async def _leave_a_kept_copy(service, snapshots: Path, event_id: str, content: bytes) -> Path:
    """A set-aside photo whose name an automatic file took, so the return kept it beside."""
    await service.cache_snapshot(event_id, content)
    _leave_age_staged(service, snapshots / f"{event_id}.jpg")
    (snapshots / f"{event_id}.jpg").write_bytes(b"automatic-photo")
    await service.return_age_staged_files()
    [kept] = [path for path in snapshots.iterdir() if path.name.endswith(".kept.tmp")]
    return kept


@pytest.mark.asyncio
async def test_a_kept_copy_counts_towards_space_used_and_shows_until_it_is_gone(tmp_path, monkeypatch):
    from app.services.error_diagnostics import error_diagnostics_history

    error_diagnostics_history.clear()
    service, snapshots = _make_service(tmp_path, monkeypatch)
    kept = await _leave_a_kept_copy(service, snapshots, "spare", b"k" * 5000)
    assert service.kept_copies_count == 1
    assert (await service.get_cache_stats())["total_size_bytes"] >= 5000
    [warning] = [e for e in error_diagnostics_history.snapshot()["events"] if e["reason_code"] == "media_kept_copies"]
    assert warning["severity"] == "warning" and warning["context"] == {"files": 1}

    kept.unlink()
    await service.return_age_staged_files()
    assert service.kept_copies_count == 0
    error_diagnostics_history.clear()


@pytest.mark.asyncio
async def test_deleting_a_capture_or_clearing_the_cache_removes_its_kept_copies(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    gone = await _leave_a_kept_copy(service, snapshots, "deleted", b"one")
    await service.delete_cached_media("deleted")
    assert not gone.exists()
    assert service.kept_copies_count == 0

    cleared = await _leave_a_kept_copy(service, snapshots, "cleared", b"three")
    assert service.kept_copies_count == 1
    await service.clear_all()
    assert not cleared.exists()
    assert service.kept_copies_count == 0


@pytest.mark.asyncio
async def test_cleanup_old_media_keeps_canonical_photo_for_owner_confirmed_and_manual_selection(tmp_path, monkeypatch):
    service, snapshots = _make_service(tmp_path, monkeypatch)
    clips = media_cache_module.CLIPS_DIR
    previews = media_cache_module.PREVIEWS_DIR

    # 1. Owner-confirmed event: canonical photo kept, candidate & clip aged out.
    await service.cache_snapshot("evt-confirmed", b"confirmed-photo", source="frigate_snapshot")
    await service.cache_thumbnail("evt-confirmed", b"confirmed-thumb", source="snapshot_derived")
    await service.cache_snapshot(
        "evt-confirmed__model_crop__f1__0123456789__image", b"cand", source="snapshot_candidate"
    )
    await service.cache_clip("evt-confirmed", b"c" * 1024)
    await service.cache_preview_assets("evt-confirmed", b"sprite", '{"cues": []}')

    # 2. Manually selected photo (without owner confirmation): canonical photo kept, candidate & clip aged out.
    await service.replace_snapshot(
        "evt-chosen", b"chosen-photo", source="hq_candidate_model_crop", manual_selection=True
    )
    await service.cache_snapshot("evt-chosen__model_crop__f1__0123456789__image", b"cand2", source="snapshot_candidate")
    await service.cache_clip("evt-chosen", b"c" * 1024)

    # 3. Ordinary event: everything aged out.
    await service.cache_snapshot("evt-ordinary", b"ordinary-photo", source="frigate_snapshot")
    await service.cache_clip("evt-ordinary", b"c" * 1024)

    old_time = (datetime.now() - timedelta(days=5)).timestamp()
    for directory in (snapshots, clips, previews):
        for path in directory.iterdir():
            os.utime(path, (old_time, old_time))

    _without_detection_history(service, monkeypatch)
    stats = await service.cleanup_old_media(
        retention_days=1,
        protected_event_ids=set(),
        protected_snapshot_event_ids=set(),
        protected_canonical_photo_event_ids={"evt-confirmed"},
    )

    assert (snapshots / "evt-confirmed.jpg").exists()
    assert (snapshots / "evt-confirmed.jpg.meta.json").exists()
    assert (snapshots / "evt-confirmed_thumb.jpg").exists()
    assert not (snapshots / "evt-confirmed__model_crop__f1__0123456789__image.jpg").exists()
    assert not (clips / "evt-confirmed.mp4").exists()
    assert not (previews / "evt-confirmed.jpg").exists()

    assert (snapshots / "evt-chosen.jpg").exists()
    assert (snapshots / "evt-chosen.jpg.meta.json").exists()
    assert not (snapshots / "evt-chosen__model_crop__f1__0123456789__image.jpg").exists()
    assert not (clips / "evt-chosen.mp4").exists()

    assert not (snapshots / "evt-ordinary.jpg").exists()
    assert not (clips / "evt-ordinary.mp4").exists()
    assert stats["protected_skipped"] == 6
