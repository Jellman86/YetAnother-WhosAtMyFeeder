"""Backfill canonical catalogue identity onto existing detection history.

Phase 3's conservative backfill: a detection whose `scientific_name` resolves
to exactly one catalogue identity — through a concept or a recorded resolved
synonym — gains a `species_id`. Everything else stays exactly as it is and is
counted, never guessed. Name snapshots and artifact provenance are never
touched, an identity already present is never replaced, and re-running is a
no-op, so the backfill is safe to schedule on every startup.
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


async def backfill_catalog_identity(db, resolver: Optional[SpeciesCatalogResolver] = None) -> dict[str, Any]:
    """Fill `species_id` on rows whose scientific name resolves unambiguously."""
    active_resolver = resolver or species_catalog_resolver
    repository = DetectionRepository(db)

    summary: dict[str, Any] = {
        "status": "complete",
        "names_resolved": 0,
        "names_ambiguous": 0,
        "names_unresolved": 0,
        "rows_identified": 0,
    }

    names = await repository.distinct_scientific_names_without_identity()
    for name in names:
        species_id, reason = await asyncio.to_thread(active_resolver.resolve_scientific_name, name)
        if reason == "unavailable":
            summary["status"] = "unavailable"
            _record_summary(summary)
            return summary
        if species_id is not None:
            summary["names_resolved"] += 1
            summary["rows_identified"] += await repository.assign_species_id_by_scientific_name(name, species_id)
        elif reason == "ambiguous":
            summary["names_ambiguous"] += 1
        else:
            summary["names_unresolved"] += 1

    # Audio detections carry the same identity, for the same reason: grouping
    # audio by identity while older rows have none would split a species at the
    # upgrade boundary. Reported separately so an audio-only shortfall is
    # visible rather than folded into the detection numbers.
    try:
        audio = await repository.backfill_audio_species_ids(resolver=active_resolver)
        summary["audio_rows_identified"] = audio.get("identified", 0)
        summary["audio_rows_unresolved"] = audio.get("unresolved", 0)
    except Exception as error:  # pragma: no cover - defensive
        log.warning("Audio identity backfill skipped", error=str(error))
        summary["audio_rows_identified"] = 0
        summary["audio_rows_unresolved"] = 0

    _record_summary(summary)
    return summary


async def start_background_catalog_backfill() -> None:
    """Run the backfill detached from startup; never fatal, always reported."""
    from app.database import get_db

    try:
        async with get_db() as db:
            summary = await backfill_catalog_identity(db)
        log.info("Catalogue identity backfill finished", **summary)
    except Exception as error:
        _record_summary({"status": "failed", "error": str(error)})
        log.warning("Catalogue identity backfill failed", error=str(error))
