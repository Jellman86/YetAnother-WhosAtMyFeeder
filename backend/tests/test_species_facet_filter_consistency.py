"""Every species the filter panel offers must return its rows when chosen.

The Explorer builds its species list by collapsing the different spellings a
bird was recorded under, then filtering has to take the chosen option back to
every one of those rows. Where the two sides disagree, the panel offers a
species and the filter finds none of it - the exact shape reported in #301
("Eurasian Blue Tit ... 2" offered, "0 visits" returned). These cases drive
adversarial label shapes through the real API and assert the invariant:
an offered option is never an empty answer.
"""

import uuid
import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.routers.events import _event_filters_cache


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def offline_taxonomy(monkeypatch):
    from app.services.taxonomy import taxonomy_service as ts_module

    async def unavailable(self, name):
        raise ts_module.TaxonomyLookupUnavailable(name)

    monkeypatch.setattr(ts_module.TaxonomyService, "_lookup_inaturalist", unavailable)


@pytest_asyncio.fixture(autouse=True)
async def db_setup():
    await init_db()
    settings.auth.enabled = False
    settings.public_access.enabled = False
    _event_filters_cache.clear()
    # These invariants assert on the exact option values the facet emits, so
    # every case starts from an empty slate rather than tolerating leftovers.
    async with get_db() as db:
        await db.execute("DELETE FROM detections")
        await db.execute("DELETE FROM taxonomy_cache")
        await db.commit()
    yield
    _event_filters_cache.clear()
    await close_db()


async def _insert(event_id, display, *, sci=None, common=None, taxa=None, hidden=False):
    async with get_db() as db:
        await db.execute(
            """INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged,
                scientific_name, common_name, taxa_id
            ) VALUES (datetime('now'), 1, 0.8, ?, ?, ?, 'cam', ?, 0, ?, ?, ?)""",
            (display, display, event_id, 1 if hidden else 0, sci, common, taxa),
        )
        await db.commit()


async def _cache(sci, common, taxa):
    async with get_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES (?,?,?)",
            (sci, common, taxa),
        )
        await db.commit()


SHAPES = [
    # (label, rows[(display, sci, common, taxa)], cache[(sci, common, taxa)])
    ("plain-no-taxonomy", [("Mystery Wren", None, None, None)], []),
    ("parenthetical-common-sci", [("Eurasian Blue Tit (Cyanistes caeruleus)", None, None, None)], []),
    ("parenthetical-sci-common", [("Cyanistes caeruleus (Eurasian Blue Tit)", None, None, None)], []),
    (
        "sci-stored-cache-known",
        [("Blue Tit Label", "Cyanistes caeruleus", None, None)],
        [("Cyanistes caeruleus", "Eurasian Blue Tit", 13270)],
    ),
    (
        "mixed-one-taxa-one-not",
        [
            ("Eurasian Blue Tit", "Cyanistes caeruleus", "Eurasian Blue Tit", 13270),
            ("Cyanistes caeruleus (Eurasian Blue Tit)", None, None, None),
        ],
        [("Cyanistes caeruleus", "Eurasian Blue Tit", 13270)],
    ),
    (
        "cache-only-via-sci",
        [("Tit A", "Cyanistes caeruleus", None, None), ("Tit B", "Cyanistes caeruleus", None, None)],
        [("Cyanistes caeruleus", "Eurasian Blue Tit", 13270)],
    ),
    ("accented", [("Grünfink", None, None, None)], []),
    ("taxa-stored-cache-conflict", [("Conflict Bird", "Parus major", None, 999)], [("Parus major", "Great Tit", 111)]),
    (
        "parenthetical-with-cache-common-match",
        [("Eurasian Blue Tit (Cyanistes caeruleus)", None, None, None)],
        [("Cyanistes caeruleus", "Eurasian Blue Tit", 13270)],
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("label,rows,cache", SHAPES, ids=[s[0] for s in SHAPES])
async def test_every_offered_species_returns_its_rows(client, label, rows, cache):
    for sci, common, taxa in cache:
        await _cache(sci, common, taxa)
    displays = set()
    for i, (display, sci, common, taxa) in enumerate(rows):
        await _insert(f"evt-{label}-{i}-{uuid.uuid4().hex[:6]}", display, sci=sci, common=common, taxa=taxa)
        displays.add(display.lower())

    resp = await client.get("/api/events/filters", params={"force_refresh": "true"})
    assert resp.status_code == 200
    options = resp.json()["species"]
    # find the option(s) covering our seeded rows
    mine = [
        o
        for o in options
        if (o["display_name"] or "").lower() in displays
        or (o.get("scientific_name") or "").lower() in {r[1].lower() for r in rows if r[1]}
        or (o["value"] or "").lower() in displays
        or any(d in (o["display_name"] or "").lower() for d in displays)
    ]
    assert mine, f"{label}: no facet option found among {[o['display_name'] for o in options]}"
    for o in mine:
        value = o["value"]
        r = await client.get("/api/events", params={"species": value, "fields": "list", "limit": 50})
        assert r.status_code == 200, r.text
        events = r.json()
        c = await client.get("/api/events/count", params={"species": value})
        n = c.json()["count"]
        assert len(events) > 0 and n > 0, (
            f"{label}: option value={value!r} display={o['display_name']!r} "
            f"facet_count={o['count']} -> list={len(events)} count={n}"
        )


@pytest.mark.asyncio
async def test_cache_linked_group_offers_a_name_not_an_unstored_id(client):
    """A `taxa:` value must only be offered when some detection row stores that
    id: an id that exists only in the taxonomy cache is rewritten whenever the
    cache refreshes, and a filter built on it goes from "2 detections" to
    "0 visits" without anything else changing (#301)."""
    await _cache("Cyanistes caeruleus", "Eurasian Blue Tit", 13270)
    await _insert(f"evt-{uuid.uuid4().hex[:8]}", "Blue Tit Label", sci="Cyanistes caeruleus")

    resp = await client.get("/api/events/filters", params={"force_refresh": "true"})
    option = next(
        o for o in resp.json()["species"] if (o.get("scientific_name") or "").lower() == "cyanistes caeruleus"
    )
    assert not option["value"].startswith("taxa:"), option
    r = await client.get("/api/events/count", params={"species": option["value"]})
    assert r.json()["count"] >= 1


@pytest.mark.asyncio
async def test_offered_value_survives_taxonomy_cache_drift(client):
    """Filtering by an offered option must still work after the cache learns a
    corrected taxon id, because the cache is refreshed independently of the
    filter list the user is looking at (#301)."""
    await _cache("Cyanistes caeruleus", "Eurasian Blue Tit", 13270)
    await _insert(f"evt-{uuid.uuid4().hex[:8]}", "Blue Tit Label", sci="Cyanistes caeruleus")

    resp = await client.get("/api/events/filters", params={"force_refresh": "true"})
    option = next(
        o for o in resp.json()["species"] if (o.get("scientific_name") or "").lower() == "cyanistes caeruleus"
    )

    # iNaturalist corrects the id after the filter list was built.
    async with get_db() as db:
        await db.execute("UPDATE taxonomy_cache SET taxa_id = 144849 WHERE scientific_name = 'Cyanistes caeruleus'")
        await db.commit()

    r = await client.get("/api/events/count", params={"species": option["value"]})
    assert r.json()["count"] >= 1, option
    rows = await client.get("/api/events", params={"species": option["value"], "fields": "list", "limit": 10})
    assert len(rows.json()) >= 1


@pytest.mark.asyncio
async def test_stored_ids_keep_the_taxa_fast_path(client):
    await _insert(f"evt-{uuid.uuid4().hex[:8]}", "Great Tit", sci="Parus major", common="Great Tit", taxa=111)
    resp = await client.get("/api/events/filters", params={"force_refresh": "true"})
    option = next(o for o in resp.json()["species"] if o.get("taxa_id") == 111)
    assert option["value"] == "taxa:111"
    r = await client.get("/api/events/count", params={"species": "taxa:111"})
    assert r.json()["count"] >= 1


@pytest.mark.asyncio
async def test_failed_lookup_never_downgrades_a_cached_identity():
    """A not-found answer for a name must not null the taxon id a cache row
    already carries: features key on that id, and losing it turns an offered
    species into an empty filter (#301)."""
    from app.services.taxonomy.taxonomy_service import taxonomy_service

    await taxonomy_service._save_to_cache(
        {"scientific_name": "Parus major", "common_name": "Great Tit", "taxa_id": 111, "is_not_found": False}
    )
    await taxonomy_service._save_to_cache(
        {"scientific_name": "Parus major", "common_name": None, "taxa_id": None, "is_not_found": True}
    )
    async with get_db() as db:
        async with db.execute(
            "SELECT common_name, taxa_id, is_not_found FROM taxonomy_cache WHERE scientific_name = 'Parus major'"
        ) as cur:
            row = await cur.fetchone()
    assert row == ("Great Tit", 111, 0), row
