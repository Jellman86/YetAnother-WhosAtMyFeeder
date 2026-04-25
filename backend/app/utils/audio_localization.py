"""Shared helpers for localizing BirdNET-Go species names at response time.

BirdNET-Go publishes `comName` in whichever locale it is configured for.
These helpers canonicalize those strings to the user's display language
via `taxonomy_cache` — the same transform applied to visual detections.
"""
import structlog
import aiosqlite
from app.services.taxonomy.taxonomy_service import taxonomy_service

log = structlog.get_logger()


async def _resolve_taxa_id(
    db: aiosqlite.Connection,
    scientific: str | None,
    species: str | None,
) -> int | None:
    """Resolve a taxa_id from whatever identifier we have.

    Order of preference:
      1. `scientific` looks like a real Latin scientific name and the
         taxonomy_cache row keyed by it has a non-null taxa_id.
      2. `taxonomy_cache.common_name` row matches `species` text (handles
         the case where BirdNET-Go has been running in English and the
         canonical English name is what got cached visually).
      3. `taxonomy_translations.common_name` row matches `species` text
         in *any* language code (handles BirdNET-Go running in Russian /
         German / etc., where the visual path has already cached the
         localised name during a prior visual classification of the same
         species).

    Returns the resolved taxa_id, or None if no path yields one. Returning
    None means we fall back to the stored species string verbatim.
    """
    scientific = (scientific or "").strip()
    species = (species or "").strip()

    if scientific:
        try:
            taxonomy = await taxonomy_service._query_cache(db, scientific)
        except Exception as exc:
            log.warning("Audio taxonomy cache lookup failed", scientific=scientific, error=str(exc))
            taxonomy = None
        if taxonomy and taxonomy.get("taxa_id"):
            return int(taxonomy["taxa_id"])

    if not species:
        return None

    # Fall back to matching by stored species text. The stored value may be
    # in *any* language depending on how BirdNET-Go was configured at
    # ingest time. We never call out to iNaturalist here — only consult
    # already-populated tables — so this is cheap enough to run per request.
    try:
        async with db.execute(
            "SELECT taxa_id FROM taxonomy_cache WHERE LOWER(common_name) = LOWER(?) AND taxa_id IS NOT NULL LIMIT 1",
            (species,),
        ) as cursor:
            row = await cursor.fetchone()
        if row and row[0]:
            return int(row[0])
    except Exception as exc:
        log.warning("Audio taxonomy_cache common-name lookup failed", species=species, error=str(exc))

    try:
        async with db.execute(
            "SELECT taxa_id FROM taxonomy_translations WHERE LOWER(common_name) = LOWER(?) LIMIT 1",
            (species,),
        ) as cursor:
            row = await cursor.fetchone()
        if row and row[0]:
            return int(row[0])
    except Exception as exc:
        log.warning("Audio taxonomy_translations lookup failed", species=species, error=str(exc))

    return None


async def localize_audio_detections(
    detections: list[dict],
    lang: str,
    db: aiosqlite.Connection,
) -> None:
    """In-place: replace locale-dependent `species` in a list of audio detection dicts.

    Each dict should have a `scientific_name` key (may be None/empty) and a
    `species` key. Dicts that yield no resolvable taxa_id by either path
    are left unchanged — graceful degradation.
    """
    taxa_id_cache: dict[tuple[str, str], int | None] = {}
    for d in detections:
        scientific = (d.get("scientific_name") or "").strip()
        species = (d.get("species") or "").strip()
        cache_key = (scientific, species)

        if cache_key in taxa_id_cache:
            taxa_id = taxa_id_cache[cache_key]
        else:
            taxa_id = await _resolve_taxa_id(db, scientific, species)
            taxa_id_cache[cache_key] = taxa_id

        if not taxa_id:
            continue

        try:
            if lang != "en":
                resolved = await taxonomy_service.get_localized_common_name(taxa_id, lang, db=db)
            else:
                resolved = await taxonomy_service.get_canonical_english_name(taxa_id, db=db)
        except Exception as exc:
            log.warning("Audio name localization failed", scientific=scientific, species=species, lang=lang, error=str(exc))
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

    # Unconfirmed: look up scientific_name from audio_detections, then go
    # through the same shared resolver so we benefit from common_name and
    # translation fallbacks.
    try:
        async with db.execute(
            "SELECT scientific_name FROM audio_detections WHERE species = ? AND scientific_name IS NOT NULL LIMIT 1",
            (comname.strip(),),
        ) as cursor:
            row = await cursor.fetchone()
    except Exception as exc:
        log.warning("Audio scientific_name lookup failed", species=comname, error=str(exc))
        row = None

    scientific = row[0].strip() if row and row[0] else None
    taxa_id = await _resolve_taxa_id(db, scientific, comname)
    if not taxa_id:
        return None

    try:
        if lang != "en":
            return await taxonomy_service.get_localized_common_name(taxa_id, lang, db=db)
        else:
            return await taxonomy_service.get_canonical_english_name(taxa_id, db=db)
    except Exception as exc:
        log.warning("Audio unconfirmed name localization failed", species=comname, error=str(exc))
        return None
