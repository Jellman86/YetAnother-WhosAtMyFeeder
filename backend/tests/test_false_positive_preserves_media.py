"""Frigate withdrawing its object must not destroy recoverable owner media."""

import asyncio
from contextlib import asynccontextmanager, closing
from datetime import datetime
import json
import os
import sqlite3
import time
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
from PIL import Image
import pytest

from app.repositories.detection_repository import Detection, DetectionRepository
from app.services import event_processor as module
from app.services import media_cache as cache_module
from app.services.mqtt_service import MQTTService


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "manual_tagged, chosen_photo, concurrent_tag",
    [(True, False, False), (False, True, False), (False, False, False), (False, True, True)],
)
async def test_admitted_false_positive_keeps_photograph_and_sidecars(
    tmp_path, monkeypatch, manual_tagged, chosen_photo, concurrent_tag
):
    path = tmp_path / "history.db"
    with closing(sqlite3.connect(os.environ["DB_PATH"])) as source, closing(sqlite3.connect(path)) as target:
        source.backup(target)
        target.execute("DELETE FROM detections")
        target.commit()

    @asynccontextmanager
    async def database():
        async with aiosqlite.connect(path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            yield db

    monkeypatch.setattr(module, "get_db", database)
    for name in ("SNAPSHOTS_DIR", "CLIPS_DIR", "PREVIEWS_DIR"):
        directory = tmp_path / name.lower()
        directory.mkdir()
        monkeypatch.setattr(cache_module, name, directory)
    cache = cache_module.MediaCacheService()
    monkeypatch.setattr(module, "media_cache", cache)
    async with database() as db:
        await DetectionRepository(db).create(
            Detection(datetime.now(), 1, 0.9, "Robin", "Robin", "owner-photo", "camera", manual_tagged=manual_tagged)
        )
    photograph = cache_module.SNAPSHOTS_DIR / "owner-photo.jpg"
    Image.new("RGB", (24, 24), color="red").save(photograph)
    await cache.set_manual_snapshot_selection("owner-photo", chosen_photo)
    before = photograph.read_bytes()
    metadata = await cache.get_snapshot_metadata("owner-photo")
    if concurrent_tag:
        original_hide = DetectionRepository.hide_detection

        async def tag_then_hide(repo, event_id, **kwargs):
            async with database() as owner_db:
                await owner_db.execute("UPDATE detections SET manual_tagged = 1 WHERE frigate_event = ?", (event_id,))
                await owner_db.commit()
            return await original_hide(repo, event_id, **kwargs)

        monkeypatch.setattr(DetectionRepository, "hide_detection", tag_then_hide)
    classifier = MagicMock()
    classifier.classify_async_live = AsyncMock(side_effect=AssertionError("False positives do not need inference"))
    processor = module.EventProcessor(classifier)
    payload = json.dumps(
        {
            "type": "update",
            "after": {
                "id": "owner-photo",
                "camera": "camera",
                "label": "bird",
                "start_time": time.time(),
                "false_positive": True,
            },
        }
    ).encode()
    mqtt = MQTTService()
    mqtt.running = True
    try:
        meta = mqtt._parse_frigate_payload_meta(payload)
        assert meta["should_process"]
        await asyncio.wait_for(mqtt._schedule_frigate_message(processor, payload, event_id=meta["event_id"]), timeout=3)
        # Duplicate terminal withdrawal remains idempotent and keeps recovery media.
        await processor.process_mqtt_message(payload)
    finally:
        await mqtt.stop()
    async with database() as db:
        detection = await DetectionRepository(db).get_by_frigate_event("owner-photo")
    assert detection is not None
    assert detection.is_hidden is not (manual_tagged or concurrent_tag)
    assert photograph.is_file() and photograph.read_bytes() == before
    assert await cache.get_snapshot_metadata("owner-photo") == metadata
    classifier.classify_async_live.assert_not_awaited()
