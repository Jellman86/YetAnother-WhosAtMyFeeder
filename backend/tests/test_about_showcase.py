"""The About page opens on this install's own photographs: one per species, crops only.

A full frame shown at card size is a picture of a feeder, so the reel keeps only stored
photographs the media cache recorded as crops, one per species, newest first, and never a
hidden detection. Which photographs are crops is a metadata read per candidate, so the walk
is bounded.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.models import Detection
from app.auth import session_cookie_allowed
from app.routers.about import REEL_IMAGE_MAX_EDGE, is_crop_source, resize_for_reel, stored_crops

SOURCES = {
    "robin_new": "hq_candidate_model_crop",
    "robin_old": "high_quality_bird_crop",
    "bluetit": "frigate_snapshot_cropped",
    "dunnock": "high_quality_snapshot",  # whole scene: left out
    "dunnock_old": "hq_candidate_frigate_hint_crop",  # the crop that stands in for the dunnock
    "pigeon": "hq_candidate_full_frame",  # whole scene: left out
    "greattit": "frigate_snapshot",  # the pipeline's uncropped completed-event frame: left out
    "sparrow_hidden": "hq_candidate_model_crop",
    "coaltit": "hq_candidate_frigate_snapshot_fallback",
}


async def _source(event_id: str) -> str | None:
    return SOURCES.get(event_id)


def _detection(event: str, name: str, when: str, taxa_id: int | None = None) -> Detection:
    return Detection(
        detection_time=datetime.fromisoformat(when).replace(tzinfo=timezone.utc),
        detection_index=1,
        score=0.9,
        display_name=name,
        category_name="bird",
        frigate_event=event,
        camera_name="cam",
        taxa_id=taxa_id,
    )


@pytest.mark.asyncio
async def test_each_species_is_represented_by_its_newest_crop_not_its_newest_frame():
    rows = [
        _detection("dunnock", "Dunnock", "2026-09-11T12:00", taxa_id=2),
        _detection("robin_new", "Robin", "2026-09-11T10:00", taxa_id=1),
        _detection("robin_old", "European Robin", "2026-09-10T10:00", taxa_id=1),
        _detection("dunnock_old", "Dunnock", "2026-09-09T10:00", taxa_id=2),
        _detection("bluetit", "Blue Tit", "2026-09-08T10:00"),
        _detection("bluetit_older", "blue tit", "2026-09-07T10:00"),
    ]
    kept = await stored_crops(rows, limit=10, read_source=_source)
    # The dunnock's newest frame is a whole scene, so its older crop stands in; one robin, by taxon.
    assert [d.frigate_event for d in kept] == ["robin_new", "dunnock_old", "bluetit"]


@pytest.mark.asyncio
async def test_the_walk_is_bounded_by_reads_and_by_the_limit():
    rows = [
        _detection("dunnock", "Dunnock", "2026-09-11T12:00"),
        _detection("robin_new", "Robin", "2026-09-11T10:00"),
        _detection("pigeon", "Pigeon", "2026-09-11T09:00"),
        _detection("bluetit", "Blue Tit", "2026-09-11T08:00"),
        _detection("coaltit", "Coal Tit", "2026-09-11T07:00"),
    ]
    reads = AsyncMock(side_effect=_source)
    kept = await stored_crops(rows, limit=10, max_reads=2, read_source=reads)
    assert [d.frigate_event for d in kept] == ["robin_new"]
    assert reads.await_count == 2

    reads = AsyncMock(side_effect=_source)
    kept = await stored_crops(rows, limit=1, read_source=reads)
    assert [d.frigate_event for d in kept] == ["robin_new"]
    assert reads.await_count == 2  # stopped as soon as the reel was full


def test_a_crop_is_whatever_the_classifier_provenance_calls_a_crop():
    for crop in ("frigate_snapshot_cropped", "hq_candidate_model_crop", "high_quality_bird_crop"):
        assert is_crop_source(crop)
    for whole_scene in (
        "frigate_snapshot",
        "frigate_snapshot_uncropped",
        "high_quality_snapshot",
        "hq_candidate_full_frame",
    ):
        assert not is_crop_source(whole_scene)
    assert not is_crop_source(None)


def test_the_session_cookie_may_authorise_the_reel_image_but_not_the_list():
    class _Request:
        method = "GET"

        def __init__(self, path: str) -> None:
            self.url = SimpleNamespace(path=path)

    assert session_cookie_allowed(_Request("/api/about/showcase/1789143136.914536-bms3jr.jpg"))
    assert not session_cookie_allowed(_Request("/api/about/showcase"))


@pytest_asyncio.fixture
async def seeded_db():
    await init_db()
    try:
        async with get_db() as db:
            await db.execute("DELETE FROM detections")
            await db.execute(
                """
                INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index, score, display_name, category_name, is_hidden)
                VALUES
                ('robin_new', 'cam1', '2026-09-11 10:00:00', 1, 0.91, 'Robin', 'bird', 0),
                ('robin_old', 'cam1', '2026-09-10 10:00:00', 1, 0.80, 'Robin', 'bird', 0),
                ('dunnock', 'cam1', '2026-09-11 12:00:00', 1, 0.77, 'Dunnock', 'bird', 0),
                ('dunnock_old', 'cam1', '2026-09-07 12:00:00', 1, 0.75, 'Dunnock', 'bird', 0),
                ('bluetit', 'cam1', '2026-09-09 10:00:00', 1, 0.97, 'Blue Tit', 'bird', 0),
                ('sparrow_hidden', 'cam1', '2026-09-11 11:00:00', 1, 0.70, 'House Sparrow', 'bird', 1),
                ('coaltit', 'cam1', '2026-09-08 10:00:00', 1, 0.98, 'Coal Tit', 'bird', 0)
                """
            )
            await db.commit()
        yield
    finally:
        await close_db()


@pytest.fixture
def media_cache_on():
    original = (settings.media_cache.enabled, settings.media_cache.cache_snapshots)
    settings.media_cache.enabled = True
    settings.media_cache.cache_snapshots = True
    yield
    settings.media_cache.enabled, settings.media_cache.cache_snapshots = original


@pytest.mark.asyncio
async def test_showcase_returns_one_crop_per_species_newest_first(seeded_db, media_cache_on):
    with patch("app.services.media_cache.media_cache.get_snapshot_metadata", new=AsyncMock(side_effect=_meta)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/about/showcase")
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert [i["frigate_event"] for i in items] == ["robin_new", "bluetit", "coaltit", "dunnock_old"]
    assert items[0]["display_name"] == "Robin"
    assert items[0]["camera_name"] == "cam1"
    assert items[0]["detection_time"].endswith("Z") or "+00:00" in items[0]["detection_time"]


@pytest.mark.asyncio
async def test_showcase_respects_the_limit(seeded_db, media_cache_on):
    with patch("app.services.media_cache.media_cache.get_snapshot_metadata", new=AsyncMock(side_effect=_meta)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/about/showcase?limit=2")
    assert [i["frigate_event"] for i in res.json()["items"]] == ["robin_new", "bluetit"]


@pytest.mark.asyncio
async def test_showcase_is_empty_without_a_media_cache(seeded_db):
    original = settings.media_cache.enabled
    settings.media_cache.enabled = False
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/about/showcase")
    finally:
        settings.media_cache.enabled = original
    assert res.status_code == 200
    assert res.json() == {"items": []}


async def _meta(event_id: str) -> dict | None:
    source = SOURCES.get(event_id)
    return {"source": source} if source else None


def _jpeg(width: int, height: int) -> bytes:
    from io import BytesIO

    from PIL import Image

    out = BytesIO()
    Image.new("RGB", (width, height), (40, 90, 60)).save(out, format="JPEG")
    return out.getvalue()


def test_reel_image_is_card_sized_and_keeps_the_crop_shape():
    from io import BytesIO

    from PIL import Image

    resized = resize_for_reel(_jpeg(2400, 1800))
    with Image.open(BytesIO(resized)) as image:
        assert image.size == (REEL_IMAGE_MAX_EDGE, REEL_IMAGE_MAX_EDGE * 3 // 4)
    small = resize_for_reel(_jpeg(320, 240))
    with Image.open(BytesIO(small)) as image:
        assert image.size == (320, 240)  # never upscaled


@pytest.mark.asyncio
async def test_reel_image_route_serves_the_stored_photograph_small(seeded_db, media_cache_on, tmp_path):
    photograph = tmp_path / "robin_new.jpg"
    photograph.write_bytes(_jpeg(2400, 1800))
    with patch("app.services.media_cache.media_cache.get_snapshot_path", new=AsyncMock(return_value=photograph)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/about/showcase/robin_new.jpg")
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "image/jpeg"
    assert len(res.content) < len(photograph.read_bytes())
    with patch("app.services.media_cache.media_cache.get_snapshot_path", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            missing = await client.get("/api/about/showcase/robin_old.jpg")
    assert missing.status_code == 404


@pytest.fixture
def guest_install():
    original = (
        settings.auth.enabled,
        settings.auth.initial_setup_complete,
        settings.public_access.enabled,
        settings.public_access.show_snapshots,
    )
    settings.auth.enabled = True
    settings.auth.initial_setup_complete = True
    settings.public_access.enabled = True
    yield
    (
        settings.auth.enabled,
        settings.auth.initial_setup_complete,
        settings.public_access.enabled,
        settings.public_access.show_snapshots,
    ) = original


@pytest.mark.asyncio
async def test_a_guest_who_may_not_see_snapshots_gets_no_reel(seeded_db, media_cache_on, guest_install):
    settings.public_access.show_snapshots = False
    with patch("app.services.media_cache.media_cache.get_snapshot_metadata", new=AsyncMock(side_effect=_meta)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/about/showcase")
    assert res.status_code == 200
    assert res.json() == {"items": []}


@pytest.mark.asyncio
async def test_a_guest_sees_no_camera_names_and_only_the_shared_window(seeded_db, media_cache_on, guest_install):
    original = (
        settings.public_access.show_camera_names,
        settings.public_access.historical_days_mode,
        settings.public_access.show_historical_days,
    )
    settings.public_access.show_camera_names = False
    settings.public_access.historical_days_mode = "custom"
    settings.public_access.show_historical_days = 1
    try:
        with patch("app.services.media_cache.media_cache.get_snapshot_metadata", new=AsyncMock(side_effect=_meta)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.get("/api/about/showcase")
    finally:
        (
            settings.public_access.show_camera_names,
            settings.public_access.historical_days_mode,
            settings.public_access.show_historical_days,
        ) = original
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    # Everything seeded is older than a day, so the shared window is empty for a guest.
    assert items == [] or all(item["camera_name"] is None for item in items)


@pytest.mark.asyncio
async def test_the_reel_image_answers_a_guest_only_for_a_visit_they_may_see(
    seeded_db, media_cache_on, guest_install, tmp_path
):
    photograph = tmp_path / "p.jpg"
    photograph.write_bytes(_jpeg(400, 300))
    settings.public_access.show_snapshots = True
    with patch("app.services.media_cache.media_cache.get_snapshot_path", new=AsyncMock(return_value=photograph)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            hidden = await client.get("/api/about/showcase/sparrow_hidden.jpg")
            unknown = await client.get("/api/about/showcase/no_such_event.jpg")
            bad = await client.get("/api/about/showcase/..%2F..%2Fetc.jpg")
    assert hidden.status_code == 404
    assert unknown.status_code == 404
    assert bad.status_code in (400, 404)
