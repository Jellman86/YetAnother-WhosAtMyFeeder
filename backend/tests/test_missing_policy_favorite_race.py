"""Automatic expiry must honour a favourite accepted before its delete commits."""

from contextlib import closing
from datetime import datetime
import json
import os
import sqlite3

import aiosqlite
from aiosqlite.context import contextmanager as query_context
from PIL import Image
import pytest
import pytest_asyncio

from app.config import settings
from app.repositories.detection_repository import DetectionRepository, Detection
from app.services import frigate_missing_policy as policy
from app.services import media_cache as cache_module
from app.repositories.daily_totals_repository import DailyTotalsRepository


@pytest_asyncio.fixture
async def fixture_history(tmp_path, monkeypatch):
    path = tmp_path / "history.db"
    with closing(sqlite3.connect(os.environ["DB_PATH"])) as source, closing(sqlite3.connect(path)) as target:
        source.backup(target)
        target.execute("DELETE FROM detections")
        target.commit()
    for name in ("SNAPSHOTS_DIR", "CLIPS_DIR", "PREVIEWS_DIR"):
        directory = tmp_path / name.lower()
        directory.mkdir()
        monkeypatch.setattr(cache_module, name, directory)
    cache = cache_module.MediaCacheService()
    monkeypatch.setattr(policy, "media_cache", cache)
    monkeypatch.setattr(settings.maintenance, "frigate_missing_behavior", "delete")
    async with aiosqlite.connect(path) as deletion, aiosqlite.connect(path) as owner:
        for db in (deletion, owner):
            await db.execute("PRAGMA foreign_keys=ON")
        repo = DetectionRepository(deletion)
        owner_repo = DetectionRepository(owner)
        await repo.create(Detection(datetime.now(), 1, 0.9, "Robin", "Robin", "fav-race", "camera"))
        # A record YA-WAMF holds its own photo for is never deleted by the policy, so the files
        # whose cleanup these races guard are the record's preview, not its photograph.
        photograph = cache_module.PREVIEWS_DIR / "fav-race.jpg"
        Image.new("RGB", (24, 24), color="red").save(photograph)
        metadata = cache_module.PREVIEWS_DIR / "fav-race.json"
        metadata.write_text(json.dumps({"event_id": "fav-race", "source": "owner"}))
        yield repo, owner_repo, photograph, metadata


@pytest.mark.asyncio
async def test_favorite_accepted_immediately_before_delete_preserves_history_and_photograph(
    fixture_history, monkeypatch
):
    repo, owner, photograph, metadata = fixture_history
    # The automatic delete keeps the capture's count with it (#949); the favourite is accepted just
    # before that delete, which must still check it.
    original_delete = DailyTotalsRepository.delete_lost_capture
    accepted = []

    async def accept_favorite_then_delete(self, event_id, **kwargs):
        accepted.append(await owner.favorite_detection(event_id))
        return await original_delete(self, event_id, **kwargs)

    monkeypatch.setattr(DailyTotalsRepository, "delete_lost_capture", accept_favorite_then_delete)
    result = await policy.apply_missing_policy(
        repo=repo, frigate_event="fav-race", error="event_not_found", source="fixture", media_kind="any"
    )
    assert accepted == [True]
    detection = await owner.get_by_frigate_event("fav-race")
    assert detection is not None and detection.is_favorite
    assert detection.frigate_status == "missing"
    assert result == {"deleted_count": 0, "marked_missing_count": 1, "kept_count": 0}
    assert photograph.is_file() and metadata.is_file()


@pytest.mark.asyncio
async def test_automatic_delete_keeps_a_record_whose_photo_yawamf_still_holds(fixture_history):
    repo, owner, _preview, _metadata = fixture_history
    photograph = cache_module.SNAPSHOTS_DIR / "fav-race.jpg"
    Image.new("RGB", (24, 24), color="red").save(photograph)
    result = await policy.apply_missing_policy(
        repo=repo, frigate_event="fav-race", error="event_not_found", source="fixture", media_kind="snapshot"
    )
    assert result == {"deleted_count": 0, "marked_missing_count": 1, "kept_count": 0}
    detection = await owner.get_by_frigate_event("fav-race")
    assert detection is not None and detection.frigate_status == "missing"
    assert photograph.is_file()


@pytest.mark.asyncio
async def test_successful_automatic_delete_commits_history_before_removing_files(fixture_history, monkeypatch):
    repo, owner, photograph, metadata = fixture_history
    original_cleanup = policy.media_cache.delete_cached_media

    async def check_commit_then_cleanup(event_id):
        assert await owner.get_by_frigate_event(event_id) is None
        await original_cleanup(event_id)

    monkeypatch.setattr(policy.media_cache, "delete_cached_media", check_commit_then_cleanup)
    result = await policy.apply_missing_policy(
        repo=repo, frigate_event="fav-race", error="event_not_found", source="fixture", media_kind="any"
    )
    assert result["deleted_count"] == 1
    assert not photograph.exists() and not metadata.exists()
    assert await owner.favorite_detection("fav-race") is None


@pytest.mark.asyncio
async def test_explicit_owner_delete_still_removes_a_favorite(fixture_history):
    repo, owner, _photograph, _metadata = fixture_history
    assert await owner.favorite_detection("fav-race") is True
    assert await repo.delete_by_frigate_event("fav-race") is True
    assert await owner.get_by_frigate_event("fav-race") is None


@pytest.mark.asyncio
async def test_delete_winning_before_favorite_insert_returns_not_found_without_foreign_key_error(
    fixture_history, monkeypatch
):
    deletion, owner, _photograph, _metadata = fixture_history
    original_execute = owner.db.execute

    @query_context
    async def delete_then_insert(sql, parameters):
        assert await deletion.delete_by_frigate_event("fav-race") is True
        return await original_execute(sql, parameters)

    def intercept_insert(sql, parameters=()):
        if "INSERT OR IGNORE INTO detection_favorites" in sql:
            return delete_then_insert(sql, parameters)
        return original_execute(sql, parameters)

    monkeypatch.setattr(owner.db, "execute", intercept_insert)
    assert await owner.favorite_detection("fav-race") is None


@pytest.mark.asyncio
async def test_repeating_missing_policy_for_an_absent_row_does_not_remove_files(fixture_history):
    repo, _owner, photograph, metadata = fixture_history
    assert await repo.delete_by_frigate_event("fav-race") is True
    result = await policy.apply_missing_policy(
        repo=repo, frigate_event="fav-race", error="event_not_found", source="fixture", media_kind="any"
    )
    assert result == {"deleted_count": 0, "marked_missing_count": 0, "kept_count": 0}
    assert photograph.is_file() and metadata.is_file()
