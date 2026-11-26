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
from app.auth import AuthLevel, SESSION_COOKIE, create_access_token, session_cookie_allowed
from app.routers.about import (
    REEL_IMAGE_MAX_EDGE,
    REEL_TILE_MAX_EDGE,
    is_crop_source,
    newest_photographed_visit,
    resize_for_reel,
    stored_crops,
)
from app.services import media_cache as media_cache_module
from app.services.frigate_client import frigate_client
from app.services.reel_image_service import reel_image_service

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


@pytest.mark.asyncio
async def test_the_latest_visit_prefers_a_crop_but_never_claims_no_picture_while_one_is_stored():
    rows = [
        _detection("unphotographed", "Wren", "2026-09-11T13:00"),
        _detection("greattit", "Great Tit", "2026-09-11T12:00"),
        _detection("pigeon", "Pigeon", "2026-09-11T11:00"),
        _detection("robin_new", "Robin", "2026-09-11T10:00"),
    ]

    async def stored(event_id: str) -> bool:
        return event_id in SOURCES

    newest = await newest_photographed_visit(rows, max_reads=20, read_source=_source, has_photograph=stored)
    assert newest is not None and newest.frigate_event == "robin_new"

    # No crop in reach: the newest whole-scene photograph stands in, rather than "no picture".
    newest = await newest_photographed_visit(rows[:3], max_reads=20, read_source=_source, has_photograph=stored)
    assert newest is not None and newest.frigate_event == "greattit"

    # Nothing stored at all is the only case with no picture, and the walk stays bounded.
    checks = AsyncMock(return_value=False)
    assert await newest_photographed_visit(rows, max_reads=2, read_source=_source, has_photograph=checks) is None
    assert checks.await_count == 2


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


@pytest.fixture(autouse=True)
def reset_reel_image_caches():
    reel_image_service.reset()
    frigate_client.readiness.reset()
    yield
    reel_image_service.reset()
    frigate_client.readiness.reset()


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
    original = media_cache_module.media_cache._available
    media_cache_module.media_cache._available = True
    yield
    media_cache_module.media_cache._available = original


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
    with (
        patch("app.services.media_cache.media_cache.get_snapshot_path", new=AsyncMock(return_value=None)),
        patch("app.services.media_cache.media_cache.get_thumbnail_path", new=AsyncMock(return_value=None)),
        patch(
            "app.services.reel_image_service.frigate_client.get_snapshot_with_error",
            new=AsyncMock(return_value=(None, "snapshot_not_found")),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            missing = await client.get("/api/about/showcase/robin_old.jpg")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_reel_image_route_serves_a_wall_tile_smaller_than_a_card(seeded_db, media_cache_on, tmp_path):
    from io import BytesIO

    from PIL import Image

    photograph = tmp_path / "robin_new.jpg"
    photograph.write_bytes(_jpeg(2400, 1800))
    with patch("app.services.media_cache.media_cache.get_snapshot_path", new=AsyncMock(return_value=photograph)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            card = await client.get("/api/about/showcase/robin_new.jpg")
            tile = await client.get("/api/about/showcase/robin_new.jpg?size=tile")
            card_again = await client.get("/api/about/showcase/robin_new.jpg?size=card")
            unknown = await client.get("/api/about/showcase/robin_new.jpg?size=poster")
    assert tile.status_code == 200, tile.text
    with Image.open(BytesIO(tile.content)) as image:
        assert image.size == (REEL_TILE_MAX_EDGE, REEL_TILE_MAX_EDGE * 3 // 4)
    with Image.open(BytesIO(card.content)) as image:
        assert image.size == (REEL_IMAGE_MAX_EDGE, REEL_IMAGE_MAX_EDGE * 3 // 4)
    assert len(tile.content) < len(card.content)
    # The two sizes are cached apart: asking for a tile must not change what a card receives.
    assert card_again.content == card.content
    assert unknown.status_code == 422


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


@pytest.mark.asyncio
async def test_evicted_visit_advertised_by_events_falls_back_read_only_to_frigate(seeded_db, media_cache_on):
    """Issue #1108: an evicted media_cache visit still retained in Frigate renders on the wall without disk writes."""
    from io import BytesIO

    from PIL import Image

    raw_frigate = _jpeg(1600, 1200)
    frigate_fetch = AsyncMock(return_value=(raw_frigate, None))
    cache_snapshot = AsyncMock()
    cache_thumbnail = AsyncMock()

    with (
        patch("app.services.media_cache.media_cache.has_snapshot", return_value=False),
        patch("app.services.media_cache.media_cache.get_snapshot_path", new=AsyncMock(return_value=None)),
        patch("app.services.media_cache.media_cache.get_thumbnail_path", new=AsyncMock(return_value=None)),
        patch("app.services.archive_service.archive_service.snapshot_path", new=AsyncMock(return_value=None)),
        patch("app.services.media_cache.media_cache.cache_snapshot", new=cache_snapshot),
        patch("app.services.media_cache.media_cache.cache_thumbnail", new=cache_thumbnail),
        patch(
            "app.routers.events.frigate_client.get_event_with_error",
            new=AsyncMock(return_value=({"has_snapshot": True, "has_clip": False}, None)),
        ),
        patch("app.services.reel_image_service.frigate_client.get_snapshot_with_error", new=frigate_fetch),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            events_res = await client.get("/api/events?event_id=robin_new&fields=frigate_event,has_snapshot")
            assert events_res.status_code == 200, events_res.text
            assert events_res.json()[0]["has_snapshot"] is True

            tile = await client.get("/api/about/showcase/robin_new.jpg?size=tile")
            tile_again = await client.get("/api/about/showcase/robin_new.jpg?size=tile")
            card = await client.get("/api/about/showcase/robin_new.jpg?size=card")

    assert tile.status_code == 200, tile.text
    assert tile.headers["cache-control"].startswith("no-store")
    assert tile_again.status_code == 200 and tile_again.content == tile.content
    assert card.status_code == 200, card.text
    with Image.open(BytesIO(tile.content)) as img:
        assert img.size == (REEL_TILE_MAX_EDGE, REEL_TILE_MAX_EDGE * 3 // 4)
    with Image.open(BytesIO(card.content)) as img:
        assert img.size == (REEL_IMAGE_MAX_EDGE, REEL_IMAGE_MAX_EDGE * 3 // 4)
    # Second tile request came from warm memory cache; disk cache was never touched.
    assert frigate_fetch.await_count == 2
    assert cache_snapshot.await_count == 0
    assert cache_thumbnail.await_count == 0


@pytest.mark.asyncio
async def test_local_snapshot_and_archive_always_win_over_warm_fallback(seeded_db, media_cache_on, tmp_path):
    frigate_fetch = AsyncMock(return_value=(_jpeg(1000, 750), None))
    local_photo = tmp_path / "robin_new.jpg"
    local_photo.write_bytes(_jpeg(400, 400))
    archive_photo = tmp_path / "robin_old_archive.jpg"
    archive_photo.write_bytes(_jpeg(400, 200))

    with (
        patch("app.services.media_cache.media_cache.get_snapshot_path", new=AsyncMock(return_value=None)),
        patch("app.services.media_cache.media_cache.get_thumbnail_path", new=AsyncMock(return_value=None)),
        patch("app.services.archive_service.archive_service.snapshot_path", new=AsyncMock(return_value=None)),
        patch("app.services.reel_image_service.frigate_client.get_snapshot_with_error", new=frigate_fetch),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            fallback_res = await client.get("/api/about/showcase/robin_new.jpg?size=tile")
    assert fallback_res.status_code == 200
    assert frigate_fetch.await_count == 1

    # Local snapshot appearing after fallback hit wins immediately without calling Frigate.
    with (
        patch("app.services.media_cache.media_cache.get_snapshot_path", new=AsyncMock(return_value=local_photo)),
        patch("app.services.reel_image_service.frigate_client.get_snapshot_with_error", new=frigate_fetch),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            local_res = await client.get("/api/about/showcase/robin_new.jpg?size=tile")
    assert local_res.status_code == 200
    assert local_res.content != fallback_res.content
    assert frigate_fetch.await_count == 1

    # Archive wins without calling Frigate.
    with (
        patch("app.services.media_cache.media_cache.get_snapshot_path", new=AsyncMock(return_value=None)),
        patch("app.services.archive_service.archive_service.snapshot_path", new=AsyncMock(return_value=archive_photo)),
        patch("app.services.reel_image_service.frigate_client.get_snapshot_with_error", new=frigate_fetch),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            archive_res = await client.get("/api/about/showcase/robin_old.jpg?size=tile")
    assert archive_res.status_code == 200
    assert frigate_fetch.await_count == 1


@pytest.mark.asyncio
async def test_manual_upload_and_thumbnail_provenance_paths(seeded_db, media_cache_on, tmp_path):
    frigate_fetch = AsyncMock(return_value=(_jpeg(800, 600), None))
    manual_preview = tmp_path / "manual_preview.jpg"
    manual_preview.write_bytes(_jpeg(640, 480))
    thumb_file = tmp_path / "robin_thumb.jpg"
    thumb_file.write_bytes(_jpeg(320, 240))

    # Manual upload with preview -> 200, never calls Frigate.
    with (
        patch("app.services.media_cache.media_cache.get_snapshot_path", new=AsyncMock(return_value=None)),
        patch("app.services.archive_service.archive_service.snapshot_path", new=AsyncMock(return_value=None)),
        patch(
            "app.services.manual_observation_service.manual_observation_service.path_for_event",
            new=AsyncMock(return_value=manual_preview),
        ),
        patch("app.services.reel_image_service.frigate_client.get_snapshot_with_error", new=frigate_fetch),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/about/showcase/manual_abc123.jpg?size=tile")
    assert res.status_code == 200
    assert frigate_fetch.await_count == 0

    # Manual upload without preview -> 404, never calls Frigate.
    with (
        patch("app.services.media_cache.media_cache.get_snapshot_path", new=AsyncMock(return_value=None)),
        patch("app.services.archive_service.archive_service.snapshot_path", new=AsyncMock(return_value=None)),
        patch(
            "app.services.manual_observation_service.manual_observation_service.path_for_event",
            new=AsyncMock(return_value=None),
        ),
        patch("app.services.reel_image_service.frigate_client.get_snapshot_with_error", new=frigate_fetch),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/about/showcase/manual_missing.jpg?size=tile")
    assert res.status_code == 404
    assert frigate_fetch.await_count == 0

    # Eligible cached thumbnail (frigate_thumbnail) serves locally without calling Frigate.
    with (
        patch("app.services.media_cache.media_cache.get_snapshot_path", new=AsyncMock(return_value=None)),
        patch("app.services.archive_service.archive_service.snapshot_path", new=AsyncMock(return_value=None)),
        patch("app.services.media_cache.media_cache.get_thumbnail_path", new=AsyncMock(return_value=thumb_file)),
        patch(
            "app.services.media_cache.media_cache.get_thumbnail_metadata",
            new=AsyncMock(return_value={"source": "frigate_thumbnail"}),
        ),
        patch("app.services.reel_image_service.frigate_client.get_snapshot_with_error", new=frigate_fetch),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/about/showcase/robin_new.jpg?size=tile")
    assert res.status_code == 200
    assert frigate_fetch.await_count == 0

    # Stale snapshot_derived thumbnail with missing snapshot falls through to Frigate.
    with (
        patch("app.services.media_cache.media_cache.get_snapshot_path", new=AsyncMock(return_value=None)),
        patch("app.services.archive_service.archive_service.snapshot_path", new=AsyncMock(return_value=None)),
        patch("app.services.media_cache.media_cache.get_thumbnail_path", new=AsyncMock(return_value=thumb_file)),
        patch(
            "app.services.media_cache.media_cache.get_thumbnail_metadata",
            new=AsyncMock(return_value={"source": "snapshot_derived"}),
        ),
        patch("app.services.reel_image_service.frigate_client.get_snapshot_with_error", new=frigate_fetch),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/about/showcase/robin_new.jpg?size=tile")
    assert res.status_code == 200
    assert frigate_fetch.await_count == 1


@pytest.mark.asyncio
async def test_unknown_invalid_dotdot_and_deleted_detections_never_serve_or_probe_frigate(seeded_db, media_cache_on):
    frigate_fetch = AsyncMock(return_value=(_jpeg(800, 600), None))

    with (
        patch("app.services.media_cache.media_cache.get_snapshot_path", new=AsyncMock(return_value=None)),
        patch("app.services.media_cache.media_cache.get_thumbnail_path", new=AsyncMock(return_value=None)),
        patch("app.services.archive_service.archive_service.snapshot_path", new=AsyncMock(return_value=None)),
        patch("app.services.reel_image_service.frigate_client.get_snapshot_with_error", new=frigate_fetch),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            unknown = await client.get("/api/about/showcase/not_in_db_event.jpg")
            dotdot = await client.get("/api/about/showcase/a..b.jpg")
            bad = await client.get("/api/about/showcase/bad$id.jpg")

            assert unknown.status_code == 404
            assert dotdot.status_code == 400
            assert bad.status_code == 400
            assert frigate_fetch.await_count == 0

            # Warm fallback cache for a real detection, then delete the detection from DB.
            warm = await client.get("/api/about/showcase/robin_new.jpg?size=tile")
            assert warm.status_code == 200
            assert frigate_fetch.await_count == 1

            async with get_db() as db:
                await db.execute("DELETE FROM detections WHERE frigate_event = 'robin_new'")
                await db.commit()

            after_delete = await client.get("/api/about/showcase/robin_new.jpg?size=tile")
            assert after_delete.status_code == 404
            assert frigate_fetch.await_count == 1


@pytest.mark.asyncio
async def test_denied_guest_cannot_read_owner_warmed_fallback_and_permitted_guest_can(
    seeded_db, media_cache_on, guest_install
):
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index, score, display_name, category_name, is_hidden)
            VALUES
            ('recent_visible', 'cam1', ?, 1, 0.92, 'Robin', 'bird', 0),
            ('recent_hidden', 'cam1', ?, 1, 0.90, 'Robin', 'bird', 1)
            """,
            (now_iso, now_iso),
        )
        await db.commit()

    owner_token = create_access_token("owner", AuthLevel.OWNER)
    frigate_fetch = AsyncMock(return_value=(_jpeg(800, 600), None))
    original_media_window = (
        settings.public_access.media_days_mode,
        settings.public_access.media_historical_days,
    )
    settings.public_access.media_days_mode = "custom"
    settings.public_access.media_historical_days = 1

    try:
        with (
            patch("app.services.media_cache.media_cache.get_snapshot_path", new=AsyncMock(return_value=None)),
            patch("app.services.media_cache.media_cache.get_thumbnail_path", new=AsyncMock(return_value=None)),
            patch("app.services.archive_service.archive_service.snapshot_path", new=AsyncMock(return_value=None)),
            patch("app.services.reel_image_service.frigate_client.get_snapshot_with_error", new=frigate_fetch),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                cookies={SESSION_COOKIE: owner_token},
            ) as owner_client:
                # Owner primes the fallback cache for hidden, out-of-window, and visible visits.
                settings.public_access.show_snapshots = True
                primed_hidden = await owner_client.get("/api/about/showcase/recent_hidden.jpg?size=tile")
                primed_old = await owner_client.get("/api/about/showcase/robin_new.jpg?size=tile")
                primed_visible = await owner_client.get("/api/about/showcase/recent_visible.jpg?size=tile")
                assert primed_hidden.status_code == 200
                assert primed_old.status_code == 200
                assert primed_visible.status_code == 200
                assert frigate_fetch.await_count == 3

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as guest_client:
                # Guest cannot read hidden, out-of-window, or snapshot-disabled visits even when warm.
                guest_hidden = await guest_client.get("/api/about/showcase/recent_hidden.jpg?size=tile")
                guest_old = await guest_client.get("/api/about/showcase/robin_new.jpg?size=tile")
                assert guest_hidden.status_code == 404
                assert guest_old.status_code == 404
                assert frigate_fetch.await_count == 3

                settings.public_access.show_snapshots = False
                guest_disabled = await guest_client.get("/api/about/showcase/recent_visible.jpg?size=tile")
                assert guest_disabled.status_code == 404
                assert frigate_fetch.await_count == 3

                # Permitted guest gets 200 from the warm fallback cache.
                settings.public_access.show_snapshots = True
                guest_ok = await guest_client.get("/api/about/showcase/recent_visible.jpg?size=tile")
                assert guest_ok.status_code == 200
                assert frigate_fetch.await_count == 3
    finally:
        (
            settings.public_access.media_days_mode,
            settings.public_access.media_historical_days,
        ) = original_media_window


@pytest.mark.asyncio
async def test_transient_frigate_outage_returns_503_with_retry_after_and_recovers(seeded_db, media_cache_on):
    responses = iter([(None, "snapshot_timeout"), (_jpeg(800, 600), None)])
    fetch = AsyncMock(side_effect=lambda *_a, **_kw: next(responses))

    with (
        patch("app.services.media_cache.media_cache.get_snapshot_path", new=AsyncMock(return_value=None)),
        patch("app.services.media_cache.media_cache.get_thumbnail_path", new=AsyncMock(return_value=None)),
        patch("app.services.archive_service.archive_service.snapshot_path", new=AsyncMock(return_value=None)),
        patch("app.services.reel_image_service.frigate_client.get_snapshot_with_error", new=fetch),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.get("/api/about/showcase/robin_new.jpg?size=tile")
            assert first.status_code == 503
            assert first.headers.get("retry-after") == "5"

            # Reset breaker as if window elapsed; retry succeeds because transient failure was not cached as missing.
            reel_image_service._breaker_until = 0.0
            second = await client.get("/api/about/showcase/robin_new.jpg?size=tile")
            assert second.status_code == 200
    assert fetch.await_count == 2
