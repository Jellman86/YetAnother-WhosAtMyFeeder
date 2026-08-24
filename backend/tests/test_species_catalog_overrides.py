"""Owner renames belong to the catalogue, not to a lookup cache.

A rename is the one piece of naming the owner authored, and it was stored in
`taxonomy_cache.manual_common_name` -- a table whose other columns are a cache
of provider answers that can be refetched at will. The catalogue has held
`species_name_overrides` since its first migration, and the shared naming
function already prefers it over every other source, but nothing ever wrote to
it, so the precedence had to be hand-rolled again wherever a name was chosen.

These tests fix the store of record: an override is written to the catalogue,
keyed on the species it names rather than on a spelling of that species.
"""

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import build_species_catalog_seed as seed_builder  # noqa: E402

from app.services.species_catalog_overrides import (  # noqa: E402
    ALL_LANGUAGES,
    clear_catalogue_override,
    write_catalogue_override,
)
from app.services.species_names import SpeciesNameLookup  # noqa: E402

REFERENCE_SCHEMA = """
CREATE TABLE reference_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE taxon (id INTEGER PRIMARY KEY, scientific_name TEXT NOT NULL, common_name TEXT);
CREATE TABLE taxon_name (
    taxon_id INTEGER NOT NULL, locale TEXT NOT NULL, common_name TEXT NOT NULL,
    PRIMARY KEY (taxon_id, locale)
) WITHOUT ROWID;
"""


@pytest.fixture
def catalog(tmp_path):
    pinned = hashlib.sha256(b"override workbook").hexdigest()
    reference = tmp_path / "reference.db"
    connection = sqlite3.connect(reference)
    try:
        connection.executescript(REFERENCE_SCHEMA)
        connection.execute("INSERT INTO reference_meta VALUES ('source_sha256', ?)", (pinned,))
        connection.executemany(
            "INSERT INTO taxon VALUES (?, ?, ?)",
            [(1, "Cyanistes caeruleus", "Eurasian Blue Tit"), (2, "Erithacus rubecula", "European Robin")],
        )
        connection.executemany(
            "INSERT INTO taxon_name VALUES (?, ?, ?)",
            [(1, "de", "Blaumeise"), (2, "de", "Rotkehlchen")],
        )
        connection.commit()
    finally:
        connection.close()

    manifest = tmp_path / "sources.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "frozen_on": "2026-08-24",
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
                        "content_sha256": pinned,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    path = tmp_path / "catalog.db"
    seed_builder.build(reference, path, manifest_path=manifest)
    return path


def overrides_in(catalog_path):
    connection = sqlite3.connect(catalog_path)
    try:
        return connection.execute(
            "SELECT species_id, language_tag, name FROM species_name_overrides ORDER BY species_id, language_tag"
        ).fetchall()
    finally:
        connection.close()


class TestWritingAnOverride:
    def test_a_rename_is_recorded_against_the_species_it_names(self, catalog):
        assert write_catalogue_override(1, "Bluetit", catalog_path=catalog) is True

        assert overrides_in(catalog) == [(1, ALL_LANGUAGES, "Bluetit")]

    def test_a_rename_applies_in_every_language_unless_told_otherwise(self, catalog):
        """The name the owner typed replaced one name, not one translation, so
        it is recorded for every language rather than only for theirs."""
        write_catalogue_override(1, "Bluetit", catalog_path=catalog)

        lookup = SpeciesNameLookup(catalog)

        assert lookup.display_names([1], language="de") == {1: "Bluetit"}
        assert lookup.display_names([1], language="en") == {1: "Bluetit"}
        # A species the owner did not rename still gets the curated name.
        assert lookup.display_names([2], language="de") == {2: "Rotkehlchen"}

    def test_renaming_again_replaces_the_first_rename(self, catalog):
        write_catalogue_override(1, "Bluetit", catalog_path=catalog)
        write_catalogue_override(1, "Blue Tit", catalog_path=catalog)

        assert overrides_in(catalog) == [(1, ALL_LANGUAGES, "Blue Tit")]

    def test_a_blank_name_is_refused_rather_than_stored(self, catalog):
        assert write_catalogue_override(1, "   ", catalog_path=catalog) is False

        assert overrides_in(catalog) == []

    def test_an_unknown_species_is_refused_by_the_schema_not_written(self, catalog):
        assert write_catalogue_override(99999, "Nothing", catalog_path=catalog) is False

        assert overrides_in(catalog) == []


class TestClearingAnOverride:
    def test_clearing_removes_the_rename(self, catalog):
        write_catalogue_override(1, "Bluetit", catalog_path=catalog)

        assert clear_catalogue_override(1, catalog_path=catalog) is True
        assert overrides_in(catalog) == []

    def test_clearing_a_rename_that_was_never_set_is_not_an_error(self, catalog):
        assert clear_catalogue_override(1, catalog_path=catalog) is False

    def test_the_curated_name_returns_once_the_rename_is_cleared(self, catalog):
        write_catalogue_override(1, "Bluetit", catalog_path=catalog)
        clear_catalogue_override(1, catalog_path=catalog)

        assert SpeciesNameLookup(catalog).display_names([1], language="de") == {1: "Blaumeise"}


class TestDegradingWithoutACatalogue:
    def test_writing_without_a_catalogue_reports_failure_rather_than_raising(self, tmp_path):
        assert write_catalogue_override(1, "Bluetit", catalog_path=tmp_path / "nowhere.db") is False

    def test_clearing_without_a_catalogue_reports_failure_rather_than_raising(self, tmp_path):
        assert clear_catalogue_override(1, catalog_path=tmp_path / "nowhere.db") is False

    def test_a_file_that_is_not_a_catalogue_is_not_written_to(self, tmp_path):
        junk = tmp_path / "junk.db"
        junk.write_bytes(b"not a database")

        assert write_catalogue_override(1, "Bluetit", catalog_path=junk) is False


class TestFillingTheCatalogueFromTheDetectionDatabase:
    """The one-way migration that gives the catalogue the renames an owner made
    before it existed."""

    @pytest.fixture
    def cache(self, tmp_path):
        import aiosqlite

        path = tmp_path / "speciesid.db"
        connection = sqlite3.connect(path)
        try:
            connection.execute(
                "CREATE TABLE taxonomy_cache ("
                " scientific_name TEXT PRIMARY KEY, common_name TEXT, manual_common_name TEXT)"
            )
            connection.executemany(
                "INSERT INTO taxonomy_cache VALUES (?, ?, ?)",
                [
                    ("Cyanistes caeruleus", "Eurasian Blue Tit", "Bluetit"),
                    ("Erithacus rubecula", "European Robin", None),
                    ("Nonexistent bird", "Fantasy", "My Fantasy Bird"),
                ],
            )
            connection.commit()
        finally:
            connection.close()
        return aiosqlite.connect(path)

    @pytest.mark.asyncio
    async def test_a_rename_made_before_the_catalogue_existed_is_carried_over(self, catalog, cache, monkeypatch):
        from app.services import species_catalog_resolver as resolver_module
        from app.services.species_catalog_overrides import migrate_cache_overrides

        monkeypatch.setattr(
            resolver_module, "species_catalog_resolver", resolver_module.SpeciesCatalogResolver(catalog)
        )

        async with cache as db:
            summary = await migrate_cache_overrides(db, catalog_path=catalog)

        assert summary["migrated"] == 1
        # The fantasy bird names no catalogue species, so it stays where it is
        # rather than being attached to a guess.
        assert summary["unresolved"] == 1
        assert overrides_in(catalog) == [(1, ALL_LANGUAGES, "Bluetit")]

    @pytest.mark.asyncio
    async def test_it_never_resurrects_a_rename_the_owner_has_since_changed(self, catalog, cache, monkeypatch):
        from app.services import species_catalog_resolver as resolver_module
        from app.services.species_catalog_overrides import migrate_cache_overrides

        monkeypatch.setattr(
            resolver_module, "species_catalog_resolver", resolver_module.SpeciesCatalogResolver(catalog)
        )
        write_catalogue_override(1, "What I call it now", catalog_path=catalog)

        async with cache as db:
            summary = await migrate_cache_overrides(db, catalog_path=catalog)

        assert summary["migrated"] == 0
        assert summary["already_present"] == 1
        assert overrides_in(catalog) == [(1, ALL_LANGUAGES, "What I call it now")]

    @pytest.mark.asyncio
    async def test_a_database_without_the_cache_table_is_reported_not_raised(self, catalog, tmp_path):
        import aiosqlite

        from app.services.species_catalog_overrides import migrate_cache_overrides

        empty = tmp_path / "empty.db"
        sqlite3.connect(empty).close()

        async with aiosqlite.connect(empty) as db:
            summary = await migrate_cache_overrides(db, catalog_path=catalog)

        assert summary["status"] == "unavailable"


class TestNotAskingForMoreAccessThanIsNeeded:
    def test_renames_can_be_counted_on_a_read_only_catalogue(self, catalog):
        """Diagnostics count renames on every health poll. Taking a writable
        handle there would report nothing available on a catalogue mounted
        read-only, when the data reads perfectly well."""
        import os
        import stat

        from app.services.species_catalog_overrides import catalogue_override_count

        write_catalogue_override(1, "Bluetit", catalog_path=catalog)
        os.chmod(catalog, stat.S_IRUSR)
        try:
            assert catalogue_override_count(catalog) == 1
            # And a write against it fails rather than raising.
            assert write_catalogue_override(2, "Robin", catalog_path=catalog) is False
        finally:
            os.chmod(catalog, stat.S_IRUSR | stat.S_IWUSR)
