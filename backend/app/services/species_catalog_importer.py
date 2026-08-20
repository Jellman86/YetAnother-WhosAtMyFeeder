"""Import a catalogue release bundle into the live catalogue, transactionally.

A bundle is a built catalogue file (what the seed builder produces): a fully
migrated `species_catalog.db` holding exactly one release. The importer
validates the bundle — schema revision, one release row, recorded content
digest, foreign-key integrity — then stages its rows and activates the release
inside a single transaction against the live catalogue. Interruption at any
point rolls back to the previous release with no partial rows.

Species identity is stable and durable: an incoming taxon already known
through any provider concept keeps its live `species_id`; an unknown one gets
a new identity; and identities are never deleted, only left behind by newer
releases, so rollback keeps every previously referenced `species_id` valid.
Owner overrides live in their own table and are never touched.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

import structlog

from app.services.species_catalog_migrations import catalog_migration_heads, default_catalog_path
from app.services.species_catalog_release import connection_content_digest

log = structlog.get_logger()


class CatalogImportError(Exception):
    """A release bundle failed validation, or the import could not complete."""


@dataclass(frozen=True)
class ImportResult:
    status: str
    release_id: int
    species_added: int = 0
    species_matched: int = 0
    names_added: int = 0


@dataclass(frozen=True)
class _Bundle:
    release: sqlite3.Row
    species: list[sqlite3.Row]
    concepts: list[sqlite3.Row]
    names: list[sqlite3.Row]


def _schema_revision(connection: sqlite3.Connection) -> Optional[str]:
    try:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    except sqlite3.Error:
        return None
    return row[0] if row else None


def _read_bundle(bundle_path: Path) -> _Bundle:
    try:
        connection = sqlite3.connect(f"file:{bundle_path}?mode=ro", uri=True)
    except sqlite3.Error as error:
        raise CatalogImportError(f"Bundle unreadable at {bundle_path}: {error}") from error
    connection.row_factory = sqlite3.Row
    try:
        head = catalog_migration_heads()[0]
        revision = _schema_revision(connection)
        if revision != head:
            raise CatalogImportError(f"Bundle schema revision '{revision}' does not match the expected head '{head}'")

        releases = connection.execute("SELECT * FROM catalogue_releases").fetchall()
        if len(releases) != 1:
            raise CatalogImportError(f"A bundle must hold exactly one release, found {len(releases)}")
        release = releases[0]

        recomputed = connection_content_digest(connection)
        if recomputed != release["content_sha256"]:
            raise CatalogImportError(
                "Bundle content does not match its recorded digest: "
                f"recorded {release['content_sha256']}, recomputed {recomputed}"
            )

        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise CatalogImportError("Bundle fails foreign-key integrity")

        return _Bundle(
            release=release,
            species=connection.execute("SELECT * FROM species ORDER BY species_id").fetchall(),
            concepts=connection.execute(
                "SELECT * FROM species_concepts ORDER BY species_id, provider, provider_taxon_id"
            ).fetchall(),
            names=connection.execute("SELECT * FROM species_names ORDER BY species_id, language_tag, name").fetchall(),
        )
    finally:
        connection.close()


def _before_activation(connection: sqlite3.Connection) -> None:
    """Test seam: the last point an interruption can strike before activation."""


def _map_species(live: sqlite3.Connection, bundle: _Bundle) -> tuple[dict[int, int], int, int]:
    """Match bundle species to live identities; create the ones nobody knows."""
    concepts_by_species: dict[int, list[sqlite3.Row]] = {}
    for concept in bundle.concepts:
        concepts_by_species.setdefault(concept["species_id"], []).append(concept)

    id_map: dict[int, int] = {}
    added = matched = 0
    for species in bundle.species:
        bundle_id = species["species_id"]
        live_id: Optional[int] = None
        for concept in concepts_by_species.get(bundle_id, []):
            row = live.execute(
                "SELECT species_id FROM species_concepts WHERE provider = ? AND provider_taxon_id = ? LIMIT 1",
                (concept["provider"], concept["provider_taxon_id"]),
            ).fetchone()
            if row:
                live_id = row[0]
                break
        if live_id is None:
            cursor = live.execute(
                "INSERT INTO species (rank, status) VALUES (?, ?)", (species["rank"], species["status"])
            )
            live_id = int(cursor.lastrowid or 0)
            added += 1
        else:
            matched += 1
        id_map[bundle_id] = live_id

    for species in bundle.species:
        accepted = species["accepted_species_id"]
        if accepted is not None and accepted in id_map:
            live.execute(
                "UPDATE species SET accepted_species_id = ? WHERE species_id = ?",
                (id_map[accepted], id_map[species["species_id"]]),
            )
    return id_map, added, matched


def import_release(bundle_path: Path, catalog_path: Optional[Path] = None) -> ImportResult:
    bundle = _read_bundle(Path(bundle_path))
    path = Path(catalog_path or default_catalog_path())
    if not path.is_file():
        raise CatalogImportError(f"No live catalogue at {path}")

    live = sqlite3.connect(path, isolation_level=None)
    live.row_factory = sqlite3.Row
    try:
        live.execute("PRAGMA foreign_keys = ON")
        head = catalog_migration_heads()[0]
        if _schema_revision(live) != head:
            raise CatalogImportError("Live catalogue schema is not at the expected head; run migrations first")

        live.execute("BEGIN IMMEDIATE")
        try:
            existing = live.execute(
                "SELECT id FROM catalogue_releases WHERE content_sha256 = ?",
                (bundle.release["content_sha256"],),
            ).fetchone()
            if existing:
                live.execute("ROLLBACK")
                log.info("Catalogue release already imported", release_id=existing["id"])
                return ImportResult(status="already_imported", release_id=existing["id"])

            cursor = live.execute(
                "INSERT INTO catalogue_releases (schema_version, source_manifest, content_sha256, generated_at, state)"
                " VALUES (?, ?, ?, ?, 'staged')",
                (
                    bundle.release["schema_version"],
                    bundle.release["source_manifest"],
                    bundle.release["content_sha256"],
                    bundle.release["generated_at"],
                ),
            )
            release_id = int(cursor.lastrowid or 0)

            id_map, added, matched = _map_species(live, bundle)

            for concept in bundle.concepts:
                live.execute(
                    "INSERT INTO species_concepts"
                    " (species_id, provider, provider_taxon_id, source_release, scientific_name,"
                    "  authorship, accepted_name_usage, status)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT (provider, source_release, provider_taxon_id) DO NOTHING",
                    (
                        id_map[concept["species_id"]],
                        concept["provider"],
                        concept["provider_taxon_id"],
                        concept["source_release"],
                        concept["scientific_name"],
                        concept["authorship"],
                        concept["accepted_name_usage"],
                        concept["status"],
                    ),
                )

            names_before = live.total_changes
            for name in bundle.names:
                live.execute(
                    "INSERT INTO species_names"
                    " (species_id, language_tag, name, name_kind, preferred, region, provider, source_release)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT (species_id, language_tag, provider, source_release, name) DO NOTHING",
                    (
                        id_map[name["species_id"]],
                        name["language_tag"],
                        name["name"],
                        name["name_kind"],
                        name["preferred"],
                        name["region"],
                        name["provider"],
                        name["source_release"],
                    ),
                )
            names_added = live.total_changes - names_before

            _before_activation(live)
            live.execute("UPDATE catalogue_releases SET state = 'retired' WHERE state = 'active'")
            live.execute(
                "UPDATE catalogue_releases SET state = 'active', activated_at = ? WHERE id = ?",
                (datetime.now(UTC).isoformat(), release_id),
            )
            live.execute("COMMIT")
        except CatalogImportError:
            live.execute("ROLLBACK")
            raise
        except Exception as error:
            live.execute("ROLLBACK")
            raise CatalogImportError(f"Import interrupted, previous release left active: {error}") from error
    finally:
        live.close()

    log.info(
        "Catalogue release imported",
        release_id=release_id,
        species_added=added,
        species_matched=matched,
        names_added=names_added,
    )
    return ImportResult(
        status="imported",
        release_id=release_id,
        species_added=added,
        species_matched=matched,
        names_added=names_added,
    )


def rollback_to_release(release_id: int, catalog_path: Optional[Path] = None) -> None:
    """Reactivate a retired release. Identities and rows are kept, only the
    active-release pointer moves; that is what makes a refresh reversible."""
    path = Path(catalog_path or default_catalog_path())
    live = sqlite3.connect(path, isolation_level=None)
    try:
        live.execute("BEGIN IMMEDIATE")
        try:
            row = live.execute("SELECT state FROM catalogue_releases WHERE id = ?", (release_id,)).fetchone()
            if row is None or row[0] != "retired":
                raise CatalogImportError(f"Release {release_id} is not a retired release; nothing to roll back to")
            live.execute("UPDATE catalogue_releases SET state = 'retired' WHERE state = 'active'")
            live.execute(
                "UPDATE catalogue_releases SET state = 'active', activated_at = ? WHERE id = ?",
                (datetime.now(UTC).isoformat(), release_id),
            )
            live.execute("COMMIT")
        except CatalogImportError:
            live.execute("ROLLBACK")
            raise
        except Exception as error:
            live.execute("ROLLBACK")
            raise CatalogImportError(f"Rollback interrupted, nothing changed: {error}") from error
    finally:
        live.close()
    log.info("Catalogue rolled back", release_id=release_id)
