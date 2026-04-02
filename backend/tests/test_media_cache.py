from pathlib import Path

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
async def test_recording_clip_cache_uses_distinct_key_from_event_clip(tmp_path, monkeypatch):
    service, _snapshots = _make_service(tmp_path, monkeypatch)
    event_id = "evt_recording"

    clip_path = await service.cache_clip(event_id, b"a" * 600)
    recording_path = await service.cache_recording_clip(event_id, b"b" * 700)

    assert clip_path is not None
    assert recording_path is not None
    assert clip_path.name == f"{event_id}.mp4"
    assert recording_path.name == f"{event_id}_recording.mp4"
    assert clip_path != recording_path
    assert service.get_clip_path(event_id) == clip_path
    assert service.get_recording_clip_path(event_id) == recording_path


def test_get_recording_clip_path_rejects_truncated_cached_recording_and_preview_assets(tmp_path, monkeypatch):
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
    assert not recording_path.exists()
    assert not preview_sprite_path.exists()
    assert not preview_manifest_path.exists()
