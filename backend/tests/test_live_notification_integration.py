"""MQTT -> real classifier policy -> migrated SQLite -> real notification queue.

Only model inference, media/taxonomy/weather and the outbound channel are fake.
No real feeder, broker, model download or Telegram account is used.
"""

import asyncio
from contextlib import asynccontextmanager
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
from PIL import Image
import pytest
import pytest_asyncio

from app.config import settings
from app.repositories.detection_repository import DetectionRepository
from app.services import detection_service as detection_module
from app.services import event_processor as event_module
from app.services import notification_orchestrator as notification_module
from app.services.notification_dispatcher import NotificationDispatcher
from app.services.notification_service import NotificationService
from app.services.species_catalog_resolver import ShadowResolution


@pytest.fixture(scope="module")
def pipeline_schema(tmp_path_factory):
    path = tmp_path_factory.mktemp("pipeline-schema") / "template.db"
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "DB_PATH": str(path)},
        check=True,
        capture_output=True,
    )
    return path


@pytest_asyncio.fixture
async def pipeline(tmp_path, monkeypatch, pipeline_schema):
    path = tmp_path / "pipeline.db"
    shutil.copyfile(pipeline_schema, path)

    @asynccontextmanager
    async def database():
        async with aiosqlite.connect(path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            yield db

    for module in (detection_module, event_module, notification_module):
        monkeypatch.setattr(module, "get_db", database)
    for name, value in {
        "threshold": 0.6,
        "min_confidence": 0.6,
        "trust_frigate_sublabel": False,
        "blocked_labels": [],
        "blocked_species": [],
        "auto_video_classification": False,
        "write_frigate_sublabel": False,
    }.items():
        monkeypatch.setattr(settings.classification, name, value)
    monkeypatch.setattr(settings.media_cache, "enabled", False)
    monkeypatch.setattr(settings.notifications, "mode", "final")
    monkeypatch.setattr(settings.notifications, "delay_until_video", False)
    monkeypatch.setattr(settings.notifications, "notification_cooldown_minutes", 0)
    monkeypatch.setattr(settings.notifications.filters, "min_confidence", 0.6)
    monkeypatch.setattr(settings.notifications.filters, "audio_confirmed_only", False)
    monkeypatch.setattr(settings.notifications.filters, "camera_filters", {})
    monkeypatch.setattr(settings.notifications.filters, "species_mode", "none")
    for channel in ("telegram", "discord", "pushover", "email"):
        monkeypatch.setattr(getattr(settings.notifications, channel), "enabled", channel == "telegram")
    monkeypatch.setattr(settings.notifications.telegram, "include_snapshot", True)
    monkeypatch.setattr(event_module.taxonomy_service, "get_names", AsyncMock(return_value={}))
    monkeypatch.setattr(event_module.audio_service, "find_match", AsyncMock(return_value=None))
    monkeypatch.setattr(event_module.weather_service, "get_current_weather", AsyncMock(return_value={}))
    monkeypatch.setattr(detection_module.birdweather_service, "report_detection", AsyncMock(return_value=False))
    monkeypatch.setattr(
        detection_module, "_catalog_shadow_resolution", AsyncMock(return_value=ShadowResolution(verdict="unavailable"))
    )
    image = BytesIO()
    Image.new("RGB", (32, 32), "green").save(image, "JPEG")
    snapshot = AsyncMock(return_value=(image.getvalue(), None))
    monkeypatch.setattr(event_module.frigate_client, "get_snapshot_with_error", snapshot)
    # The event has expired by notification time. Delivery must work without media.
    expired_snapshot = AsyncMock(return_value=None)
    monkeypatch.setattr(event_module.frigate_client, "get_snapshot", expired_snapshot)
    monkeypatch.setattr(event_module.frigate_client, "get_thumbnail", AsyncMock(return_value=None))
    monkeypatch.setattr(
        event_module.frigate_client, "get_recording_clip_with_error", AsyncMock(return_value=(None, "not_found"))
    )
    monkeypatch.setattr(event_module.media_cache, "get_snapshot", AsyncMock(return_value=None))
    classifier = MagicMock()
    classifier.classify_async_live = AsyncMock(
        return_value=[{"label": "Prunella modularis", "score": 0.95, "index": 2}]
    )
    dispatcher = NotificationDispatcher()
    monkeypatch.setattr(event_module, "notification_dispatcher", dispatcher)
    notifications = NotificationService()
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(notifications, "_send_telegram", send)
    monkeypatch.setattr(notification_module, "notification_service", notifications)
    processor = event_module.EventProcessor(classifier)
    await dispatcher.start()

    async def deliver(kind):
        await processor.process_mqtt_message(
            json.dumps(
                {
                    "type": kind,
                    "after": {
                        "id": "pipeline-event",
                        "label": "bird",
                        "camera": "test-feeder",
                        "start_time": time.time() - 1,
                        "end_time": time.time() if kind == "end" else None,
                    },
                }
            ).encode()
        )
        await asyncio.wait_for(dispatcher._queue.join(), timeout=3)

    async def stored():
        async with database() as db:
            return await DetectionRepository(db).get_by_frigate_event("pipeline-event")

    try:
        yield SimpleNamespace(
            deliver=deliver,
            stored=stored,
            classifier=classifier,
            send=send,
            database=database,
            expired_snapshot=expired_snapshot,
            snapshot=snapshot,
            image=image.getvalue(),
        )
    finally:
        await dispatcher.stop()
        await notifications.client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,at_new,at_end", [("standard", 1, 1), ("final", 0, 1), ("silent", 0, 0)])
async def test_notification_modes_persist_once_across_duplicate_updates_and_ends(
    pipeline, monkeypatch, mode, at_new, at_end
):
    monkeypatch.setattr(settings.notifications, "mode", mode)
    await pipeline.deliver("new")
    assert (await pipeline.stored()).score == pytest.approx(0.95)
    assert pipeline.send.await_count == at_new
    await pipeline.deliver("update")
    assert pipeline.send.await_count == at_new
    await pipeline.deliver("end")
    await pipeline.deliver("end")
    assert pipeline.send.await_count == at_end
    assert bool((await pipeline.stored()).notified_at) is bool(at_end)
    pipeline.classifier.classify_async_live.assert_awaited_once()
    async with pipeline.database() as db:
        assert (await (await db.execute("SELECT COUNT(*) FROM detections")).fetchone())[0] == 1
        assert (await (await db.execute("PRAGMA integrity_check")).fetchone())[0] == "ok"


@pytest.mark.asyncio
async def test_failed_delivery_is_not_marked_sent_and_can_retry_on_end(pipeline):
    pipeline.send.side_effect = [False, True]
    await pipeline.deliver("new")
    await pipeline.deliver("end")
    assert (await pipeline.stored()).notified_at is None
    await pipeline.deliver("end")
    assert (await pipeline.stored()).notified_at is not None
    assert pipeline.send.await_count == 2
    assert pipeline.send.await_args.args[5] is None  # expired media does not suppress text delivery
    pipeline.expired_snapshot.assert_awaited()


@pytest.mark.asyncio
async def test_filtered_detection_is_neither_saved_nor_notified_on_end(pipeline):
    pipeline.classifier.classify_async_live.return_value[0]["score"] = 0.2
    await pipeline.deliver("new")
    await pipeline.deliver("end")
    assert await pipeline.stored() is None
    pipeline.send.assert_not_awaited()
    pipeline.classifier.classify_async_live.assert_awaited_once()


@pytest.mark.asyncio
async def test_terminal_event_recovers_missing_initial_detection_and_notifies(pipeline):
    await pipeline.deliver("end")
    assert (await pipeline.stored()).notified_at is not None
    pipeline.send.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["snapshot_missing", "inference_timeout"])
async def test_update_recovers_a_transient_failure_without_losing_final_notification(pipeline, failure):
    if failure == "snapshot_missing":
        pipeline.snapshot.return_value = (None, "snapshot_not_found")
    else:
        pipeline.classifier.classify_async_live.side_effect = [
            asyncio.TimeoutError(),
            [{"label": "Prunella modularis", "score": 0.95, "index": 2}],
        ]
    await pipeline.deliver("new")
    assert await pipeline.stored() is None
    pipeline.send.assert_not_awaited()
    pipeline.snapshot.return_value = (pipeline.image, None)
    await pipeline.deliver("update")
    assert await pipeline.stored() is not None
    await pipeline.deliver("end")
    assert (await pipeline.stored()).notified_at is not None
    pipeline.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_frigate_writeback_outage_cannot_lose_saved_detection_or_notification(pipeline, monkeypatch):
    monkeypatch.setattr(settings.classification, "write_frigate_sublabel", True)
    writeback = AsyncMock(side_effect=OSError("Frigate unavailable"))
    monkeypatch.setattr(event_module.frigate_client, "set_sublabel", writeback)
    await pipeline.deliver("new")
    writeback.assert_awaited_once()
    assert await pipeline.stored() is not None
    await pipeline.deliver("end")
    assert (await pipeline.stored()).notified_at is not None
    pipeline.send.assert_awaited_once()
