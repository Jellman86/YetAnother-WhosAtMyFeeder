"""Public evidence stays mapped, bounded and current before paging and caching."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from app.auth import create_access_token
from app.config import settings
from app.main import app
from app.routers import events, species
from test_guest_privacy_review import private_history as private_history


ROUTES = (
    "/api/events?audio_confirmed_only=true",
    "/api/events/count?audio_confirmed_only=true",
    "/api/events/filters?force_refresh=true",
    "/api/leaderboard/species?span=week",
)


def confirmation_count(route, body):
    if "/count" in route:
        return body["count"]
    if "/filters" in route:
        return body["totals"]["audio_matched"]
    if "/leaderboard/" in route:
        return sum(row["window_audio_confirmed_count"] for row in body["species"])
    return len(body)


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
async def test_public_aggregate_does_not_substitute_another_microphone(private_history, monkeypatch, route):
    _, factory = private_history
    monkeypatch.setattr(settings.frigate, "camera_audio_mapping", {"secret-camera": "micA"})
    monkeypatch.setattr(species.nearby_species_service, "get_report", AsyncMock(return_value=None))
    async with factory() as db:
        await db.execute("UPDATE detections SET audio_confirmed=1,audio_species='Robin' WHERE frigate_event='visible'")
        await db.execute(
            "UPDATE audio_detections SET species='Robin',sensor_id='micA',is_hidden=1 WHERE species='Visible'"
        )
        await db.execute(
            "UPDATE audio_detections SET species='Robin',sensor_id='micB',is_hidden=0 WHERE species='Hidden'"
        )
        await db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get(route)
        projected = await client.get("/api/events")
        owner = await client.get(route, headers={"Authorization": f"Bearer {create_access_token('owner')}"})
    assert response.status_code == 200, response.text
    assert projected.json()[0]["audio_confirmed"] is False
    assert confirmation_count(route, response.json()) == 0
    assert confirmation_count(route, owner.json()) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mapping", "sensor", "payload"),
    [
        ("*", "other", {}),
        (" micA ;other", "MICA", {}),
        ("mic-strasse", "MIC-STRAßE", {}),
        ("micA", "other", {"nm": " MicA "}),
        ("micA", "other", {"sourceName": "micA"}),
        ("micA", "other", {"Source": {"displayName": "micA"}}),
        ("micA", "other", {"src": "micA"}),
        ("micA", "other", {"sourceId": "micA"}),
        ("micA", "other", {"Source": {"id": "micA"}}),
        ("micA", "other", {"id": "micA"}),
        ("micA", "other", {"sensor_id": "micA"}),
    ],
)
async def test_public_mapping_keys_match_projection(private_history, monkeypatch, mapping, sensor, payload):
    _, factory = private_history
    monkeypatch.setattr(settings.frigate, "camera_audio_mapping", {"secret-camera": mapping})
    async with factory() as db:
        await db.execute("UPDATE detections SET audio_confirmed=1,audio_species='Robin' WHERE frigate_event='visible'")
        await db.execute(
            "UPDATE audio_detections SET species='Robin',sensor_id=?,raw_data=? WHERE species='Visible'",
            (sensor, json.dumps(payload)),
        )
        await db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        filtered = await client.get("/api/events?audio_confirmed_only=true")
        count = await client.get("/api/events/count?audio_confirmed_only=true")
    assert filtered.status_code == 200, filtered.text
    assert len(filtered.json()) == 1
    assert filtered.json()[0]["audio_confirmed"] is True
    assert count.json()["count"] == 1


@pytest.mark.asyncio
async def test_public_mapping_filters_before_pagination(private_history, monkeypatch):
    _, factory = private_history
    monkeypatch.setattr(settings.frigate, "camera_audio_mapping", {"secret-camera": "micA"})
    async with factory() as db:
        await db.execute("UPDATE detections SET audio_confirmed=1,audio_species='Robin' WHERE frigate_event='visible'")
        await db.execute("UPDATE audio_detections SET species='Robin',sensor_id='micA' WHERE species='Visible'")
        await db.execute(
            "INSERT INTO detections(frigate_event,camera_name,detection_time,detection_index,score,display_name,category_name,audio_confirmed,audio_species) SELECT 'unmapped','unmapped-camera',datetime(detection_time,'+1 second'),1,.95,'Robin','Robin',1,'Robin' FROM detections WHERE frigate_event='visible'"
        )
        await db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get("/api/events?audio_confirmed_only=true&limit=1")
        count = await client.get("/api/events/count?audio_confirmed_only=true")
    assert [row["frigate_event"] for row in response.json()] == ["visible"]
    assert count.json()["count"] == 1


@pytest.mark.asyncio
async def test_public_page_batches_audio_and_excludes_future_secondary(private_history, monkeypatch):
    today, factory = private_history
    edge = today + timedelta(hours=23, minutes=59, seconds=59)
    async with factory() as db:
        await db.execute("DELETE FROM detections")
        await db.execute("DELETE FROM audio_detections")
        for i in range(20):
            await db.execute(
                "INSERT INTO detections(frigate_event,camera_name,detection_time,detection_index,score,display_name,category_name,audio_confirmed,audio_species) VALUES(?,'secret-camera',?,1,.9,'Robin','Robin',0,'Robin')",
                (f"edge-{i}", edge.replace(tzinfo=None).isoformat(sep=" ")),
            )
        for stamp, label in [(edge, "Robin"), (edge + timedelta(seconds=2), "TOMORROW_SECONDARY")]:
            await db.execute(
                "INSERT INTO audio_detections(timestamp,species,confidence,sensor_id,raw_data,is_hidden) VALUES(?,?,.9,'micA','{}',0)",
                (stamp.replace(tzinfo=None).isoformat(sep=" "), label),
            )
        await db.commit()
    queries = []

    @asynccontextmanager
    async def traced_db():
        async with factory() as db:
            await db.set_trace_callback(queries.append)
            yield db

    monkeypatch.setattr(events, "get_db", traced_db)
    monkeypatch.setattr(events, "localize_audio_species_name", AsyncMock(side_effect=lambda name, lang, db: name))
    monkeypatch.setattr(events, "localize_audio_detections", AsyncMock())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get("/api/events?limit=20")
    assert response.status_code == 200, response.text
    assert len(response.json()) == 20
    assert all(row["audio_context_species"] == ["Robin"] for row in response.json())
    assert (
        sum("audio_detections" in query and query.lstrip().upper().startswith(("SELECT", "WITH")) for query in queries)
        <= 2
    )


@pytest.mark.asyncio
async def test_public_portraits_revalidate_cached_hidden_photo(private_history, monkeypatch):
    today, factory = private_history
    monkeypatch.setattr(settings.media_cache, "enabled", True)
    monkeypatch.setattr(settings.media_cache, "cache_snapshots", True)
    monkeypatch.setattr(settings.public_access, "media_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "media_historical_days", 7)
    monkeypatch.setattr(settings.public_access, "show_historical_days", 7)
    from app.services.media_cache import media_cache

    monkeypatch.setattr(
        media_cache, "get_snapshot_metadata", AsyncMock(return_value={"source": "hq_candidate_model_crop"})
    )
    species.clear_portraits_cache()
    async with factory() as db:
        await db.execute("DELETE FROM detections")
        for event, offset in [("portrait-new", 1), ("portrait-old", 2)]:
            await db.execute(
                "INSERT INTO detections(frigate_event,camera_name,detection_time,detection_index,score,display_name,category_name) VALUES(?,'secret-camera',?,1,.9,'Robin','Robin')",
                (
                    event,
                    (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=offset)).isoformat(sep=" "),
                ),
            )
        await db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        warm = await client.get("/api/leaderboard/portraits?span=day")
        hidden = await client.post(
            "/api/events/portrait-new/hide", headers={"Authorization": f"Bearer {create_access_token('owner')}"}
        )
        response = await client.get("/api/leaderboard/portraits?span=day")
    assert warm.json()["portraits"][0]["frigate_event"] == "portrait-new"
    assert hidden.status_code == 200
    assert response.json()["portraits"][0]["frigate_event"] == "portrait-old"
    species.clear_portraits_cache()


@pytest.mark.asyncio
@pytest.mark.parametrize("precision,expected", [("approximate", (51.5, -0.1)), ("exact", (51.5074, -0.1278))])
async def test_manual_coordinates_use_guest_precision_and_preserve_owner(
    private_history, monkeypatch, precision, expected
):
    today, factory = private_history
    monkeypatch.setattr(settings.public_access, "location_precision", precision)
    from app.repositories.manual_observation_repository import ManualObservationDraft, ManualObservationRepository

    async with factory() as db:
        await db.execute(
            "INSERT INTO detections(frigate_event,camera_name,detection_time,detection_index,score,display_name,category_name) VALUES('manual_pin','manual',?,1,.9,'Robin','Robin')",
            ((today + timedelta(seconds=1)).replace(tzinfo=None).isoformat(sep=" "),),
        )
        await db.commit()
        repo = ManualObservationRepository(db)
        await repo.create(
            ManualObservationDraft(
                id="manual-pin-draft",
                status="ready",
                media_type="photo",
                original_filename="fixture.jpg",
                content_type="image/jpeg",
                content_sha256="fixture-sha",
                size_bytes=1,
                source_filename="fixture.jpg",
            )
        )
        await repo.mark_saved(
            "manual-pin-draft", "manual_pin", None, latitude=51.5074, longitude=-0.1278, location_source="manual"
        )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        guest = await client.get("/api/events?event_id=manual_pin")
        owner = await client.get(
            "/api/events?event_id=manual_pin", headers={"Authorization": f"Bearer {create_access_token('owner')}"}
        )
    assert guest.status_code == 200, guest.text
    assert (guest.json()[0]["observation_latitude"], guest.json()[0]["observation_longitude"]) == expected
    assert (owner.json()[0]["observation_latitude"], owner.json()[0]["observation_longitude"]) == (51.5074, -0.1278)


@pytest.mark.asyncio
async def test_public_audio_batch_bounds_rows_and_chunks_before_mapping(private_history, monkeypatch):
    today, factory = private_history
    monkeypatch.setattr(settings.frigate, "camera_audio_mapping", {"secret-camera": "micA"})
    from app.repositories.detection_repository import DetectionRepository

    async with factory() as db:
        await db.execute("DELETE FROM detections")
        await db.execute("DELETE FROM audio_detections")
        for i in range(51):
            await db.execute(
                "INSERT INTO detections(frigate_event,camera_name,detection_time,detection_index,score,display_name,category_name,audio_confirmed,audio_species) VALUES(?,'secret-camera',?,1,.9,'Robin','Robin',0,' Robin ')",
                (f"bounded-{i}", (today + timedelta(seconds=2)).replace(tzinfo=None).isoformat(sep=" ")),
            )
        for i in range(30):
            await db.execute(
                "INSERT INTO audio_detections(timestamp,species,confidence,sensor_id,raw_data,is_hidden) VALUES(?,'Other',.99,'micA','{}',0)",
                ((today + timedelta(seconds=2)).replace(tzinfo=None).isoformat(sep=" "),),
            )
        await db.execute(
            "INSERT INTO audio_detections(timestamp,species,confidence,sensor_id,raw_data,is_hidden) VALUES(?,'Robin',.1,'micA','not-json',0)",
            ((today + timedelta(seconds=3)).replace(tzinfo=None).isoformat(sep=" "),),
        )
        await db.commit()
        repo = DetectionRepository(db)
        targets = await repo.get_all(limit=51)
        queries = []
        await db.set_trace_callback(queries.append)
        evidence = await repo.get_public_audio_for_detections(targets)
        plans = []
        for query in list(queries):
            if query.lstrip().startswith("WITH d("):
                async with db.execute("EXPLAIN QUERY PLAN " + query) as cursor:
                    plans.extend(await cursor.fetchall())
    assert any("SEARCH a USING INDEX" in row[3] and "timestamp>?" in row[3] for row in plans)
    assert len(evidence) == 51
    assert all(row["primary"]["species"] == "Robin" for row in evidence.values())
    assert all(len(row["context"]) == 8 for row in evidence.values())
    assert sum(query.lstrip().startswith("WITH d(") for query in queries) == 2
    assert all("raw_data" not in item for row in evidence.values() for item in [row["primary"], *row["context"]])


@pytest.mark.asyncio
async def test_public_portraits_apply_window_before_species_limit(private_history, monkeypatch):
    today, factory = private_history
    monkeypatch.setattr(settings.media_cache, "enabled", True)
    monkeypatch.setattr(settings.media_cache, "cache_snapshots", True)
    monkeypatch.setattr(settings.public_access, "media_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "media_historical_days", 0)
    from app.services.media_cache import media_cache

    monkeypatch.setattr(
        media_cache, "get_snapshot_metadata", AsyncMock(return_value={"source": "hq_candidate_model_crop"})
    )
    species.clear_portraits_cache()
    async with factory() as db:
        await db.execute("DELETE FROM detections")
        for i in range(4):
            await db.execute(
                "INSERT INTO detections(frigate_event,camera_name,detection_time,detection_index,score,display_name,category_name) VALUES(?,'secret-camera',?,1,.9,'PrivateOld','PrivateOld')",
                (f"old-{i}", (today - timedelta(days=1)).replace(tzinfo=None).isoformat(sep=" ")),
            )
        await db.execute(
            "INSERT INTO detections(frigate_event,camera_name,detection_time,detection_index,score,display_name,category_name) VALUES('current','secret-camera',?,1,.9,'Robin','Robin')",
            ((today + timedelta(seconds=1)).replace(tzinfo=None).isoformat(sep=" "),),
        )
        await db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.get("/api/leaderboard/portraits?span=week&limit=1")
    assert response.status_code == 200, response.text
    assert [row["frigate_event"] for row in response.json()["portraits"]] == ["current"]
    species.clear_portraits_cache()


@pytest.mark.asyncio
@pytest.mark.parametrize("public_days", [0, 7])
async def test_public_audio_lookup_work_depends_on_capture_window_not_shared_history(
    private_history, monkeypatch, public_days
):
    today, factory = private_history
    monkeypatch.setattr(settings.public_access, "show_historical_days", public_days)
    from app.repositories.detection_repository import DetectionRepository

    capture_time = today + timedelta(hours=12)
    stamp = capture_time.replace(tzinfo=None).isoformat(sep=" ")
    unrelated_stamp = (today + timedelta(hours=2)).replace(tzinfo=None).isoformat(sep=" ")
    async with factory() as db:
        await db.execute("DELETE FROM detections")
        await db.execute("DELETE FROM audio_detections")
        await db.execute(
            "INSERT INTO detections(frigate_event,camera_name,detection_time,detection_index,score,display_name,category_name,audio_confirmed,audio_species) VALUES('capture','secret-camera',?,1,.9,'Robin','Robin',1,'Robin')",
            (stamp,),
        )
        await db.executemany(
            "INSERT INTO audio_detections(timestamp,species,confidence,sensor_id,raw_data,is_hidden) VALUES(?,'Robin',.99,'micA','{}',0)",
            [(unrelated_stamp,)] * 1000,
        )
        await db.execute(
            "INSERT INTO audio_detections(timestamp,species,confidence,sensor_id,raw_data,is_hidden) VALUES(?,'Robin',.75,'micA','{}',0)",
            (stamp,),
        )
        await db.commit()
        calls = 0
        register = db.create_function

        async def counted_registration(name, arity, function, **kwargs):
            if name == "public_audio_window_bound":
                original = function

                def counted(*args):
                    nonlocal calls
                    calls += 1
                    return original(*args)

                function = counted
            await register(name, arity, function, **kwargs)

        monkeypatch.setattr(db, "create_function", counted_registration)
        repo = DetectionRepository(db)
        evidence = await repo.get_public_audio_for_detections(await repo.get_all())
    assert evidence["capture"]["primary"]["confidence"] == 0.75
    assert evidence["capture"]["context"] == []
    assert calls < 20, "The indexed capture lookup scanned unrelated shared audio history"


@pytest.mark.asyncio
@pytest.mark.parametrize("public_days", [0, 7])
@pytest.mark.parametrize("seconds", [0, 120])
@pytest.mark.parametrize("capture_offset", [0, 12 * 3600, 24 * 3600 - 1])
async def test_public_audio_indexed_bounds_preserve_midnight_and_capture_edges(
    private_history, monkeypatch, public_days, seconds, capture_offset
):
    from app.repositories.detection_repository import _public_audio_conditions_sql
    from app.utils.api_datetime import serialize_storage_datetime
    from app.utils.public_access import public_events_window

    today, factory = private_history
    monkeypatch.setattr(settings.public_access, "show_historical_days", public_days)
    monkeypatch.setattr(settings.frigate, "audio_correlation_window_seconds", seconds)
    target = today + timedelta(seconds=capture_offset)
    cutoff, end = public_events_window(today)
    samples = sorted(
        {
            cutoff - timedelta(microseconds=1),
            cutoff,
            today,
            today + timedelta(days=1) - timedelta(microseconds=1),
            today + timedelta(days=1),
            target - timedelta(seconds=seconds, microseconds=1),
            target - timedelta(seconds=seconds),
            target,
            target + timedelta(seconds=seconds),
            target + timedelta(seconds=seconds, microseconds=1),
        }
    )
    async with factory() as db:
        await db.execute("DELETE FROM audio_detections")
        await db.executemany(
            "INSERT INTO audio_detections(timestamp,species,confidence,sensor_id,raw_data,is_hidden) VALUES(?,'Robin',.9,'micA','{}',0)",
            [(serialize_storage_datetime(stamp),) for stamp in samples],
        )
        sql, params = await _public_audio_conditions_sql(db)
        query = f"""WITH d(camera_name,detection_time,audio_species) AS (VALUES (?,?,?))
            SELECT a.timestamp FROM d JOIN audio_detections a ON {sql} ORDER BY a.timestamp"""
        async with db.execute(query, ["secret-camera", serialize_storage_datetime(target), "Robin", *params]) as cursor:
            actual = [row[0] for row in await cursor.fetchall()]
    expected = [
        serialize_storage_datetime(stamp)
        for stamp in samples
        if stamp >= cutoff
        and (end is None or stamp < end)
        and target - timedelta(seconds=seconds) <= stamp <= target + timedelta(seconds=seconds)
    ]
    assert actual == expected
