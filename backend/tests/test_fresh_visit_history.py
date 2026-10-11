"""Fresh migrated history and out-of-order imports share the live visit rules."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from io import BytesIO
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import httpx
from PIL import Image
import pytest
import pytest_asyncio

from app.repositories.bird_observation_repository import BirdObservationRepository
from app.repositories.visit_repository import VisitRepository
from app.services import backfill_service as backfill_module
from app.services import detection_service as detection_module
from app.services.species_catalog_resolver import ShadowResolution
from app.services import media_cache as media_cache_module


START = datetime(2033, 10, 3, 10)


@pytest.fixture(scope="module")
def fresh_history_template(tmp_path_factory):
    path = tmp_path_factory.mktemp("fresh-visit-schema") / "template.db"
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "DB_PATH": str(path)},
        check=True,
        capture_output=True,
        timeout=60,
    )
    return path


@pytest_asyncio.fixture
async def history(tmp_path, fresh_history_template, monkeypatch):
    from app.config import settings
    from app.routers import events, stats, visits
    from app.services.broadcaster import broadcaster

    path = tmp_path / "fresh-history.db"
    shutil.copyfile(fresh_history_template, path)

    @asynccontextmanager
    async def database():
        async with aiosqlite.connect(path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            yield db

    for module in (events, stats, visits, detection_module):
        monkeypatch.setattr(module, "get_db", database)
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    monkeypatch.setattr(settings, "api_key", None)
    monkeypatch.setattr(media_cache_module.media_cache, "_available", False)
    for key, value in {
        "threshold": 0.6,
        "min_confidence": 0.6,
        "trust_frigate_sublabel": False,
        "blocked_labels": [],
        "blocked_species": [],
    }.items():
        monkeypatch.setattr(settings.classification, key, value)
    monkeypatch.setattr(stats, "utc_naive_now", lambda: START + timedelta(hours=1))
    clips = AsyncMock(return_value={})
    monkeypatch.setattr(events, "batch_check_clips", clips)
    broadcast = AsyncMock()
    monkeypatch.setattr(broadcaster, "broadcast", broadcast)
    classifier = MagicMock()
    classifier.classify_async_background = AsyncMock(
        return_value=[{"label": "Turdus merula", "score": 0.85, "index": 2}]
    )
    monkeypatch.setattr(detection_module.taxonomy_service, "get_names", AsyncMock(return_value={}))
    monkeypatch.setattr(
        detection_module, "_catalog_shadow_resolution", AsyncMock(return_value=ShadowResolution(verdict="unavailable"))
    )
    monkeypatch.setattr(detection_module.birdweather_service, "report_detection", AsyncMock(return_value=False))
    image = BytesIO()
    Image.new("RGB", (32, 32), "green").save(image, "JPEG")
    snapshot = AsyncMock(return_value=image.getvalue())
    monkeypatch.setattr(backfill_module.frigate_client, "get_snapshot", snapshot)

    async def keep_snapshot(event_id, event, data, provenance):
        return data, provenance

    monkeypatch.setattr(backfill_module, "prefer_recording_snapshot", keep_snapshot)
    yield SimpleNamespace(
        database=database,
        classifier=classifier,
        broadcast=broadcast,
        service=backfill_module.BackfillService(classifier),
        snapshot=snapshot,
        clips=clips,
    )


@pytest.mark.asyncio
async def test_fresh_database_empty_visits_filters_and_stats_do_not_start_media_work(history):
    from app.main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for suffix in ("", "?multiple_species_only=true", "?offset=100&multiple_species_only=true"):
            response = await client.get("/api/visits" + suffix)
            assert response.status_code == 200, response.text
            assert response.json() == {"visits": [], "total": 0, "gap_seconds": 60}
        missing = await client.get("/api/visits/not-imported-yet/captures")
        assert missing.status_code == 404
        for url in ("/api/events?multiple_species_only=true", "/api/events/count?multiple_species_only=true"):
            response = await client.get(url)
            assert response.status_code == 200, response.text
            assert response.json()["count"] == 0 if "/count" in url else response.json() == []
        summary = await client.get("/api/stats/daily-summary")
        assert summary.status_code == 200, summary.text
        data = summary.json()
        assert data["total_count"] == data["visit_count"] == data["counted_birds"] == data["counted_captures"] == 0
        assert data["top_species"] == data["camera_visits"] == []
        assert data["latest_detection"] is None
        assert data["hourly_visits"] == data["hourly_distribution"] == [0] * 24
    history.classifier.classify_async_background.assert_not_awaited()
    history.snapshot.assert_not_awaited()
    history.broadcast.assert_not_awaited()


@pytest.mark.asyncio
async def test_out_of_order_backfill_recomputes_complete_visits_without_count_inference(history):
    stamp = START.replace(tzinfo=timezone.utc).timestamp()
    durations = {0: 180, 20: 30, 160: 170, 250: 260}
    for seconds in (160, 250, 20, 0):
        event = {
            "id": f"fresh-backfill-{seconds}",
            "camera": "birdcam",
            "start_time": stamp + seconds,
            "end_time": stamp + durations[seconds],
            "top_score": 0.95,
        }
        assert await history.service.process_historical_event(event) == ("new", None)
    assert history.classifier.classify_async_background.await_count == 4
    assert history.broadcast.await_count == 4
    async with history.database() as db:
        repo = VisitRepository(db)
        rows, total = await repo.list_visits(start=START, end=START + timedelta(minutes=10), sort="oldest")
        assert total == 2
        assert [(row["visit_id"], row["capture_count"]) for row in rows] == [
            ("fresh-backfill-0", 3),
            ("fresh-backfill-250", 1),
        ]
        captures, capture_count = await repo.visit_captures("fresh-backfill-0")
        assert capture_count == 3
        assert [capture.frigate_event for capture in captures] == [
            "fresh-backfill-0",
            "fresh-backfill-20",
            "fresh-backfill-160",
        ]
        assert len(await repo.get_window_visit_openings(START, START + timedelta(minutes=10))) == total
        assert (
            sum(row["visit_count"] for row in await repo.get_daily_species_counts(START, START + timedelta(minutes=10)))
            == total
        )
        assert await repo.get_daily_visit_counts(start_date=START, end_date=START + timedelta(minutes=10)) == {
            "2033-10-03": total
        }
        assert (await repo.list_visits(multiple_species_only=True))[1] == 0
        assert await BirdObservationRepository(db).count_visible_between(START, START + timedelta(minutes=10)) == {
            "birds": 0,
            "captures": 0,
        }
        async with db.execute("SELECT COUNT(*) FROM bird_observations") as cursor:
            assert (await cursor.fetchone())[0] == 0
    # Querying derived visits adds no inference, Frigate calls or SSE traffic.
    assert history.classifier.classify_async_background.await_count == history.snapshot.await_count == 4
    assert history.broadcast.await_count == 4


@pytest.mark.asyncio
async def test_unknown_manual_and_hidden_imports_cannot_bridge_visible_known_visits(history):
    stamp = START.replace(tzinfo=timezone.utc).timestamp()
    fixtures = [
        ("known-first", 0, "Turdus merula", 0),
        ("known-last", 200, "Turdus merula", 0),
        ("hidden-bridge", 100, "Turdus merula", 1),
        ("unknown-first", 0, "Unknown Bird", 0),
        ("unknown-last", 20, "Unknown Bird", 0),
        ("manual_first", 0, "Turdus merula", 0),
        ("manual_last", 20, "Turdus merula", 0),
    ]
    async with history.database() as db:
        repo = VisitRepository(db)
        for event, seconds, species, hidden in fixtures:
            await db.execute(
                """INSERT INTO detections (frigate_event,detection_time,detection_index,score,display_name,
                   category_name,scientific_name,camera_name,is_hidden) VALUES (?,?,0,.85,?,?,?,'birdcam',?)""",
                (
                    event,
                    (START + timedelta(seconds=seconds)).isoformat(sep=" "),
                    species,
                    species,
                    None if species == "Unknown Bird" else species,
                    hidden,
                ),
            )
            await db.commit()
            saved = await repo.save_event_bounds(
                event, stamp + seconds, stamp + seconds + (180 if event != "known-first" else 10)
            )
            assert saved == (not event.startswith("manual_"))
        rows, total = await repo.list_visits(start=START, end=START + timedelta(minutes=10))
        assert total == 6
        assert all(row["capture_count"] == 1 for row in rows)
        assert "hidden-bridge" not in {row["visit_id"] for row in rows}
        assert (
            sum(row["visit_count"] for row in await repo.get_daily_species_counts(START, START + timedelta(minutes=10)))
            == total
        )
        assert len(await repo.get_window_visit_openings(START, START + timedelta(minutes=10))) == total
        assert (await repo.list_visits(multiple_species_only=True))[1] == 0
    history.classifier.classify_async_background.assert_not_awaited()
    history.broadcast.assert_not_awaited()
