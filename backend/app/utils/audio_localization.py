"""Shared helpers for localizing BirdNET-Go species names at response time.

BirdNET-Go publishes `comName` in whichever locale it is configured for.
These helpers canonicalize those strings to the user's display language
via `taxonomy_cache` — the same transform applied to visual detections.
"""
import structlog
import aiosqlite
from app.services.taxonomy.taxonomy_service import taxonomy_service

log = structlog.get_logger()


async def localize_audio_detections(
    detections: list[dict],
    lang: str,
    db: aiosqlite.Connection,
) -> None:
    """In-place: replace locale-dependent `species` in a list of audio detection dicts.

    Each dict must have a `scientific_name` key (may be None/empty). Dicts without a
    resolvable scientific name are left unchanged — graceful degradation for older rows.
    """
    taxa_id_cache: dict[str, int | None] = {}
    for d in detections:
        scientific = (d.get("scientific_name") or "").strip()
        if not scientific:
            continue

        if scientific in taxa_id_cache:
            taxa_id = taxa_id_cache[scientific]
        else:
            try:
                taxonomy = await taxonomy_service._query_cache(db, scientific)
                taxa_id = taxonomy.get("taxa_id") if taxonomy else None
            except Exception as exc:
                log.warning("Audio taxonomy cache lookup failed", scientific=scientific, error=str(exc))
                taxa_id = None
            taxa_id_cache[scientific] = taxa_id

        if not taxa_id:
            continue

        try:
            if lang != "en":
                resolved = await taxonomy_service.get_localized_common_name(int(taxa_id), lang, db=db)
            else:
                resolved = await taxonomy_service.get_canonical_english_name(int(taxa_id), db=db)
        except Exception as exc:
            log.warning("Audio name localization failed", scientific=scientific, lang=lang, error=str(exc))
            resolved = None

        if resolved:
            d["species"] = resolved


async def localize_audio_species_name(
    comname: str | None,
    lang: str,
    db: aiosqlite.Connection,
    confirmed_taxa_id: int | None = None,
) -> str | None:
    """Return the canonical/localized name for a single BirdNET-Go `comName` string.

    When `confirmed_taxa_id` is provided (visual + audio matched the same species), we
    skip the audio_detections lookup and resolve directly — the visual taxa_id is
    authoritative. Otherwise, we look up the matching scientific name from audio_detections
    to drive the taxonomy resolution.

    Returns the resolved name, or None if it cannot be determined (caller should fall back
    to the original stored value).
    """
    if not comname:
        return None

    if confirmed_taxa_id is not None:
        try:
            if lang != "en":
                return await taxonomy_service.get_localized_common_name(confirmed_taxa_id, lang, db=db)
            else:
                return await taxonomy_service.get_canonical_english_name(confirmed_taxa_id, db=db)
        except Exception as exc:
            log.warning("Audio confirmed name localization failed", taxa_id=confirmed_taxa_id, error=str(exc))
            return None

    # Unconfirmed: look up scientific_name from audio_detections
    try:
        async with db.execute(
            "SELECT scientific_name FROM audio_detections WHERE species = ? AND scientific_name IS NOT NULL LIMIT 1",
            (comname.strip(),),
        ) as cursor:
            row = await cursor.fetchone()
        if not row or not row[0]:
            return None

        scientific = row[0].strip()
        taxonomy = await taxonomy_service._query_cache(db, scientific)
        taxa_id = taxonomy.get("taxa_id") if taxonomy else None
        if not taxa_id:
            return None

        if lang != "en":
            return await taxonomy_service.get_localized_common_name(int(taxa_id), lang, db=db)
        else:
            return await taxonomy_service.get_canonical_english_name(int(taxa_id), db=db)
    except Exception as exc:
        log.warning("Audio unconfirmed name localization failed", species=comname, error=str(exc))
        return None
