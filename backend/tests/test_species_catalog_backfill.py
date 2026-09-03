"""Backfilling canonical identity onto existing detection history.

Phase 3's conservative backfill: rows whose `scientific_name` resolves to
exactly one catalogue identity — through a concept or a recorded resolved
synonym — gain a `species_id`. Everything else stays exactly as it is and is
counted, never guessed: an ambiguous name, a name no source holds, or a row
with no scientific name at all remains readable and repairable. Name
snapshots and artifact provenance are never touched by the backfill.
"""

import hashlib
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import aiosqlite
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import build_species_catalog_seed as seed_builder  # noqa: E402

from app.services.species_catalog_backfill import backfill_catalog_identity  # noqa: E402
from app.services.species_catalog_resolver import SpeciesCatalogResolver  # noqa: E402

REFERENCE_SCHEMA = """
CREATE TABLE reference_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE taxon (id INTEGER PRIMARY KEY, scientific_name TEXT NOT NULL, common_name TEXT);
CREATE TABLE taxon_name (
    taxon_id INTEGER NOT NULL, locale TEXT NOT NULL, common_name TEXT NOT NULL,
    PRIMARY KEY (taxon_id, locale)
) WITHOUT ROWID;
"""

DETECTIONS_SCHEMA = """
CREATE TABLE detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detection_time TIMESTAMP NOT NULL,
    detection_index INTEGER NOT NULL,
    score FLOAT NOT NULL,
    display_name TEXT NOT NULL,
    category_name TEXT NOT NULL,
    frigate_event TEXT UNIQUE NOT NULL,
    camera_name TEXT NOT NULL,
    scientific_name TEXT,
    common_name TEXT,
    taxa_id INTEGER,
    manual_tagged BOOLEAN DEFAULT 0,
    species_id INTEGER,
    model_artifact_id INTEGER,
    model_output_index INTEGER
)
"""


@pytest.fixture
def catalog(tmp_path):
    """A catalogue holding the blue tit plus the Bufotes synonym alias."""
    ioc_pinned = hashlib.sha256(b"backfill ioc").hexdigest()
    col_pinned = hashlib.sha256(b"backfill col").hexdigest()

    reference = tmp_path / "reference.db"
    connection = sqlite3.connect(reference)
    try:
        connection.executescript(REFERENCE_SCHEMA)
        connection.execute("INSERT INTO reference_meta VALUES ('source_sha256', ?)", (ioc_pinned,))
        connection.execute("INSERT INTO taxon VALUES (1, 'Cyanistes caeruleus', 'Eurasian Blue Tit')")
        connection.commit()
    finally:
        connection.close()

    col = tmp_path / "col.json"
    col.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source": {"id": "catalogue-of-life", "version": "COL26.7-test", "export_sha256": col_pinned},
                "concepts": [
                    {
                        "scientific_name": "Bufotes balearicus",
                        "kingdom": "Animalia",
                        "label_class": "Amphibia",
                        "col_id": "S1",
                        "col_status": "synonym",
                        "accepted_col_id": "A1",
                        "accepted_scientific_name": "Bufotes viridis",
                    }
                ],
                "unresolved": [],
            }
        ),
        encoding="utf-8",
    )

    manifest = tmp_path / "sources.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "frozen_on": "2026-08-19",
                "sources": [
                    {
                        "id": "ioc-world-bird-list",
                        "name": "IOC",
                        "role": "bird-vernacular-names",
                        "version": "14.2-test",
                        "url": "https://www.worldbirdnames.org/",
                        "licence": "CC-BY-3.0",
                        "citation": "IOC World Bird List.",
                        "redistribution": "bundled",
                        "content_sha256": ioc_pinned,
                    },
                    {
                        "id": "catalogue-of-life",
                        "name": "Catalogue of Life",
                        "role": "canonical-taxonomy",
                        "version": "COL26.7-test",
                        "url": "https://www.checklistbank.org/dataset/315777",
                        "licence": "CC-BY-4.0",
                        "citation": "Catalogue of Life, COL26.7.",
                        "redistribution": "build-input",
                        "content_sha256": col_pinned,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    path = tmp_path / "catalog.db"
    seed_builder.build(reference, path, manifest_path=manifest, col_concepts_path=col)
    return path


async def _seed_detections(db, rows):
    await db.executescript(DETECTIONS_SCHEMA)
    for event, scientific, species_id in rows:
        await db.execute(
            "INSERT INTO detections (detection_time, detection_index, score, display_name, category_name,"
            " frigate_event, camera_name, scientific_name, species_id)"
            " VALUES (?, 0, 0.9, ?, ?, ?, 'feeder', ?, ?)",
            (
                datetime(2026, 1, 1, 12, 0, 0),
                scientific or "Unknown Bird",
                scientific or "Unknown Bird",
                event,
                scientific,
                species_id,
            ),
        )
    await db.commit()


async def _seed_detections_more(db, rows):
    for event, scientific, species_id in rows:
        await db.execute(
            "INSERT INTO detections (detection_time, detection_index, score, display_name, category_name,"
            " frigate_event, camera_name, scientific_name, species_id)"
            " VALUES (?, 0, 0.9, ?, ?, ?, 'feeder', ?, ?)",
            (datetime(2026, 1, 1, 12, 0, 0), scientific, scientific, event, scientific, species_id),
        )
    await db.commit()


async def _species_ids(db):
    cursor = await db.execute("SELECT frigate_event, species_id, scientific_name FROM detections ORDER BY id")
    return {row[0]: (row[1], row[2]) for row in await cursor.fetchall()}


@pytest.mark.asyncio
async def test_exact_and_synonym_names_gain_identity_and_the_rest_stay_untouched(catalog):
    resolver = SpeciesCatalogResolver(catalog)
    async with aiosqlite.connect(":memory:") as db:
        await _seed_detections(
            db,
            [
                ("evt-tit", "Cyanistes caeruleus", None),
                ("evt-tit-case", "cyanistes CAERULEUS", None),
                ("evt-toad", "Bufotes balearicus", None),
                ("evt-unknown", "Nonexistus maximus", None),
                ("evt-no-name", None, None),
            ],
        )

        summary = await backfill_catalog_identity(db, resolver=resolver)

        results = await _species_ids(db)
        assert results["evt-tit"][0] is not None
        assert results["evt-tit-case"][0] == results["evt-tit"][0]
        assert results["evt-toad"][0] is not None
        assert results["evt-unknown"] == (None, "Nonexistus maximus")
        assert results["evt-no-name"][0] is None
        assert summary["rows_identified"] == 3
        assert summary["names_resolved"] == 3
        assert summary["names_unresolved"] == 1


@pytest.mark.asyncio
async def test_an_identity_that_agrees_with_its_name_is_never_rewritten(catalog):
    resolver = SpeciesCatalogResolver(catalog)
    async with aiosqlite.connect(":memory:") as db:
        await _seed_detections(db, [("evt-tit", "Cyanistes caeruleus", None)])
        await backfill_catalog_identity(db, resolver=resolver)
        tit_id = (await _species_ids(db))["evt-tit"][0]
        assert tit_id is not None

        await _seed_detections_more(db, [("evt-already", "Cyanistes caeruleus", tit_id)])
        first = await backfill_catalog_identity(db, resolver=resolver)
        second = await backfill_catalog_identity(db, resolver=resolver)

        results = await _species_ids(db)
        assert results["evt-already"][0] == tit_id
        assert first["rows_identified"] == 0 and first["rows_repaired"] == 0
        assert second["rows_identified"] == 0 and second["rows_repaired"] == 0


@pytest.mark.asyncio
async def test_an_identity_that_names_a_different_bird_is_repaired_from_the_rows_own_name(catalog):
    """The #386 shape: a Dunnock retagged by hand before corrections carried
    identity kept the Tree Sparrow's `species_id` under the Dunnock name, and the
    leaderboard listed Dunnock twice. The name is what the owner asserted."""
    resolver = SpeciesCatalogResolver(catalog)
    async with aiosqlite.connect(":memory:") as db:
        await _seed_detections(
            db,
            [
                ("evt-tit", "Cyanistes caeruleus", None),
                ("evt-stale", "Cyanistes caeruleus", 9999),
            ],
        )

        first = await backfill_catalog_identity(db, resolver=resolver)
        second = await backfill_catalog_identity(db, resolver=resolver)

        results = await _species_ids(db)
        assert results["evt-stale"][0] == results["evt-tit"][0], "the stale id is re-derived from the name"
        assert first["rows_identified"] == 1
        assert first["rows_repaired"] == 1 and first["names_repaired"] == 1
        assert second["rows_repaired"] == 0, "re-running repairs nothing twice"


@pytest.mark.asyncio
async def test_a_disputed_identity_under_an_ambiguous_name_is_left_alone(catalog):
    """Repair uses the same rule as the fill: exactly one match, or nothing."""
    connection = sqlite3.connect(catalog)
    try:
        connection.execute("INSERT INTO species (species_id, rank, status) VALUES (99, 'species', 'accepted')")
        connection.execute(
            "INSERT INTO species_concepts (species_id, provider, provider_taxon_id, source_release, scientific_name)"
            " VALUES (99, 'catalogue-of-life', 'HOMONYM', 'COL26.7-test', 'Cyanistes caeruleus')"
        )
        connection.commit()
    finally:
        connection.close()
    resolver = SpeciesCatalogResolver(catalog)

    async with aiosqlite.connect(":memory:") as db:
        await _seed_detections(db, [("evt-stale", "Cyanistes caeruleus", 9999)])

        summary = await backfill_catalog_identity(db, resolver=resolver)

        assert (await _species_ids(db))["evt-stale"][0] == 9999
        assert summary["rows_repaired"] == 0


@pytest.mark.asyncio
async def test_an_ambiguous_name_fails_closed(catalog):
    """A name the catalogue holds for two different species resolves nothing."""
    connection = sqlite3.connect(catalog)
    try:
        connection.execute("INSERT INTO species (species_id, rank, status) VALUES (99, 'species', 'accepted')")
        connection.execute(
            "INSERT INTO species_concepts (species_id, provider, provider_taxon_id, source_release, scientific_name)"
            " VALUES (99, 'catalogue-of-life', 'HOMONYM', 'COL26.7-test', 'Cyanistes caeruleus')"
        )
        connection.commit()
    finally:
        connection.close()
    resolver = SpeciesCatalogResolver(catalog)

    async with aiosqlite.connect(":memory:") as db:
        await _seed_detections(db, [("evt-tit", "Cyanistes caeruleus", None)])

        summary = await backfill_catalog_identity(db, resolver=resolver)

        results = await _species_ids(db)
        assert results["evt-tit"][0] is None
        assert summary["names_ambiguous"] == 1


@pytest.mark.asyncio
async def test_a_missing_catalogue_reports_and_changes_nothing(tmp_path):
    resolver = SpeciesCatalogResolver(tmp_path / "nowhere.db")
    async with aiosqlite.connect(":memory:") as db:
        await _seed_detections(db, [("evt-tit", "Cyanistes caeruleus", None)])

        summary = await backfill_catalog_identity(db, resolver=resolver)

        results = await _species_ids(db)
        assert results["evt-tit"][0] is None
        assert summary["status"] == "unavailable"
