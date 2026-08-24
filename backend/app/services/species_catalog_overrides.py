"""Record an owner's rename in the catalogue, against the species it names.

A rename is the one piece of naming an owner authored. It lived in
`taxonomy_cache.manual_common_name`, beside columns that are a cache of
provider answers and can be refetched at will, and it was keyed on a spelling
of a scientific name rather than on the species -- so a taxon that is renamed
upstream loses the name its owner gave it.

The catalogue has held `species_name_overrides` since its first migration, and
`choose_display_name` already prefers it over every other source. Nothing ever
wrote to it, which is why the same precedence had to be hand-rolled wherever a
name was chosen. This writes it.

Fail-soft throughout: a catalogue that is absent, unreadable, or does not hold
the species reports failure and changes nothing, and the caller keeps the
detection-database copy that the pre-3.0 compatibility readers still use.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Optional

import structlog

from app.services.species_catalog_migrations import default_catalog_path

log = structlog.get_logger()

#: The scope of a rename that names the bird rather than one translation of it.
#: Empty rather than NULL because SQLite treats NULLs as distinct, which would
#: make the table's uniqueness constraint unenforceable.
ALL_LANGUAGES = ""


def _open_writable(catalog_path: Optional[Path]) -> Optional[sqlite3.Connection]:
    path = Path(catalog_path or default_catalog_path())
    if not path.is_file():
        return None
    try:
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("SELECT 1 FROM species_name_overrides LIMIT 1").fetchone()
    except sqlite3.Error:
        try:
            connection.close()
        except (sqlite3.Error, UnboundLocalError):  # pragma: no cover - defensive
            pass
        return None
    return connection


def write_catalogue_override(
    species_id: int,
    name: str,
    *,
    language_tag: str = ALL_LANGUAGES,
    overwrite: bool = True,
    catalog_path: Optional[Path] = None,
) -> bool:
    """Record `name` as the owner's name for this species. True when stored.

    `overwrite=False` fills a gap without touching a rename already recorded,
    which is what the migration from the detection database needs: it must
    never resurrect a name the owner has since changed or cleared.
    """
    cleaned = str(name or "").strip()
    if not cleaned or species_id is None:
        return False

    connection = _open_writable(catalog_path)
    if connection is None:
        return False
    on_conflict = (
        " ON CONFLICT (species_id, language_tag) DO UPDATE SET name = excluded.name, updated_at = CURRENT_TIMESTAMP"
        if overwrite
        else " ON CONFLICT (species_id, language_tag) DO NOTHING"
    )
    try:
        with connection:
            cursor = connection.execute(
                "INSERT INTO species_name_overrides (species_id, language_tag, name) VALUES (?, ?, ?)" + on_conflict,
                (int(species_id), str(language_tag or ALL_LANGUAGES), cleaned),
            )
            # With `DO NOTHING` a conflict writes no row, and the caller needs
            # to know that a rename was already there rather than assume it
            # stored one.
            written = (cursor.rowcount or 0) > 0
    except sqlite3.Error as error:
        # An unknown species is refused by the foreign key rather than stored
        # against nothing, which is the behaviour worth keeping.
        log.debug("Owner rename not recorded in the catalogue", species_id=species_id, error=str(error))
        return False
    finally:
        connection.close()
    return written


def clear_catalogue_override(
    species_id: int,
    *,
    language_tag: str = ALL_LANGUAGES,
    catalog_path: Optional[Path] = None,
) -> bool:
    """Remove the owner's name for this species. True when one was removed."""
    if species_id is None:
        return False

    connection = _open_writable(catalog_path)
    if connection is None:
        return False
    try:
        with connection:
            cursor = connection.execute(
                "DELETE FROM species_name_overrides WHERE species_id = ? AND language_tag = ?",
                (int(species_id), str(language_tag or ALL_LANGUAGES)),
            )
            removed = cursor.rowcount or 0
    except sqlite3.Error as error:
        log.debug("Owner rename not cleared in the catalogue", species_id=species_id, error=str(error))
        return False
    finally:
        connection.close()
    return removed > 0


def catalogue_override_count(catalog_path: Optional[Path] = None) -> Optional[int]:
    """How many renames the catalogue holds, or None if it cannot be read."""
    connection = _open_writable(catalog_path)
    if connection is None:
        return None
    try:
        return int(connection.execute("SELECT COUNT(*) FROM species_name_overrides").fetchone()[0])
    except sqlite3.Error:  # pragma: no cover - defensive
        return None
    finally:
        connection.close()


def override_summary(catalog_path: Optional[Path] = None) -> dict[str, Any]:
    count = catalogue_override_count(catalog_path)
    return {"available": count is not None, "overrides": count or 0}


async def migrate_cache_overrides(db, catalog_path: Optional[Path] = None) -> dict[str, Any]:
    """Copy renames from the detection database into the catalogue.

    One-way and gap-filling: a species the catalogue already has a rename for
    is left alone, so a name the owner has since changed or cleared is never
    resurrected by a later startup. A name whose spelling resolves to no single
    catalogue species is counted and left where it is, because the detection
    database keeps serving it through the compatibility readers.
    """
    import asyncio

    from app.services.species_catalog_resolver import species_catalog_resolver

    summary: dict[str, Any] = {"status": "complete", "migrated": 0, "already_present": 0, "unresolved": 0}
    try:
        async with db.execute(
            "SELECT scientific_name, manual_common_name FROM taxonomy_cache"
            " WHERE manual_common_name IS NOT NULL AND TRIM(manual_common_name) <> ''"
        ) as cursor:
            rows = await cursor.fetchall()
    except Exception as error:
        log.debug("Owner renames not read for migration", error=str(error))
        return {"status": "unavailable", "migrated": 0, "already_present": 0, "unresolved": 0}

    for scientific_name, manual_name in rows:
        species_id, reason = await asyncio.to_thread(species_catalog_resolver.resolve_scientific_name, scientific_name)
        if reason == "unavailable":
            return {**summary, "status": "unavailable"}
        if species_id is None:
            summary["unresolved"] += 1
            continue
        stored = await asyncio.to_thread(
            write_catalogue_override,
            species_id,
            manual_name,
            overwrite=False,
            catalog_path=catalog_path,
        )
        summary["migrated" if stored else "already_present"] += 1

    if summary["migrated"]:
        log.info("Owner renames recorded in the catalogue", **summary)
    return summary
