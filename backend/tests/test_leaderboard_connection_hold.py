"""Naming a species must not happen while a pooled connection is held.

The leaderboard resolves each species' display name after reading the rows,
and for a non-English reader that lookup checks a cache and then asks
iNaturalist over the network, with a ten second timeout. It did so inside
`async with get_db()`, so one uncached species could hold one of five pooled
connections for ten seconds while everything else needing the database
queued behind it. An owner's diagnostics showed this route holding a
connection for 5.1 seconds (#386, and the same disease as #300).
"""

import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database import close_db, get_db, init_db
from app.main import app

LOOKUP_DELAY_SECONDS = 0.4


@pytest_asyncio.fixture(autouse=True)
async def seeded_db():
    await init_db()
    try:
        async with get_db() as db:
            await db.execute("DELETE FROM detections")
            for index in range(4):
                await db.execute(
                    """INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index,
                       score, display_name, category_name, scientific_name, taxa_id, is_hidden)
                       VALUES (?, 'cam1', datetime('now', ?), 1, 0.9, ?, ?, ?, ?, 0)""",
                    (
                        f"evt_{index}",
                        f"-{index + 1} hours",
                        f"Bird {index}",
                        f"Genus species{index}",
                        f"Genus species{index}",
                        1000 + index,
                    ),
                )
            # An unknown-bird row, so the branch that reports it runs outside the hold too.
            await db.execute(
                """INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index,
                   score, display_name, category_name, is_hidden)
                   VALUES ('evt_unknown', 'cam1', datetime('now', '-30 minutes'), 1, 0.3, 'Unknown Bird', 'Unknown Bird', 0)"""
            )
            await db.commit()
        yield
    finally:
        await close_db()


@pytest.mark.asyncio
async def test_name_lookups_do_not_happen_while_a_connection_is_held(monkeypatch):
    from app.routers import species as species_router

    # Only the network hop is stubbed, so the cache read before it runs for real.
    # That matters: the route used to hand these lookups the connection it had
    # already given back, and a stub of the whole lookup hid it.
    async def slow_inaturalist(taxa_id, lang):
        await asyncio.sleep(LOOKUP_DELAY_SECONDS)
        return None

    monkeypatch.setattr(species_router, "get_user_language", lambda request: "de")
    monkeypatch.setattr(species_router.taxonomy_service, "_lookup_localized_inaturalist", slow_inaturalist)

    from app.database import get_db_pool_status

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/leaderboard/species?span=week")
        assert res.status_code == 200
        names = [row["species"] for row in res.json()["species"]]
        assert len(names) == 5 and "Unknown Bird" in names

    hold_max_ms = get_db_pool_status()["hold_ms_max"]
    assert hold_max_ms < LOOKUP_DELAY_SECONDS * 1000 * 0.5, (
        f"a connection was held for {hold_max_ms} ms while a name lookup took "
        f"{LOOKUP_DELAY_SECONDS * 1000} ms, so the lookup ran inside the hold"
    )


@pytest.mark.asyncio
async def test_an_english_reader_gets_canonical_names_without_a_connection_in_hand(monkeypatch):
    """The English branch resolves through the taxonomy cache too, and must open
    its own short-lived connection now the route has released its own."""
    from app.routers import species as species_router

    monkeypatch.setattr(species_router, "get_user_language", lambda request: "en")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/leaderboard/species?span=week")
        assert res.status_code == 200
        names = [row["species"] for row in res.json()["species"]]
        assert len(names) == 5 and "Unknown Bird" in names
