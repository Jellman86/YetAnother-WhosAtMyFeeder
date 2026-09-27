"""No route may hold a pooled connection while a species name is fetched.

Every route that names a species for a non-English reader is exercised with an
empty translation cache and a slow provider. Connection ownership is checked at
the provider boundary, not inferred from wall-clock timing under coverage/load.
Each test also proves the provider was actually asked, so a route that
quietly took the English, cache-only path cannot pass by accident. This is the
guard for #392 and the regression guard for #300.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database import close_db, get_db, init_db
from app import database
from app.main import app
from app.services.taxonomy.taxonomy_service import taxonomy_service

PROVIDER_DELAY_SECONDS = 0.4
TAXA = 13094
GERMAN = {"Accept-Language": "de"}


@pytest_asyncio.fixture(autouse=True)
async def seeded_db():
    await init_db()
    try:
        async with get_db() as db:
            for table in ("detections", "audio_detections", "taxonomy_translations", "taxonomy_cache"):
                await db.execute(f"DELETE FROM {table}")
            await db.execute(
                "INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id, is_not_found, last_updated)"
                " VALUES ('Cyanistes caeruleus', 'Eurasian Blue Tit', ?, 0, CURRENT_TIMESTAMP)",
                (TAXA,),
            )
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            for index in range(3):
                at = (now - timedelta(minutes=5 * index + 1)).strftime("%Y-%m-%d %H:%M:%S.%f")
                await db.execute(
                    """INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index, score,
                       display_name, category_name, scientific_name, common_name, taxa_id,
                       audio_species, audio_confirmed, is_hidden)
                       VALUES (?, 'cam1', ?, 1, 0.9, 'Eurasian Blue Tit', 'Cyanistes caeruleus',
                               'Cyanistes caeruleus', 'Eurasian Blue Tit', ?, 'Eurasian Blue Tit', 0, 0)""",
                    (f"evt_{index}", at, TAXA),
                )
                await db.execute(
                    """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, scientific_name)
                       VALUES (?, 'Eurasian Blue Tit', 0.8, 'mic1', 'Cyanistes caeruleus')""",
                    (at,),
                )
            await db.commit()
        taxonomy_service._background_fills.clear()
        yield
        await taxonomy_service.wait_for_background_fills()
    finally:
        await close_db()


@pytest.fixture
def slow_provider(monkeypatch, seeded_db):
    """Records every call, so a route test can prove the non-English path ran."""
    from app.config import settings

    # The event-scoped audio route keeps only microphones mapped to the event's
    # camera; with no mapping every row is suppressed and there is nothing to name.
    monkeypatch.setattr(settings.frigate, "camera_audio_mapping", {"cam1": "*"})
    calls: list[tuple[int, str, int]] = []
    owners = {}
    acquire = database._db_pool.acquire
    release = database._db_pool.release

    async def tracked_acquire(*args, **kwargs):
        connection = await acquire(*args, **kwargs)
        owners[id(connection)] = asyncio.current_task()
        return connection

    async def tracked_release(connection):
        owner = owners.get(id(connection))
        try:
            await release(connection)
        finally:
            if owners.get(id(connection)) is owner:
                owners.pop(id(connection), None)

    monkeypatch.setattr(database._db_pool, "acquire", tracked_acquire)
    monkeypatch.setattr(database._db_pool, "release", tracked_release)

    async def provider(taxa_id, lang):
        held = sum(owner is asyncio.current_task() for owner in owners.values())
        calls.append((taxa_id, lang, held))
        await asyncio.sleep(PROVIDER_DELAY_SECONDS)
        return "Blaumeise"

    monkeypatch.setattr(taxonomy_service, "_lookup_localized_inaturalist", provider)
    return calls


def _assert_no_hold_spanned_the_provider(path: str, calls: list[tuple[int, str, int]]) -> None:
    assert calls, f"{path}: the provider was never asked"
    assert all(held == 0 for _taxon, _language, held in calls), (
        f"{path}: provider awaited inside a pooled connection hold"
    )


ROUTES = [
    "/api/events?limit=10",
    "/api/species/Eurasian%20Blue%20Tit/stats",
    "/api/stats/daily-summary",
    "/api/audio/history?days=1",
    "/api/audio/summary?days=1",
    "/api/audio/species?span=day",
    "/api/audio/context/event/evt_0",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ROUTES)
async def test_the_route_answers_without_holding_a_connection_across_the_provider(path, slow_provider):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(path, headers=GERMAN)
        assert res.status_code == 200, (path, res.text[:200])
    await taxonomy_service.wait_for_background_fills()
    assert slow_provider, f"{path}: the provider was never asked, so the non-English path did not run"
    _assert_no_hold_spanned_the_provider(path, slow_provider)


@pytest.mark.asyncio
async def test_the_audio_context_route_answers_without_holding_a_connection_across_the_provider(slow_provider):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    path = f"/api/audio/context?timestamp={now.isoformat()}&window_seconds=3600&limit=8"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(path, headers=GERMAN)
        assert res.status_code == 200, res.text[:200]
    await taxonomy_service.wait_for_background_fills()
    assert slow_provider
    _assert_no_hold_spanned_the_provider(path, slow_provider)


@pytest.mark.asyncio
async def test_the_guard_rejects_an_actual_provider_wait_inside_a_hold(slow_provider):
    async with get_db():
        await taxonomy_service._lookup_localized_inaturalist(TAXA, "de")
    with pytest.raises(AssertionError, match="provider awaited inside"):
        _assert_no_hold_spanned_the_provider("negative control", slow_provider)


@pytest.mark.asyncio
async def test_a_second_render_has_the_name_the_first_one_filled_in(slow_provider):
    """Inside a hold the first render answers with the stored name and fills the
    cache off the request; the name is there for the next one."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.get("/api/stats/daily-summary", headers=GERMAN)
        assert first.status_code == 200
        assert "Blaumeise" not in first.text, "the first render must not have waited for the provider"
        await taxonomy_service.wait_for_background_fills()
        second = await client.get("/api/stats/daily-summary", headers=GERMAN)
        assert second.status_code == 200
    assert "Blaumeise" in second.text
