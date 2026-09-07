"""Backfill canonical catalogue identity onto existing detection history.

Phase 3's conservative backfill: a detection whose `scientific_name` resolves
to exactly one catalogue identity — through a concept or a recorded resolved
synonym — gains a `species_id`. Everything else stays exactly as it is and is
counted, never guessed. Name snapshots and artifact provenance are never
touched, and re-running is a no-op, so the backfill is safe to schedule on
every startup.

An identity already present is replaced in exactly one case: when it names a
different bird than the row's own scientific name. Manual corrections made
before they carried identity left the old bird's `species_id` under the new
name (#386), and the name is what the owner asserted, so the identity is
re-derived from it under the same "exactly one match" rule.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Optional

import structlog

from app.repositories.detection_repository import DetectionRepository
from app.services.species_catalog_resolver import SpeciesCatalogResolver, species_catalog_resolver

log = structlog.get_logger()

_summary_lock = threading.Lock()
_last_summary: Optional[dict[str, Any]] = None


def last_backfill_summary() -> Optional[dict[str, Any]]:
    with _summary_lock:
        return dict(_last_summary) if _last_summary else None


def _record_summary(summary: dict[str, Any]) -> None:
    global _last_summary
    with _summary_lock:
        _last_summary = dict(summary)


def _new_summary() -> dict[str, Any]:
    return {
        "status": "complete",
        "names_resolved": 0,
        "names_ambiguous": 0,
        "names_unresolved": 0,
        "rows_identified": 0,
        "names_repaired": 0,
        "rows_repaired": 0,
    }


async def _read_names(repository: DetectionRepository) -> tuple[list[str], list[str], list[tuple[str, int]]]:
    """Everything the backfill works from: detection names without identity,
    detection names with one, and audio names without one."""
    without_identity = await repository.distinct_scientific_names_without_identity()
    with_identity = await repository.distinct_scientific_names_with_identity()
    try:
        pending_audio = await repository.pending_audio_scientific_names()
    except Exception as error:  # pragma: no cover - defensive, as the audio pass always was
        log.warning("Audio identity backfill skipped", error=str(error))
        pending_audio = []
    return without_identity, with_identity, pending_audio


async def _resolve_audio_identities(pending: list[tuple[str, int]], resolver: SpeciesCatalogResolver) -> dict:
    """The audio identities, resolved off any database connection."""
    from app.services.audio_identity import resolve_audio_identity

    identities: dict[str, Optional[int]] = {}
    for name, _count in pending:
        identities[name] = await asyncio.to_thread(resolve_audio_identity, name, resolver=resolver)
    return identities


async def _resolve_names(
    names: list[str], resolver: SpeciesCatalogResolver
) -> Optional[list[tuple[str, Optional[int], Optional[str]]]]:
    """Ask the catalogue about each name. Needs no database connection.

    Returns ``None`` when the catalogue is unavailable, so a caller writes
    nothing rather than half of a pass.
    """
    resolved: list[tuple[str, Optional[int], Optional[str]]] = []
    for name in names:
        species_id, reason = await asyncio.to_thread(resolver.resolve_scientific_name, name)
        if reason == "unavailable":
            return None
        resolved.append((name, species_id, reason))
    return resolved


IdentityPlan = tuple[
    list[tuple[str, Optional[int], Optional[str]]],
    list[tuple[str, Optional[int], Optional[str]]],
    list[tuple[str, int]],
    dict[str, Optional[int]],
]


async def _resolve_plan(
    names: tuple[list[str], list[str], list[tuple[str, int]]], resolver: SpeciesCatalogResolver
) -> Optional[IdentityPlan]:
    """Consult the catalogue for every name read; needs no database connection."""
    without_identity, with_identity, pending_audio = names
    resolved_without = await _resolve_names(without_identity, resolver)
    if resolved_without is None:
        return None
    resolved_with = await _resolve_names(with_identity, resolver)
    if resolved_with is None:
        return None
    audio_identities = await _resolve_audio_identities(pending_audio, resolver)
    return resolved_without, resolved_with, pending_audio, audio_identities


async def _apply_plan(repository: DetectionRepository, plan: IdentityPlan, summary: dict[str, Any]) -> None:
    resolved_without, resolved_with, _pending_audio, _audio_identities = plan
    for name, species_id, reason in resolved_without:
        if species_id is not None:
            summary["names_resolved"] += 1
            summary["rows_identified"] += await repository.assign_species_id_by_scientific_name(name, species_id)
        elif reason == "ambiguous":
            summary["names_ambiguous"] += 1
        else:
            summary["names_unresolved"] += 1
    # A row whose identity contradicts its own scientific name is a manual
    # correction from before corrections carried identity. The name is the
    # owner's word; the stale id is not, and it splits the leaderboard.
    for name, species_id, _reason in resolved_with:
        if species_id is None:
            continue
        repaired = await repository.repair_species_id_by_scientific_name(name, species_id)
        if repaired:
            summary["names_repaired"] += 1
            summary["rows_repaired"] += repaired


async def _backfill_audio_and_overrides(
    db, repository: DetectionRepository, plan: IdentityPlan, summary: dict[str, Any]
) -> None:
    # Audio detections carry the same identity, for the same reason: grouping
    # audio by identity while older rows have none would split a species at the
    # upgrade boundary. Reported separately so an audio-only shortfall is
    # visible rather than folded into the detection numbers.
    _without, _with, pending_audio, audio_identities = plan
    try:
        audio = await repository.assign_audio_species_ids(pending_audio, audio_identities)
        summary["audio_rows_identified"] = audio.get("identified", 0)
        summary["audio_rows_unresolved"] = audio.get("unresolved", 0)
    except Exception as error:  # pragma: no cover - defensive
        log.warning("Audio identity backfill skipped", error=str(error))
        summary["audio_rows_identified"] = 0
        summary["audio_rows_unresolved"] = 0
    # Owner renames move to the catalogue in the same pass, because they are
    # the one piece of naming the owner authored and they were living in a
    # cache of provider answers.
    try:
        from app.services.species_catalog_overrides import migrate_cache_overrides

        overrides = await migrate_cache_overrides(db)
        summary["overrides_migrated"] = overrides.get("migrated", 0)
        summary["overrides_unresolved"] = overrides.get("unresolved", 0)
    except Exception as error:  # pragma: no cover - defensive
        log.warning("Owner rename migration skipped", error=str(error))
        summary["overrides_migrated"] = 0
        summary["overrides_unresolved"] = 0


async def backfill_catalog_identity(db, resolver: Optional[SpeciesCatalogResolver] = None) -> dict[str, Any]:
    """Fill `species_id` on rows whose scientific name resolves unambiguously.

    Works on a connection the caller already holds. The startup task uses
    :func:`backfill_catalog_identity_in_short_holds` instead, so the pool is
    not tied up while the catalogue is consulted.
    """
    active_resolver = resolver or species_catalog_resolver
    repository = DetectionRepository(db)
    summary = _new_summary()
    plan = await _resolve_plan(await _read_names(repository), active_resolver)
    if plan is None:
        summary["status"] = "unavailable"
        _record_summary(summary)
        return summary
    await _apply_plan(repository, plan, summary)
    await _backfill_audio_and_overrides(db, repository, plan, summary)
    _record_summary(summary)
    return summary


async def backfill_catalog_identity_in_short_holds(
    resolver: Optional[SpeciesCatalogResolver] = None,
) -> dict[str, Any]:
    """The same backfill, holding a pooled connection only to read and to write.

    Resolving a name means consulting the catalogue, which is not this
    database, and there can be hundreds of names on an older install. Holding
    one of the pool's five connections for the whole pass, at startup, put the
    backfill in front of the dashboard's first load on every restart.
    """
    from app.database import get_db

    active_resolver = resolver or species_catalog_resolver
    summary = _new_summary()
    async with get_db() as db:
        names = await _read_names(DetectionRepository(db))
    plan = await _resolve_plan(names, active_resolver)
    if plan is None:
        summary["status"] = "unavailable"
        _record_summary(summary)
        return summary
    async with get_db() as db:
        repository = DetectionRepository(db)
        await _apply_plan(repository, plan, summary)
        await _backfill_audio_and_overrides(db, repository, plan, summary)
    _record_summary(summary)
    return summary


async def start_background_catalog_backfill() -> None:
    """Run the backfill detached from startup; never fatal, always reported."""
    try:
        summary = await backfill_catalog_identity_in_short_holds()
        log.info("Catalogue identity backfill finished", **summary)
    except Exception as error:
        _record_summary({"status": "failed", "error": str(error)})
        log.warning("Catalogue identity backfill failed", error=str(error))
