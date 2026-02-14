from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.services import media_cache as media_cache_module


@pytest.mark.asyncio
async def test_cleanup_old_media_preserves_protected_event_ids(tmp_path, monkeypatch):
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

    service = media_cache_module.MediaCacheService()

    protected = "evt_favorite"
    stale = "evt_stale"

    protected_snapshot = snapshots / f"{protected}.jpg"
    protected_clip = clips / f"{protected}.mp4"
    protected_preview = previews / f"{protected}.json"
    stale_snapshot = snapshots / f"{stale}.jpg"
    stale_clip = clips / f"{stale}.mp4"
    stale_preview = previews / f"{stale}.json"

    for path in (
        protected_snapshot,
        protected_clip,
        protected_preview,
        stale_snapshot,
        stale_clip,
        stale_preview,
    ):
        path.write_bytes(b"x")

    old_time = (datetime.now() - timedelta(days=3)).timestamp()
    for path in (
        protected_snapshot,
        protected_clip,
        protected_preview,
        stale_snapshot,
        stale_clip,
        stale_preview,
    ):
        Path(path).touch()
        Path(path).chmod(0o644)
        import os
        os.utime(path, (old_time, old_time))

    stats = await service.cleanup_old_media(retention_days=1, protected_event_ids={protected})

    assert protected_snapshot.exists()
    assert protected_clip.exists()
    assert protected_preview.exists()
    assert not stale_snapshot.exists()
    assert not stale_clip.exists()
    assert not stale_preview.exists()
    assert stats["protected_skipped"] >= 3
