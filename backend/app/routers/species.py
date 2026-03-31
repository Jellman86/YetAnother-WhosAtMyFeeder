from fastapi import APIRouter, HTTPException, Request, Depends, Query
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
import asyncio
import httpx
import structlog
import re
import unicodedata
from typing import Literal

from app.database import get_db
from app.repositories.detection_repository import DetectionRepository
from app.models import SpeciesStats, SpeciesInfo, CameraStats, Detection, SpeciesRangeMap
from app.config import settings
from app.services.taxonomy.taxonomy_service import taxonomy_service
from app.services.i18n_service import i18n_service
from app.services.classifier_service import get_classifier
from app.services.ebird_service import ebird_service
from app.utils.classifier_labels import collapse_classifier_label
from app.utils.canonical_species import should_hide_species_label, user_facing_species_fields
from app.utils.language import get_user_language
from app.utils.enrichment import get_effective_enrichment_settings
from app.auth import require_owner, AuthContext
from app.auth import get_auth_context_with_legacy
from app.ratelimit import guest_rate_limit

router = APIRouter()
log = structlog.get_logger()

# Species info cache with TTL
_wiki_cache: dict[str, tuple[SpeciesInfo, datetime]] = {}
CACHE_TTL_SUCCESS = timedelta(hours=24)
CACHE_TTL_FAILURE = timedelta(minutes=1)  # Short TTL for failures to allow retries

# User-Agent is required by Wikipedia API - they block requests without it
WIKIPEDIA_USER_AGENT = "YA-WAMF/2.0 (Bird Watching App; https://github.com/Jellman86/YetAnother-WhosAtMyFeeder)"

GBIF_MATCH_URL = "https://api.gbif.org/v1/species/match"
GBIF_TILE_URL = "https://api.gbif.org/v2/map/occurrence/density/{z}/{x}/{y}@1x.png"
GBIF_CACHE_TTL = timedelta(hours=24)
_gbif_cache: dict[str, tuple[int | None, datetime]] = {}
SPECIES_SEARCH_HYDRATE_MAX = 30
SPECIES_SEARCH_HYDRATE_CONCURRENCY = 6
SPECIES_SEARCH_HYDRATE_LOOKUP_TIMEOUT = 2.5
SPECIES_SEARCH_HYDRATE_TRANSLATION_TIMEOUT = 1.5
SCIENTIFIC_NAME_PATTERN = re.compile(r"^[A-Z][a-z]+(?: [a-z][a-z-]+){1,3}$")

# Species names that should NOT trigger Wikipedia lookup (no valid article exists)
SKIP_WIKIPEDIA_LOOKUP = {
    "Unknown Bird",
    "Background",
    "Unknown",
    "No Detection",
    "Unidentified"
}
SKIP_LOOKUP_NORMALIZED = {name.lower() for name in SKIP_WIKIPEDIA_LOOKUP}

def _parse_cached_at(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None

def _is_cache_valid(info: SpeciesInfo, cached_at: datetime | None) -> bool:
    if not cached_at:
        return False
    is_success = bool(info.thumbnail_url or info.extract)
    cache_ttl = CACHE_TTL_SUCCESS if is_success else CACHE_TTL_FAILURE
    return datetime.now() - cached_at < cache_ttl


def _normalize_provider(provider: str | None) -> str:
    if not provider:
        return "wikipedia"
    normalized = provider.strip().lower()
    if normalized in ("inat", "inaturalist"):
        return "inaturalist"
    if normalized in ("wiki", "wikipedia"):
        return "wikipedia"
    if normalized == "ebird":
        return "ebird"
    if normalized == "disabled":
        return "wikipedia"
    return normalized


def _resolve_summary_sources() -> list[str]:
    effective = get_effective_enrichment_settings()
    mode = (effective["mode"] or "per_enrichment").strip().lower()
    if mode == "single":
        primary = _normalize_provider(effective["single_provider"])
    else:
        primary = _normalize_provider(effective["summary_source"])
    fallback = "wikipedia" if primary != "wikipedia" else "inaturalist"
    return [primary, fallback]

async def _get_gbif_taxon_key(name: str) -> int | None:
    if not name:
        return None
    normalized = name.strip().lower()
    cached = _gbif_cache.get(normalized)
    if cached and datetime.now() - cached[1] < GBIF_CACHE_TTL:
        return cached[0]

    params = {"name": name}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(GBIF_MATCH_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        log.warning("GBIF match failed", species=name, error=str(e))
        return None

    key = data.get("usageKey") or data.get("speciesKey") or None
    if key is not None:
        try:
            key = int(key)
        except (TypeError, ValueError):
            key = None

    _gbif_cache[normalized] = (key, datetime.now())
    return key

async def _lookup_taxa_id(species_name: str, language: str | None = None) -> int | None:
    async with get_db() as db:
        repo = DetectionRepository(db)
        taxonomy = await repo.get_taxonomy_names(species_name, language=language)
    if taxonomy.get("taxa_id") is not None:
        return int(taxonomy["taxa_id"])
    return None


def _should_hydrate_species_label(label: str) -> bool:
    normalized = (label or "").strip().lower()
    if not normalized:
        return False
    if normalized in SKIP_LOOKUP_NORMALIZED:
        return False
    unknown_labels = getattr(settings.classification, "unknown_bird_labels", None) or []
    if normalized in {str(name).lower() for name in unknown_labels}:
        return False
    return True


def _looks_like_scientific_name(value: str | None) -> bool:
    return bool(value and SCIENTIFIC_NAME_PATTERN.match(value.strip()))


def _split_species_alias_parts(label: str | None) -> tuple[str | None, str | None]:
    raw = str(label or "").strip()
    if not raw:
        return None, None

    match = re.match(r"^(.*?)\s*\((.*?)\)\s*$", raw)
    if not match:
        return None, None
    left = match.group(1).strip()
    right = match.group(2).strip()
    return (left or None), (right or None)


def _parse_species_alias_label(label: str | None) -> tuple[str | None, str | None]:
    left, right = _split_species_alias_parts(label)
    if not left or not right:
        return None, None

    left_is_scientific = _looks_like_scientific_name(left)
    right_is_scientific = _looks_like_scientific_name(right)
    if left_is_scientific and not right_is_scientific:
        return left, right
    if right_is_scientific and not left_is_scientific:
        return right, left
    return None, None


async def _lookup_species_search_taxonomy(
    db,
    *,
    label: str,
    lang: str,
) -> tuple[str | None, str | None, int | None]:
    candidates: list[str] = []
    left, right = _split_species_alias_parts(label)
    for candidate in [label, left, right, *_parse_species_alias_label(label)]:
        text = str(candidate or "").strip()
        if text and text not in candidates:
            candidates.append(text)

    for candidate in candidates:
        async with db.execute(
            """
            SELECT scientific_name, common_name, taxa_id
            FROM taxonomy_cache
            WHERE LOWER(scientific_name) = LOWER(?) OR LOWER(common_name) = LOWER(?)
            LIMIT 1
            """,
            (candidate, candidate),
        ) as cursor:
            row = await cursor.fetchone()
        if row:
            scientific_name = row[0]
            common_name = row[1]
            taxa_id = row[2]
            if lang != "en" and taxa_id:
                async with db.execute(
                    "SELECT common_name FROM taxonomy_translations WHERE taxa_id = ? AND language_code = ?",
                    (taxa_id, lang),
                ) as cursor:
                    translated = await cursor.fetchone()
                if translated and translated[0]:
                    common_name = translated[0]
            return scientific_name, common_name, taxa_id

    scientific_name, common_name = _parse_species_alias_label(label)
    return scientific_name, common_name, None


def _species_search_result_key(result: dict) -> str:
    taxa_id = result.get("taxa_id")
    if taxa_id is not None:
        return f"taxa:{taxa_id}"
    scientific_name = str(result.get("scientific_name") or "").strip()
    if scientific_name:
        return f"sci:{scientific_name.casefold()}"
    common_name = str(result.get("common_name") or "").strip()
    if common_name:
        return f"common:{common_name.casefold()}"
    display_name = str(result.get("display_name") or result.get("id") or "").strip()
    return f"label:{display_name.casefold()}"


def _pick_preferred_species_search_result(existing: dict, candidate: dict) -> dict:
    existing_taxa = existing.get("taxa_id")
    candidate_taxa = candidate.get("taxa_id")
    if existing_taxa is None and candidate_taxa is not None:
        return candidate
    if candidate_taxa is None and existing_taxa is not None:
        return existing

    existing_sci = bool(existing.get("scientific_name"))
    candidate_sci = bool(candidate.get("scientific_name"))
    if not existing_sci and candidate_sci:
        return candidate
    if existing_sci and not candidate_sci:
        return existing

    existing_common = bool(existing.get("common_name"))
    candidate_common = bool(candidate.get("common_name"))
    if not existing_common and candidate_common:
        return candidate
    if existing_common and not candidate_common:
        return existing

    return existing


async def _hydrate_species_search_results(
    results: list[dict],
    lang: str,
) -> None:
    """Best-effort enrichment for labels lacking common/scientific names."""
    candidates: list[dict] = []
    for result in results:
        if result.get("scientific_name") and result.get("common_name"):
            continue
        label = str(result.get("id") or result.get("display_name") or "").strip()
        if not _should_hydrate_species_label(label):
            continue
        candidates.append(result)
        if len(candidates) >= SPECIES_SEARCH_HYDRATE_MAX:
            break

    if not candidates:
        return

    semaphore = asyncio.Semaphore(SPECIES_SEARCH_HYDRATE_CONCURRENCY)

    async def _hydrate_one(item: dict) -> None:
        label = str(item.get("id") or item.get("display_name") or "").strip()
        if not label:
            return
        lookup_label = collapse_classifier_label(label, strategy="strip_trailing_parenthetical")
        async with semaphore:
            try:
                taxonomy = await asyncio.wait_for(
                    taxonomy_service.get_names(lookup_label),
                    timeout=SPECIES_SEARCH_HYDRATE_LOOKUP_TIMEOUT,
                )
            except Exception as exc:
                log.warning("Species search taxonomy hydration failed", label=label, error=str(exc))
                return

            if not taxonomy:
                return

            if not item.get("scientific_name") and taxonomy.get("scientific_name"):
                item["scientific_name"] = taxonomy.get("scientific_name")

            common_name = taxonomy.get("common_name")
            taxa_id = taxonomy.get("taxa_id")
            if lang != "en" and taxa_id:
                try:
                    localized = await asyncio.wait_for(
                        taxonomy_service.get_localized_common_name(int(taxa_id), lang),
                        timeout=SPECIES_SEARCH_HYDRATE_TRANSLATION_TIMEOUT,
                    )
                    if localized:
                        common_name = localized
                except Exception as exc:
                    log.warning(
                        "Species search localized taxonomy hydration failed",
                        label=label,
                        taxa_id=taxa_id,
                        lang=lang,
                        error=str(exc),
                    )

            if not item.get("common_name") and common_name:
                item["common_name"] = common_name

    await asyncio.gather(*(_hydrate_one(item) for item in candidates), return_exceptions=True)


def _species_unified_metrics_key(row: dict) -> str | None:
    taxa_id = row.get("taxa_id")
    if taxa_id is not None:
        return str(taxa_id)
    scientific_name = row.get("scientific_name")
    if scientific_name:
        return str(scientific_name).lower()
    species = row.get("species")
    if species:
        return str(species).lower()
    return None


def _to_utc_naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


async def _get_cached_species_info(species_name: str, taxa_id: int | None, language: str, refresh: bool) -> SpeciesInfo | None:
    if refresh:
        return None

    cache_key = f"{species_name}:{language}"
    if cache_key in _wiki_cache:
        info, cached_at = _wiki_cache[cache_key]
        if _is_cache_valid(info, cached_at):
            log.debug("Returning cached species info (memory)", species=species_name)
            return info

    async with get_db() as db:
        if taxa_id:
            cursor = await db.execute(
                """SELECT title, description, extract, thumbnail_url, wikipedia_url, source, source_url,
                          summary_source, summary_source_url, scientific_name, conservation_status, cached_at, taxa_id
                   FROM species_info_cache WHERE taxa_id = ? AND language = ?
                   ORDER BY cached_at DESC LIMIT 1""",
                (taxa_id, language)
            )
        else:
            cursor = await db.execute(
                """SELECT title, description, extract, thumbnail_url, wikipedia_url, source, source_url,
                          summary_source, summary_source_url, scientific_name, conservation_status, cached_at, taxa_id
                   FROM species_info_cache WHERE species_name = ? AND language = ?""",
                (species_name, language)
            )
        row = await cursor.fetchone()

    if not row:
        return None

    cached_at = _parse_cached_at(row[11])
    info = SpeciesInfo(
        title=row[0] or species_name,
        description=row[1],
        extract=row[2],
        thumbnail_url=row[3],
        wikipedia_url=row[4],
        source=row[5],
        source_url=row[6],
        summary_source=row[7],
        summary_source_url=row[8],
        scientific_name=row[9],
        conservation_status=row[10],
        cached_at=cached_at,
        taxa_id=row[12]
    )

    if _is_cache_valid(info, cached_at):
        _wiki_cache[cache_key] = (info, cached_at or datetime.now())
        log.debug("Returning cached species info (db)", species=species_name)
        return info

    return None

async def _save_species_info(species_name: str, taxa_id: int | None, language: str, info: SpeciesInfo) -> None:
    cached_at = datetime.now()
    info.cached_at = cached_at
    async with get_db() as db:
        if taxa_id:
            cursor = await db.execute(
                "SELECT id FROM species_info_cache WHERE taxa_id = ? AND language = ? LIMIT 1",
                (taxa_id, language)
            )
            existing = await cursor.fetchone()
        else:
            existing = None

        if existing:
            cursor = await db.execute(
                "SELECT id FROM species_info_cache WHERE species_name = ? AND language = ? LIMIT 1",
                (species_name, language)
            )
            name_row = await cursor.fetchone()
            if name_row and name_row[0] != existing[0]:
                await db.execute(
                    "DELETE FROM species_info_cache WHERE id = ?",
                    (name_row[0],)
                )
            await db.execute(
                """UPDATE species_info_cache SET
                     species_name = ?,
                     language = ?,
                     title = ?,
                     taxa_id = ?,
                     description = ?,
                     extract = ?,
                     thumbnail_url = ?,
                     wikipedia_url = ?,
                     source = ?,
                     source_url = ?,
                     summary_source = ?,
                     summary_source_url = ?,
                     scientific_name = ?,
                     conservation_status = ?,
                     cached_at = ?
                   WHERE id = ?""",
                (
                    species_name,
                    language,
                    info.title,
                    taxa_id,
                    info.description,
                    info.extract,
                    info.thumbnail_url,
                    info.wikipedia_url,
                    info.source,
                    info.source_url,
                    info.summary_source,
                    info.summary_source_url,
                    info.scientific_name,
                    info.conservation_status,
                    cached_at,
                    existing[0]
                )
            )
        else:
            await db.execute(
                """INSERT INTO species_info_cache
                   (species_name, language, title, taxa_id, description, extract, thumbnail_url, wikipedia_url, source, source_url,
                    summary_source, summary_source_url, scientific_name, conservation_status, cached_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(species_name, language) DO UPDATE SET
                     language = excluded.language,
                     title = excluded.title,
                     taxa_id = excluded.taxa_id,
                     description = excluded.description,
                     extract = excluded.extract,
                     thumbnail_url = excluded.thumbnail_url,
                     wikipedia_url = excluded.wikipedia_url,
                     source = excluded.source,
                     source_url = excluded.source_url,
                     summary_source = excluded.summary_source,
                     summary_source_url = excluded.summary_source_url,
                     scientific_name = excluded.scientific_name,
                     conservation_status = excluded.conservation_status,
                     cached_at = excluded.cached_at""",
                (
                    species_name,
                    language,
                    info.title,
                    taxa_id,
                    info.description,
                    info.extract,
                    info.thumbnail_url,
                    info.wikipedia_url,
                    info.source,
                    info.source_url,
                    info.summary_source,
                    info.summary_source_url,
                    info.scientific_name,
                    info.conservation_status,
                    cached_at
                )
            )
        await db.commit()

@router.get("/species/search")
@guest_rate_limit()
async def search_species(
    request: Request,
    q: str = "",
    limit: int = 50,
    hydrate_missing: bool = Query(False, description="Best-effort hydrate missing taxonomy/common names"),
    auth: AuthContext = Depends(get_auth_context_with_legacy)
):
    """Search for species labels (from classifier) and return with taxonomy info."""
    q = (q or "").strip()
    limit = max(1, min(limit, 100))

    q_lower = q.lower() if q else ""
    classifier = get_classifier()
    labels = [
        label
        for label in classifier.labels
        if not should_hide_species_label(label)
    ]
    lang = get_user_language(request)

    async with get_db() as db:
        if q:
            matches = [label for label in labels if q_lower in label.lower()]

            # Include labels whose cached common/scientific names match the query.
            async with db.execute(
                """SELECT scientific_name, common_name
                   FROM taxonomy_cache
                   WHERE LOWER(scientific_name) LIKE ?
                      OR LOWER(common_name) LIKE ?""",
                (f"%{q_lower}%", f"%{q_lower}%")
            ) as cursor:
                cached_rows = await cursor.fetchall()

            label_set = set(labels)
            for sci_name, common_name in cached_rows:
                if sci_name and sci_name in label_set:
                    matches.append(sci_name)
                if common_name and common_name in label_set:
                    matches.append(common_name)

            # Include labels whose localized common names match the query.
            if lang != "en":
                async with db.execute(
                    """SELECT tc.scientific_name, tc.common_name
                       FROM taxonomy_translations tt
                       JOIN taxonomy_cache tc ON tc.taxa_id = tt.taxa_id
                       WHERE tt.language_code = ?
                         AND LOWER(tt.common_name) LIKE ?""",
                    (lang, f"%{q_lower}%")
                ) as cursor:
                    localized_rows = await cursor.fetchall()

                for sci_name, common_name in localized_rows:
                    if sci_name and sci_name in label_set:
                        matches.append(sci_name)
                    if common_name and common_name in label_set:
                        matches.append(common_name)

            seen = set()
            matches = [m for m in matches if not (m in seen or seen.add(m))]
        else:
            matches = labels

        matches = matches[:limit]

        deduped_results: dict[str, dict] = {}
        for label in matches:
            sci_name, common_name, taxa_id = await _lookup_species_search_taxonomy(
                db,
                label=label,
                lang=lang,
            )
            canonical_id = sci_name or common_name or label
            result = {
                "id": canonical_id,
                "display_name": canonical_id,
                "scientific_name": sci_name,
                "common_name": common_name,
                "taxa_id": taxa_id,
            }
            key = _species_search_result_key(result)
            existing = deduped_results.get(key)
            deduped_results[key] = _pick_preferred_species_search_result(existing, result) if existing else result

        results = list(deduped_results.values())

    if hydrate_missing and results:
        await _hydrate_species_search_results(results, lang)

    return results

def _is_bird_article(data: dict) -> bool:
    return _bird_relevance_score(data) >= 2


def _normalize_lookup_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[_\-]+", " ", normalized)
    normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def _tokenize_lookup_text(value: str | None) -> set[str]:
    normalized = _normalize_lookup_text(value)
    if not normalized:
        return set()
    return {token for token in normalized.split() if len(token) > 1}


def _contains_lookup_term(text: str, term: str) -> bool:
    # For short ASCII terms (e.g. "ave"), enforce word boundaries to avoid substring noise.
    if term.isascii() and len(term) <= 3:
        return re.search(rf"\b{re.escape(term)}\b", text) is not None
    return term in text


BIRD_DESCRIPTION_PHRASES = {
    # English
    "species of bird",
    "species of passerine",
    "species of songbird",
    "genus of bird",
    "genus of birds",
    "family of bird",
    "family of birds",
    "order of birds",
    "class of birds",
    # German
    "vogelart",
    "art der vögel",
    "familie der vögel",
    "gattung der vögel",
    # French
    "espèce d oiseau",
    "famille d oiseaux",
    "genre d oiseaux",
    # Spanish
    "especie de ave",
    "especie de pájaro",
    "familia de aves",
    "género de aves",
    # Italian
    "specie di uccello",
    "famiglia di uccelli",
    "genere di uccelli",
    # Portuguese
    "espécie de ave",
    "família de aves",
    # Russian
    "вид птиц",
    "вид птицы",
    "семейство птиц",
    "род птиц",
}


BIRD_TERMS = {
    # English stems
    "bird",
    "avian",
    "passerine",
    "songbird",
    # Romance/Germanic
    "oiseau",
    "uccell",
    "vogel",
    "ave",
    "aves",
    "pajaro",
    "pájaro",
    # Slavic / Cyrillic stems
    "птиц",
    "птица",
    "птич",
    "воробьинообраз",
    "синиц",
    # CJK
    "鳥",
    "鸟",
}


BIRD_TAXONOMY_TERMS = {
    "aves",
    "passeriformes",
    "oscine",
    "paridae",
    "corvidae",
    "fringillidae",
    "turdidae",
    "accipitridae",
    "anatidae",
    "picidae",
    "strigidae",
    "columbidae",
    "hirundinidae",
    "emberizidae",
    "ictenidae",
}


def _bird_relevance_score(data: dict) -> int:
    description = _normalize_lookup_text(data.get("description") or "")
    extract = _normalize_lookup_text(data.get("extract") or "")
    combined = f"{description} {extract}".strip()
    if not combined:
        return 0

    score = 0

    description_hits = sum(1 for phrase in BIRD_DESCRIPTION_PHRASES if phrase in description)
    if description_hits:
        score += 6 + min(2, description_hits - 1)

    bird_term_hits = sum(1 for term in BIRD_TERMS if _contains_lookup_term(combined, term))
    score += min(4, bird_term_hits)

    taxonomy_hits = sum(1 for term in BIRD_TAXONOMY_TERMS if _contains_lookup_term(combined, term))
    if taxonomy_hits:
        score += 2 + min(2, taxonomy_hits - 1)

    # Russian pages often use "вид рода ..." plus bird clues in extract.
    if "вид рода" in description and any(term in combined for term in ("птиц", "птица", "воробьинообраз", "paridae", "aves")):
        score += 2

    return score


def _name_match_score(article_title: str | None, requested_name: str) -> int:
    title_norm = _normalize_lookup_text(article_title)
    requested_norm = _normalize_lookup_text(requested_name)
    if not title_norm or not requested_norm:
        return 0

    if title_norm == requested_norm:
        return 12

    score = 0
    if requested_norm in title_norm or title_norm in requested_norm:
        score = max(score, 8)

    requested_tokens = _tokenize_lookup_text(requested_name)
    title_tokens = _tokenize_lookup_text(article_title)
    if requested_tokens and title_tokens:
        overlap_ratio = len(requested_tokens & title_tokens) / max(1, len(requested_tokens))
        if overlap_ratio >= 0.75:
            score = max(score, 7)
        elif overlap_ratio >= 0.5:
            score = max(score, 5)
        elif overlap_ratio >= 0.25:
            score = max(score, 3)

    return score


def _scientific_name_match_score(data: dict, expected_scientific_name: str | None) -> int:
    if not expected_scientific_name:
        return 0

    scientific_norm = _normalize_lookup_text(expected_scientific_name)
    if not scientific_norm:
        return 0

    combined = _normalize_lookup_text(
        " ".join(
            [
                data.get("title") or "",
                data.get("description") or "",
                data.get("extract") or "",
            ]
        )
    )
    if not combined:
        return 0

    if scientific_norm in combined:
        return 10

    parts = scientific_norm.split()
    if len(parts) >= 2 and parts[0] in combined and parts[1] in combined:
        return 7
    if parts and parts[0] in combined:
        return 3
    return 0


def _score_wikipedia_candidate(
    data: dict,
    requested_name: str,
    expected_scientific_name: str | None = None,
) -> int:
    bird_score = _bird_relevance_score(data)
    if bird_score <= 0:
        return 0

    name_score = _name_match_score(data.get("title"), requested_name)
    scientific_score = _scientific_name_match_score(data, expected_scientific_name)
    if name_score <= 0 and scientific_score <= 0:
        return 0

    # Keep name/scientific agreement dominant while still preferring stronger bird evidence.
    return (name_score * 100) + (scientific_score * 100) + bird_score


def _inaturalist_name_match_score(taxon: dict, requested_name: str) -> int:
    requested_norm = _normalize_lookup_text(requested_name)
    if not requested_norm:
        return 0

    best_score = 0
    requested_tokens = _tokenize_lookup_text(requested_name)

    weighted_fields = [
        (taxon.get("matched_term"), 16),
        (taxon.get("preferred_common_name"), 14),
        (taxon.get("name"), 13),
        (taxon.get("english_common_name"), 10),
    ]

    for raw_value, exact_weight in weighted_fields:
        normalized = _normalize_lookup_text(raw_value)
        if not normalized:
            continue

        field_score = 0
        if normalized == requested_norm:
            field_score = max(field_score, exact_weight)
        elif requested_norm in normalized or normalized in requested_norm:
            field_score = max(field_score, 8)

        field_tokens = _tokenize_lookup_text(raw_value)
        if requested_tokens and field_tokens:
            overlap = len(requested_tokens & field_tokens) / max(1, len(requested_tokens))
            if overlap >= 0.75:
                field_score = max(field_score, 7)
            elif overlap >= 0.5:
                field_score = max(field_score, 5)
            elif overlap >= 0.25:
                field_score = max(field_score, 3)

        best_score = max(best_score, field_score)

    return best_score


def _score_inaturalist_candidate(
    taxon: dict,
    requested_name: str,
    expected_scientific_name: str | None = None,
) -> int:
    iconic_taxon = _normalize_lookup_text(taxon.get("iconic_taxon_name"))
    scientific_name = _normalize_lookup_text(taxon.get("name"))
    expected_scientific = _normalize_lookup_text(expected_scientific_name)

    scientific_score = 0
    if expected_scientific:
        if scientific_name == expected_scientific:
            scientific_score = 16
        elif scientific_name and expected_scientific in scientific_name:
            scientific_score = 8

    if iconic_taxon != "aves" and scientific_score <= 0:
        return 0

    name_score = _inaturalist_name_match_score(taxon, requested_name)
    if name_score <= 0 and scientific_score <= 0:
        return 0

    rank_score = {
        "species": 5,
        "subspecies": 4,
        "complex": 3,
        "hybrid": 2,
        "variety": 1,
        "form": 1,
    }.get(_normalize_lookup_text(taxon.get("rank")), 0)

    active_score = 1 if taxon.get("is_active", True) else 0
    iconic_score = 2 if iconic_taxon == "aves" else 0

    return ((name_score + scientific_score) * 100) + (rank_score * 10) + (active_score * 2) + iconic_score


def _select_inaturalist_candidate(
    candidates: list[dict],
    requested_name: str,
    expected_scientific_name: str | None = None,
) -> tuple[dict | None, int]:
    best_taxon = None
    best_score = 0
    for taxon in candidates:
        score = _score_inaturalist_candidate(
            taxon,
            requested_name=requested_name,
            expected_scientific_name=expected_scientific_name,
        )
        if score > best_score:
            best_score = score
            best_taxon = taxon
    return best_taxon, best_score


def _dedupe_inaturalist_candidates(candidates: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen_ids: set[int] = set()
    seen_fallback: set[str] = set()

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        taxon_id = candidate.get("id")
        if isinstance(taxon_id, int):
            if taxon_id in seen_ids:
                continue
            seen_ids.add(taxon_id)
            deduped.append(candidate)
            continue

        fallback_key = _normalize_lookup_text(
            f"{candidate.get('name') or ''}|{candidate.get('preferred_common_name') or ''}"
        )
        if fallback_key and fallback_key not in seen_fallback:
            seen_fallback.add(fallback_key)
            deduped.append(candidate)

    return deduped


@router.get("/species")
async def get_species_list(request: Request):
    """Get list of all species with counts."""
    lang = get_user_language(request)
    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.ensure_recent_rollups(90)
        stats = await repo.get_species_leaderboard_base()
        unified_metrics = await repo.get_unified_species_window_metrics()

        # Transform unknown bird labels for display and aggregate counts
        unknown_labels = settings.classification.unknown_bird_labels
        filtered_stats = []

        for s in stats:
            if s["species"] in unknown_labels or should_hide_species_label(s["species"]):
                continue
            metrics_key = _species_unified_metrics_key(s)
            metrics = unified_metrics.get(metrics_key or "", {})
            trend_delta = metrics.get("count_7d", 0) - metrics.get("count_prev_7d", 0)
            trend_pct = 0.0
            prev = metrics.get("count_prev_7d", 0)
            if prev > 0:
                trend_pct = (trend_delta / prev) * 100.0

            common_name = s.get("common_name")
            taxa_id = s.get("taxa_id")
            if lang != 'en' and taxa_id:
                localized = await taxonomy_service.get_localized_common_name(taxa_id, lang, db=db)
                if localized:
                    common_name = localized

            filtered_stats.append({
                "species": s["species"],
                "count": s["count"],
                "scientific_name": s.get("scientific_name"),
                "common_name": common_name,
                "taxa_id": taxa_id,
                "first_seen": s.get("first_seen"),
                "last_seen": s.get("last_seen"),
                "avg_confidence": s.get("avg_confidence"),
                "max_confidence": s.get("max_confidence"),
                "min_confidence": s.get("min_confidence"),
                "camera_count": s.get("camera_count"),
                "count_1d": metrics.get("count_1d", 0),
                "count_7d": metrics.get("count_7d", 0),
                "count_30d": metrics.get("count_30d", 0),
                "days_seen_14d": metrics.get("days_seen_14d", 0),
                "days_seen_30d": metrics.get("days_seen_30d", 0),
                "trend_delta": trend_delta,
                "trend_percent": trend_pct,
            })

        # Add aggregated "Unknown Bird" entry if any were found
        unknown_stats = await repo.get_species_aggregate_for_name("Unknown Bird")
        if unknown_stats:
            unknown_rollup = await repo.get_window_metrics_for_species_name("Unknown Bird")
            trend_delta = unknown_rollup.get("count_7d", 0) - unknown_rollup.get("count_prev_7d", 0)
            trend_pct = 0.0
            prev = unknown_rollup.get("count_prev_7d", 0)
            if prev > 0:
                trend_pct = (trend_delta / prev) * 100.0
            filtered_stats.append({
                "species": "Unknown Bird", 
                "count": unknown_stats["count"],
                "scientific_name": None,
                "common_name": None,
                "first_seen": unknown_stats.get("first_seen"),
                "last_seen": unknown_stats.get("last_seen"),
                "avg_confidence": unknown_stats.get("avg_confidence"),
                "max_confidence": unknown_stats.get("max_confidence"),
                "min_confidence": unknown_stats.get("min_confidence"),
                "camera_count": unknown_stats.get("camera_count"),
                "count_1d": unknown_rollup.get("count_1d", 0),
                "count_7d": unknown_rollup.get("count_7d", 0),
                "count_30d": unknown_rollup.get("count_30d", 0),
                "days_seen_14d": unknown_rollup.get("days_seen_14d", 0),
                "days_seen_30d": unknown_rollup.get("days_seen_30d", 0),
                "trend_delta": trend_delta,
                "trend_percent": trend_pct,
            })
            # Re-sort by count descending
            filtered_stats.sort(key=lambda x: x["count"], reverse=True)

        return filtered_stats


@router.get("/leaderboard/species")
@guest_rate_limit()
async def get_leaderboard_species(
    request: Request,
    span: Literal["day", "week", "month"] = Query("week", description="Rolling window for leaderboard stats"),
):
    """Leaderboard species stats for a rolling window aligned to the current time.

    Span definitions:
    - day: last 24 hours
    - week: last 7 days
    - month: last 30 days
    """
    lang = get_user_language(request)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if span == "day":
        window = timedelta(hours=24)
    elif span == "week":
        window = timedelta(days=7)
    else:
        window = timedelta(days=30)

    window_start = now - window
    window_end = now
    prev_start = window_start - window
    prev_end = window_start

    unknown_labels = settings.classification.unknown_bird_labels

    async with get_db() as db:
        repo = DetectionRepository(db)
        rows = await repo.get_species_leaderboard_window(
            window_start=window_start,
            window_end=window_end,
            prev_start=prev_start,
            prev_end=prev_end,
        )

        # Filter to species present in the selected window only.
        filtered = []
        for r in rows:
            if r["species"] in unknown_labels or should_hide_species_label(r["species"]):
                continue
            if r["window_count"] <= 0:
                continue

            common_name = r.get("common_name")
            taxa_id = r.get("taxa_id")
            if lang != "en" and taxa_id:
                localized = await taxonomy_service.get_localized_common_name(taxa_id, lang, db=db)
                if localized:
                    common_name = localized

            delta = r["window_count"] - r["prev_count"]
            pct = 0.0
            if r["prev_count"] > 0:
                pct = (delta / r["prev_count"]) * 100.0

            filtered.append({
                "species": r["species"],
                "scientific_name": r.get("scientific_name"),
                "common_name": common_name,
                "taxa_id": taxa_id,
                "window_count": r["window_count"],
                "window_prev_count": r["prev_count"],
                "window_delta": delta,
                "window_percent": pct,
                "window_first_seen": r["window_first_seen"].isoformat() if r.get("window_first_seen") else None,
                "window_last_seen": r["window_last_seen"].isoformat() if r.get("window_last_seen") else None,
                "window_avg_confidence": r.get("window_avg_confidence", 0.0),
                "window_camera_count": r.get("window_camera_count", 0),
            })

        unknown = await repo.get_species_leaderboard_window_for_name(
            species_name="Unknown Bird",
            window_start=window_start,
            window_end=window_end,
            prev_start=prev_start,
            prev_end=prev_end,
        )
        if unknown and unknown.get("window_count", 0) > 0:
            delta = unknown["window_count"] - unknown["prev_count"]
            pct = 0.0
            if unknown["prev_count"] > 0:
                pct = (delta / unknown["prev_count"]) * 100.0
            filtered.append({
                "species": "Unknown Bird",
                "scientific_name": None,
                "common_name": None,
                "taxa_id": None,
                "window_count": unknown["window_count"],
                "window_prev_count": unknown["prev_count"],
                "window_delta": delta,
                "window_percent": pct,
                "window_first_seen": unknown["window_first_seen"].isoformat() if unknown.get("window_first_seen") else None,
                "window_last_seen": unknown["window_last_seen"].isoformat() if unknown.get("window_last_seen") else None,
                "window_avg_confidence": unknown.get("window_avg_confidence", 0.0),
                "window_camera_count": unknown.get("window_camera_count", 0),
            })

        # Sort by selected window count desc.
        filtered.sort(key=lambda x: int(x.get("window_count") or 0), reverse=True)

        return {
            "span": span,
            "window_start": window_start.replace(tzinfo=timezone.utc).isoformat(),
            "window_end": window_end.replace(tzinfo=timezone.utc).isoformat(),
            "species": filtered,
        }

@router.get("/species/{species_name}/stats", response_model=SpeciesStats)
@guest_rate_limit()
async def get_species_stats(
    species_name: str,
    request: Request,
    auth: AuthContext = Depends(get_auth_context_with_legacy)
):
    """Get comprehensive statistics for a species."""
    lang = get_user_language(request)
    hide_camera_names = (
        not auth.is_owner
        and settings.public_access.enabled
        and not settings.public_access.show_camera_names
    )
    async with get_db() as db:
        repo = DetectionRepository(db)

        # For "Unknown Bird" queries, we need to aggregate stats from all unknown labels
        unknown_labels = settings.classification.unknown_bird_labels
        is_unknown_query = species_name == "Unknown Bird"
        alias_info = None

        if is_unknown_query:
            query_labels = ["Unknown Bird"]
        else:
            alias_info = await repo.resolve_species_aliases(species_name, language=lang)
            # Repository species-detail helpers now normalize aliases canonically,
            # so non-unknown species should be queried once to avoid double counting.
            query_labels = [species_name]

        # Get all stats - aggregate if multiple labels
        total_stats = {"total": 0, "first_seen": None, "last_seen": None,
                       "avg_confidence": 0.0, "max_confidence": 0.0, "min_confidence": 1.0}
        all_camera_stats = []
        hourly = [0] * 24
        daily = [0] * 7
        monthly = [0] * 12
        recent = []
        confidence_sum = 0.0
        confidence_count = 0

        for label in query_labels:
            basic_stats = await repo.get_species_basic_stats(label)
            if basic_stats["total"] > 0:
                total_stats["total"] += basic_stats["total"]
                if basic_stats["first_seen"]:
                    candidate_first_seen = _to_utc_naive(basic_stats["first_seen"])
                    current_first_seen = _to_utc_naive(total_stats["first_seen"])
                    if current_first_seen is None or (
                        candidate_first_seen is not None and candidate_first_seen < current_first_seen
                    ):
                        total_stats["first_seen"] = candidate_first_seen
                if basic_stats["last_seen"]:
                    candidate_last_seen = _to_utc_naive(basic_stats["last_seen"])
                    current_last_seen = _to_utc_naive(total_stats["last_seen"])
                    if current_last_seen is None or (
                        candidate_last_seen is not None and candidate_last_seen > current_last_seen
                    ):
                        total_stats["last_seen"] = candidate_last_seen
                total_stats["max_confidence"] = max(total_stats["max_confidence"], basic_stats["max_confidence"])
                total_stats["min_confidence"] = min(total_stats["min_confidence"], basic_stats["min_confidence"])
                confidence_sum += basic_stats["avg_confidence"] * basic_stats["total"]
                confidence_count += basic_stats["total"]

                # Aggregate distributions
                label_hourly = await repo.get_hourly_distribution(label)
                label_daily = await repo.get_daily_distribution(label)
                label_monthly = await repo.get_monthly_distribution(label)
                hourly = [h + lh for h, lh in zip(hourly, label_hourly)]
                daily = [d + ld for d, ld in zip(daily, label_daily)]
                monthly = [m + lm for m, lm in zip(monthly, label_monthly)]

                # Get camera breakdown
                label_cameras = await repo.get_camera_breakdown(label)
                all_camera_stats.extend(label_cameras)

                # Get recent sightings
                label_recent = await repo.get_recent_by_species(label, limit=5)
                recent.extend(label_recent)

        if total_stats["total"] == 0:
            raise HTTPException(
                status_code=404, 
                detail=i18n_service.translate("errors.detection_not_found", lang=lang)
            )

        # Calculate average confidence
        if confidence_count > 0:
            total_stats["avg_confidence"] = confidence_sum / confidence_count

        # Aggregate camera stats
        camera_counts = {}
        for cs in all_camera_stats:
            cam = cs["camera_name"]
            camera_counts[cam] = camera_counts.get(cam, 0) + cs["count"]
        total_cam_count = sum(camera_counts.values())
        if hide_camera_names:
            camera_breakdown = (
                [{"camera_name": "Hidden", "count": total_cam_count, "percentage": 100.0}]
                if total_cam_count > 0
                else []
            )
        else:
            camera_breakdown = [
                {"camera_name": cam, "count": count, "percentage": (count / total_cam_count * 100) if total_cam_count > 0 else 0.0}
                for cam, count in sorted(camera_counts.items(), key=lambda x: x[1], reverse=True)
            ]

        # Sort recent by time and limit to 5
        recent.sort(
            key=lambda x: _to_utc_naive(x.detection_time) or datetime.min,
            reverse=True,
        )
        recent = recent[:5]

        # Convert dataclass detections to Pydantic models
        # Also transform display_name for unknown bird labels
        recent_detections = []
        for d in recent:
            common_name = d.common_name
            if lang != 'en' and d.taxa_id:
                localized = await taxonomy_service.get_localized_common_name(d.taxa_id, lang, db=db)
                if localized:
                    common_name = localized

            public_species = user_facing_species_fields(
                display_name=d.display_name,
                category_name=d.category_name,
                scientific_name=d.scientific_name,
                common_name=common_name,
                taxa_id=d.taxa_id,
                extra_unknown_labels=unknown_labels,
            )

            recent_detections.append(Detection(
                id=d.id,
                detection_time=d.detection_time,
                detection_index=d.detection_index,
                score=d.score,
                display_name=str(public_species["display_name"]),
                category_name=public_species["category_name"],
                frigate_event=d.frigate_event,
                camera_name="Hidden" if hide_camera_names else d.camera_name,
                is_hidden=d.is_hidden,
                is_favorite=d.is_favorite,
                frigate_score=d.frigate_score,
                sub_label=d.sub_label,
                audio_confirmed=d.audio_confirmed,
                audio_species=d.audio_species,
                audio_score=d.audio_score,
                temperature=d.temperature,
                weather_condition=d.weather_condition,
                weather_cloud_cover=d.weather_cloud_cover,
                weather_wind_speed=d.weather_wind_speed,
                weather_wind_direction=d.weather_wind_direction,
                weather_precipitation=d.weather_precipitation,
                weather_rain=d.weather_rain,
                weather_snowfall=d.weather_snowfall,
                scientific_name=public_species["scientific_name"],
                common_name=public_species["common_name"],
                taxa_id=public_species["taxa_id"]
            ))

        # Get taxonomy names for the main species
        if alias_info:
            taxonomy = {
                "scientific_name": alias_info.get("scientific_name"),
                "common_name": alias_info.get("common_name"),
                "taxa_id": alias_info.get("taxa_id"),
            }
            if taxonomy["scientific_name"] is None and taxonomy["taxa_id"] is None:
                taxonomy = await repo.get_taxonomy_names(species_name, language=lang)
        else:
            taxonomy = await repo.get_taxonomy_names(species_name, language=lang)
        common_name = taxonomy["common_name"]
        taxa_id = taxonomy.get("taxa_id")
        if not taxa_id and recent:
            taxa_id = recent[0].taxa_id
        
        # Localize main common name if needed
        if lang != 'en' and taxa_id:
            localized = await taxonomy_service.get_localized_common_name(taxa_id, lang, db=db)
            if localized:
                common_name = localized

        return SpeciesStats(
            species_name=species_name,
            scientific_name=taxonomy["scientific_name"],
            common_name=common_name,
            taxa_id=taxa_id,
            total_sightings=total_stats["total"],
            first_seen=total_stats["first_seen"],
            last_seen=total_stats["last_seen"],
            cameras=[CameraStats(**c) for c in camera_breakdown],
            hourly_distribution=hourly,
            daily_distribution=daily,
            monthly_distribution=monthly,
            avg_confidence=total_stats["avg_confidence"],
            max_confidence=total_stats["max_confidence"],
            min_confidence=total_stats["min_confidence"],
            recent_sightings=recent_detections
        )

@router.delete("/species/{species_name}/cache")
async def clear_species_cache(
    species_name: str,
    auth: AuthContext = Depends(require_owner)
):
    """Clear the Wikipedia cache for a species."""
    cache_prefix = f"{species_name}:"
    for cache_key in list(_wiki_cache):
        if cache_key == species_name or cache_key.startswith(cache_prefix):
            del _wiki_cache[cache_key]
    taxa_id = await _lookup_taxa_id(species_name)
    async with get_db() as db:
        if taxa_id:
            await db.execute(
                "DELETE FROM species_info_cache WHERE species_name = ? OR taxa_id = ?",
                (species_name, taxa_id)
            )
        else:
            await db.execute(
                "DELETE FROM species_info_cache WHERE species_name = ?",
                (species_name,)
            )
        await db.commit()
    log.info("Cleared species cache", species=species_name)
    return {"status": "cleared", "species": species_name}


@router.get("/species/{species_name}/info", response_model=SpeciesInfo)
@guest_rate_limit()
async def get_species_info(
    species_name: str,
    request: Request,
    refresh: bool = False,
    auth: AuthContext = Depends(get_auth_context_with_legacy)
):
    """Get species information for a species. Use refresh=true to bypass cache."""
    lang = get_user_language(request) or "en"
    log.info("Fetching species info", species=species_name, refresh=refresh, language=lang)

    # Skip Wikipedia lookup for non-identifiable species (e.g., "Unknown Bird")
    if species_name in SKIP_WIKIPEDIA_LOOKUP:
        log.info("Skipping Wikipedia lookup for non-identifiable species", species=species_name)
        return SpeciesInfo(
            title=species_name,
            description="Unidentified bird species",
            extract="This detection could not be classified to a specific species. The bird may be at an unusual angle, partially visible, or not in the model's training data.",
            thumbnail_url=None,
            wikipedia_url=None,
            source=None,
            source_url=None,
            scientific_name=None,
            conservation_status=None,
            cached_at=datetime.now()
        )

    taxa_id = await _lookup_taxa_id(species_name, language=lang)
    cached_info = await _get_cached_species_info(species_name, taxa_id, lang, refresh)
    if cached_info:
        return cached_info

    summary_sources = _resolve_summary_sources()
    primary = summary_sources[0]

    if primary == "wikipedia":
        info = await _fetch_wikipedia_info(species_name, lang)
        if info.extract:
            info.summary_source = info.source
            info.summary_source_url = info.source_url
        if not info.extract or not info.thumbnail_url:
            inat_info = await _fetch_inaturalist_info(
                species_name,
                lang,
                expected_scientific_name=info.scientific_name,
            )
            if not info.extract and inat_info.extract:
                info.extract = inat_info.extract
                info.summary_source = inat_info.source
                info.summary_source_url = inat_info.source_url
            if not info.thumbnail_url and inat_info.thumbnail_url:
                info.thumbnail_url = inat_info.thumbnail_url
            if not info.wikipedia_url and inat_info.wikipedia_url:
                info.wikipedia_url = inat_info.wikipedia_url
            if not info.scientific_name and inat_info.scientific_name:
                info.scientific_name = inat_info.scientific_name
    elif primary == "ebird":
        info = await _fetch_ebird_info(species_name, lang)
        
        # eBird rarely provides text/images via API, so we almost always need fallbacks
        # Use the eBird-resolved common name for better fallback lookup success
        search_name = info.title if info.title and info.title != species_name else species_name
        
        # Fallback to Wikipedia for text/images
        if not info.extract or not info.thumbnail_url:
            wiki_info = await _fetch_wikipedia_info(
                search_name,
                lang,
                expected_scientific_name=info.scientific_name,
            )
            # If search by eBird name failed, try original name
            if not wiki_info.extract and search_name != species_name:
                wiki_info = await _fetch_wikipedia_info(
                    species_name,
                    lang,
                    expected_scientific_name=info.scientific_name,
                )

            if wiki_info.extract:
                info.extract = wiki_info.extract
                info.summary_source = wiki_info.source
                info.summary_source_url = wiki_info.source_url
            if wiki_info.thumbnail_url:
                info.thumbnail_url = wiki_info.thumbnail_url
            if wiki_info.wikipedia_url:
                info.wikipedia_url = wiki_info.wikipedia_url
            if not info.scientific_name and wiki_info.scientific_name:
                info.scientific_name = wiki_info.scientific_name

        # Fallback to iNaturalist if still missing
        if not info.extract or not info.thumbnail_url:
            inat_info = await _fetch_inaturalist_info(
                search_name,
                lang,
                expected_scientific_name=info.scientific_name,
            )
            if inat_info.extract:
                info.extract = inat_info.extract
                info.summary_source = inat_info.source
                info.summary_source_url = inat_info.source_url
            if inat_info.thumbnail_url:
                info.thumbnail_url = inat_info.thumbnail_url
            if inat_info.wikipedia_url and not info.wikipedia_url:
                info.wikipedia_url = inat_info.wikipedia_url
            if inat_info.scientific_name and not info.scientific_name:
                info.scientific_name = inat_info.scientific_name
    else:
        info = await _fetch_inaturalist_info(
            species_name,
            lang,
            expected_scientific_name=None,
        )
        if not info.extract or not info.thumbnail_url:
            wiki_info = None
            if info.wikipedia_url:
                wiki_info = await _fetch_wikipedia_info_from_url(info.wikipedia_url, species_name, lang)
            if not wiki_info:
                wiki_info = await _fetch_wikipedia_info(
                    species_name,
                    lang,
                    expected_scientific_name=info.scientific_name,
                )
            if not info.extract and wiki_info.extract:
                info.extract = wiki_info.extract
                info.summary_source = wiki_info.source
                info.summary_source_url = wiki_info.source_url
            if not info.thumbnail_url and wiki_info.thumbnail_url:
                info.thumbnail_url = wiki_info.thumbnail_url
            if not info.wikipedia_url and wiki_info.wikipedia_url:
                info.wikipedia_url = wiki_info.wikipedia_url
            if not info.scientific_name and wiki_info.scientific_name:
                info.scientific_name = wiki_info.scientific_name

        if lang != "en" and not info.extract:
            fallback = await _fetch_wikipedia_info(
                species_name,
                "en",
                expected_scientific_name=info.scientific_name,
            )
            if fallback.extract:
                info.extract = fallback.extract
                info.summary_source = fallback.source
                info.summary_source_url = fallback.source_url

    if info.extract and not info.summary_source:
        info.summary_source = info.source
        info.summary_source_url = info.source_url

    if taxa_id and not info.taxa_id:
        info.taxa_id = taxa_id

    # Cache the result
    await _save_species_info(species_name, taxa_id, lang, info)
    _wiki_cache[f"{species_name}:{lang}"] = (info, info.cached_at or datetime.now())

    is_success = bool(info.thumbnail_url or info.extract)
    log.info(
        "Species info fetch complete",
        species=species_name,
        success=is_success,
        source=info.source,
        has_thumbnail=bool(info.thumbnail_url),
        has_extract=bool(info.extract)
    )

    return info


@router.get("/species/{species_name}/range", response_model=SpeciesRangeMap)
@guest_rate_limit()
async def get_species_range(
    species_name: str,
    request: Request,
    scientific_name: str | None = None,
    auth: AuthContext = Depends(get_auth_context_with_legacy)
):
    query_name = scientific_name or species_name
    if not query_name:
        return SpeciesRangeMap(status="error", message="No species name provided")

    taxon_key = await _get_gbif_taxon_key(query_name)
    if not taxon_key:
        return SpeciesRangeMap(status="error", message="GBIF match not found")

    tile_url = (
        f"{GBIF_TILE_URL}?srs=EPSG:3857&taxonKey={taxon_key}"
        "&bin=hex&hexPerTile=57&style=classic.poly"
    )
    return SpeciesRangeMap(
        status="ok",
        taxon_key=taxon_key,
        map_tile_url=tile_url,
        source="GBIF",
        source_url=f"https://www.gbif.org/species/{taxon_key}"
    )

async def _fetch_ebird_info(species_name: str, lang: str) -> SpeciesInfo:
    """Fetch species information from eBird API."""
    try:
        # Resolve name to code
        code = await ebird_service.resolve_species_code(species_name, locale=lang)
        if code:
             # Find item in taxonomy (pass locale to get localized common name)
             # eBird locales use hyphens (e.g. pt-BR) but app might use underscores or just code
             # We pass it as is, eBird service handles defaults
             taxonomy = await ebird_service.get_taxonomy(locale=lang)
             item = next((i for i in taxonomy if i.get("speciesCode") == code), None)
             
             if item:
                 return SpeciesInfo(
                     title=item.get("comName") or species_name,
                     description=None, # eBird doesn't provide descriptions
                     extract=None,
                     thumbnail_url=None,
                     wikipedia_url=None,
                     source="eBird",
                     source_url=f"https://ebird.org/species/{code}",
                     summary_source=None,
                     summary_source_url=None,
                     scientific_name=item.get("sciName"),
                     conservation_status=None,
                     cached_at=datetime.now()
                 )
    except Exception as e:
        log.error("eBird info fetch failed", species=species_name, error=str(e))
    
    # Return minimal info if eBird lookup failed
    return SpeciesInfo(
        title=species_name,
        description=None,
        extract=None,
        thumbnail_url=None,
        wikipedia_url=None,
        source="eBird (Failed)",
        source_url=None,
        scientific_name=None,
        conservation_status=None,
        cached_at=datetime.now()
    )


async def _fetch_wikipedia_info(
    species_name: str,
    lang: str,
    expected_scientific_name: str | None = None,
) -> SpeciesInfo:
    """Fetch species information from Wikipedia API."""

    headers = {
        "User-Agent": WIKIPEDIA_USER_AGENT,
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers=headers
        ) as client:
            # Try multiple strategies to find the Wikipedia article
            article_title = await _find_wikipedia_article(
                client,
                species_name,
                lang,
                expected_scientific_name=expected_scientific_name,
            )

            if article_title:
                log.info("Found Wikipedia article", species=species_name, article=article_title)
                return await _get_wikipedia_summary(client, article_title, species_name, lang)
            else:
                log.warning("No Wikipedia article found after all strategies", species=species_name)

    except httpx.TimeoutException:
        log.error("Wikipedia API timeout", species=species_name)
    except httpx.RequestError as e:
        log.error("Wikipedia API request error", species=species_name, error=str(e))
    except Exception as e:
        log.error("Unexpected error fetching Wikipedia info", species=species_name, error=str(e), error_type=type(e).__name__)

    # Return minimal info if Wikipedia lookup failed
    return SpeciesInfo(
        title=species_name,
        description=None,
        extract=None,
        thumbnail_url=None,
        wikipedia_url=None,
        source=None,
        source_url=None,
        scientific_name=None,
        conservation_status=None,
        cached_at=datetime.now()
    )


async def _fetch_wikipedia_info_from_url(wikipedia_url: str, species_name: str, lang: str) -> SpeciesInfo | None:
    """Fetch Wikipedia summary directly from a known article URL."""
    from urllib.parse import urlparse, unquote

    parsed = urlparse(wikipedia_url)
    path = parsed.path or ""
    if "/wiki/" not in path:
        return None

    host = parsed.hostname or ""
    url_lang = lang
    if host.endswith(".wikipedia.org"):
        subdomain = host.split(".")[0]
        if subdomain:
            url_lang = subdomain

    title = unquote(path.split("/wiki/")[-1].replace("_", " ")).strip()
    if not title:
        return None

    headers = {
        "User-Agent": WIKIPEDIA_USER_AGENT,
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers=headers
        ) as client:
            return await _get_wikipedia_summary(client, title, species_name, url_lang)
    except httpx.TimeoutException:
        log.error("Wikipedia API timeout (direct)", species=species_name)
    except httpx.RequestError as e:
        log.error("Wikipedia API request error (direct)", species=species_name, error=str(e))
    except Exception as e:
        log.error("Unexpected error fetching Wikipedia info (direct)", species=species_name, error=str(e), error_type=type(e).__name__)

    return None


async def _inaturalist_query_candidates(
    client: httpx.AsyncClient,
    species_name: str,
    locale: str,
) -> list[dict]:
    params = {
        "q": species_name,
        "per_page": 30,
        "locale": locale,
        "is_active": "true",
        "iconic_taxa": "Aves",
        "all_names": "true",
    }
    endpoints = [
        "https://api.inaturalist.org/v1/taxa/autocomplete",
        "https://api.inaturalist.org/v1/taxa",
    ]

    merged: list[dict] = []
    for url in endpoints:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
            results = payload.get("results", []) if isinstance(payload, dict) else []
            if isinstance(results, list):
                merged.extend([r for r in results if isinstance(r, dict)])
        except Exception as e:
            log.warning("iNaturalist candidate query failed", species=species_name, locale=locale, url=url, error=str(e))

    return _dedupe_inaturalist_candidates(merged)


async def _inaturalist_fetch_taxon_details(
    client: httpx.AsyncClient,
    taxa_id: int,
    locale: str,
) -> dict | None:
    try:
        response = await client.get(
            f"https://api.inaturalist.org/v1/taxa/{taxa_id}",
            params={"locale": locale}
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            return None
        results = payload.get("results", [])
        if isinstance(results, list) and results and isinstance(results[0], dict):
            return results[0]
    except Exception as e:
        log.warning("iNaturalist taxon detail fetch failed", taxa_id=taxa_id, locale=locale, error=str(e))
    return None


async def _fetch_inaturalist_info(
    species_name: str,
    lang: str,
    expected_scientific_name: str | None = None,
) -> SpeciesInfo:
    """Fetch species information from iNaturalist API with scored candidate matching."""
    requested_locale = (lang or "en").strip().replace("_", "-")
    if not requested_locale:
        requested_locale = "en"
    locales_to_try = [requested_locale]
    if requested_locale.lower() != "en":
        locales_to_try.append("en")

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            candidates: list[dict] = []
            for locale in locales_to_try:
                candidates.extend(await _inaturalist_query_candidates(client, species_name, locale))

            candidates = _dedupe_inaturalist_candidates(candidates)
            taxon, score = _select_inaturalist_candidate(
                candidates,
                requested_name=species_name,
                expected_scientific_name=expected_scientific_name,
            )
            if not taxon:
                return SpeciesInfo(
                    title=species_name,
                    description=None,
                    extract=None,
                    thumbnail_url=None,
                    wikipedia_url=None,
                    source=None,
                    source_url=None,
                    scientific_name=None,
                    conservation_status=None,
                    cached_at=datetime.now()
                )

            # Enrich with full taxon details when autocomplete payload is sparse.
            taxa_id = taxon.get("id")
            if isinstance(taxa_id, int):
                if not taxon.get("wikipedia_summary") or not taxon.get("default_photo"):
                    details = await _inaturalist_fetch_taxon_details(client, taxa_id, requested_locale)
                    if details:
                        merged = details.copy()
                        merged.update({k: v for k, v in taxon.items() if v is not None})
                        taxon = merged

            scientific_name = taxon.get("name")
            preferred_common = taxon.get("preferred_common_name")
            title = preferred_common or scientific_name or species_name
            extract = taxon.get("wikipedia_summary")
            wikipedia_url = taxon.get("wikipedia_url")
            source_url = taxon.get("uri") or (
                f"https://www.inaturalist.org/taxa/{taxa_id}" if isinstance(taxa_id, int) else None
            )
            thumbnail_url = None
            default_photo = taxon.get("default_photo")
            if isinstance(default_photo, dict):
                thumbnail_url = default_photo.get("medium_url") or default_photo.get("square_url") or default_photo.get("url")

            log.info(
                "Selected iNaturalist taxon",
                species=species_name,
                taxon_id=taxa_id,
                scientific_name=scientific_name,
                common_name=preferred_common,
                score=score,
            )

            return SpeciesInfo(
                title=title,
                description=None,
                extract=extract,
                thumbnail_url=thumbnail_url,
                wikipedia_url=wikipedia_url,
                source="iNaturalist",
                source_url=source_url,
                summary_source="iNaturalist" if extract else None,
                summary_source_url=source_url if extract else None,
                scientific_name=scientific_name,
                conservation_status=None,
                taxa_id=taxa_id if isinstance(taxa_id, int) else None,
                cached_at=datetime.now()
            )
    except httpx.TimeoutException:
        log.error("iNaturalist API timeout", species=species_name)
    except httpx.RequestError as e:
        log.error("iNaturalist API request error", species=species_name, error=str(e))
    except Exception as e:
        log.error("Unexpected error fetching iNaturalist info", species=species_name, error=str(e), error_type=type(e).__name__)

    return SpeciesInfo(
        title=species_name,
        description=None,
        extract=None,
        thumbnail_url=None,
        wikipedia_url=None,
        source=None,
        source_url=None,
        scientific_name=None,
        conservation_status=None,
        cached_at=datetime.now()
    )


async def _find_wikipedia_article(
    client: httpx.AsyncClient,
    species_name: str,
    lang: str,
    expected_scientific_name: str | None = None,
) -> str | None:
    """Try multiple strategies and select the best matching bird article."""
    base_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary"

    titles_to_try: list[str] = [species_name]

    words = species_name.split()
    if len(words) >= 2:
        sentence_case = words[0] + " " + " ".join(w.lower() for w in words[1:])
        if sentence_case != species_name:
            titles_to_try.append(sentence_case)

        regional_prefixes = [
            "Eurasian",
            "European",
            "American",
            "African",
            "Asian",
            "Common",
            "Northern",
            "Southern",
            "Eastern",
            "Western",
            "Greater",
            "Lesser",
            "Little",
            "Great",
        ]
        if words[0] in regional_prefixes:
            short_name = " ".join(words[1:])
            titles_to_try.append(short_name)
            if len(words) > 2:
                short_sentence = words[1] + " " + " ".join(w.lower() for w in words[2:])
                titles_to_try.append(short_sentence)

    base_titles = titles_to_try.copy()
    for title in base_titles:
        titles_to_try.append(f"{title} (bird)")
    if expected_scientific_name:
        titles_to_try.append(expected_scientific_name)

    # Preserve order while removing duplicate title attempts.
    deduped_titles: list[str] = []
    seen_title_keys: set[str] = set()
    for title in titles_to_try:
        key = _normalize_lookup_text(title)
        if key and key not in seen_title_keys:
            seen_title_keys.add(key)
            deduped_titles.append(title)

    log.debug(
        "Trying Wikipedia title variations",
        species=species_name,
        language=lang,
        variations=deduped_titles,
    )

    best_title: str | None = None
    best_score = 0
    checked_candidates: set[str] = set()

    async def evaluate_candidate(title: str, strategy: str) -> None:
        nonlocal best_title, best_score
        normalized_title = _normalize_lookup_text(title)
        if not normalized_title or normalized_title in checked_candidates:
            return
        checked_candidates.add(normalized_title)

        url = f"{base_url}/{quote(title.replace(' ', '_'))}"
        try:
            response = await client.get(url)
        except Exception as e:
            log.warning("Error checking Wikipedia title", title=title, strategy=strategy, error=str(e))
            return

        if response.status_code == 404:
            return
        if response.status_code != 200:
            log.warning(
                "Unexpected Wikipedia response",
                status=response.status_code,
                title=title,
                strategy=strategy,
            )
            return

        data = response.json()
        candidate_title = data.get("title") or title
        score = _score_wikipedia_candidate(
            data,
            requested_name=species_name,
            expected_scientific_name=expected_scientific_name,
        )
        if expected_scientific_name and _normalize_lookup_text(title) == _normalize_lookup_text(expected_scientific_name):
            # Explicit scientific-name lookup is a strong signal even on localized pages.
            score = max(score, 1000 + _bird_relevance_score(data))
        if score <= 0:
            log.debug(
                "Wikipedia candidate rejected",
                species=species_name,
                language=lang,
                title=candidate_title,
                strategy=strategy,
                bird_score=_bird_relevance_score(data),
            )
            return

        if score > best_score:
            best_score = score
            best_title = candidate_title
            log.debug(
                "Wikipedia candidate accepted",
                species=species_name,
                language=lang,
                title=candidate_title,
                strategy=strategy,
                score=score,
            )

    for title in deduped_titles:
        await evaluate_candidate(title, "direct")

    if best_title:
        log.info(
            "Selected Wikipedia article via direct lookup",
            species=species_name,
            article=best_title,
            score=best_score,
        )
        return best_title

    log.debug("Falling back to Wikipedia search API", species=species_name, language=lang)
    search_url = f"https://{lang}.wikipedia.org/w/api.php"
    localized_bird_term = {
        "ru": "птица",
        "de": "vogel",
        "fr": "oiseau",
        "es": "ave",
        "it": "uccello",
        "pt": "ave",
        "ja": "鳥",
        "zh": "鸟",
    }.get(lang, "bird")

    raw_queries = [
        f"{species_name} {localized_bird_term}",
        f'"{species_name}"',
        species_name,
    ]
    if expected_scientific_name:
        raw_queries.extend([expected_scientific_name, f'"{expected_scientific_name}"'])
    if localized_bird_term != "bird":
        raw_queries.append(f"{species_name} bird")

    search_queries: list[str] = []
    seen_queries: set[str] = set()
    for query in raw_queries:
        normalized = _normalize_lookup_text(query)
        if normalized and normalized not in seen_queries:
            seen_queries.add(normalized)
            search_queries.append(query)

    for search_query in search_queries:
        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": search_query,
            "format": "json",
            "srlimit": 10,
        }
        try:
            response = await client.get(search_url, params=search_params)
        except Exception as e:
            log.warning("Wikipedia search failed", error=str(e), species=species_name, query=search_query)
            continue

        if response.status_code != 200:
            log.warning(
                "Wikipedia search failed",
                species=species_name,
                query=search_query,
                status=response.status_code,
            )
            continue

        data = response.json()
        results = data.get("query", {}).get("search", [])
        log.debug(
            "Wikipedia search results",
            species=species_name,
            language=lang,
            query=search_query,
            count=len(results),
        )
        for result in results:
            title = result.get("title") or ""
            if title:
                await evaluate_candidate(title, f"search:{search_query}")

    if best_title:
        log.info(
            "Selected Wikipedia article via search",
            species=species_name,
            article=best_title,
            score=best_score,
        )
        return best_title

    log.warning("All Wikipedia search strategies exhausted", species=species_name, language=lang)
    return None


async def _get_wikipedia_summary(client: httpx.AsyncClient, article_title: str, original_name: str, lang: str) -> SpeciesInfo:
    """Fetch the summary for a Wikipedia article."""
    import re

    base_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary"
    encoded = quote(article_title.replace(" ", "_"))
    url = f"{base_url}/{encoded}"

    try:
        response = await client.get(url)
        if response.status_code == 200:
            data = response.json()

            description = data.get("description", "")
            extract = data.get("extract", "")

            # Get the best available image
            thumbnail_url = None
            if "originalimage" in data:
                thumbnail_url = data["originalimage"].get("source")
            elif "thumbnail" in data:
                thumb_url = data["thumbnail"].get("source", "")
                if "/thumb/" in thumb_url and "px-" in thumb_url:
                    thumbnail_url = re.sub(r'/\d+px-', '/800px-', thumb_url)
                else:
                    thumbnail_url = thumb_url

            wikipedia_url = data.get("content_urls", {}).get("desktop", {}).get("page")
            return SpeciesInfo(
                title=data.get("title", original_name),
                description=description if description else None,
                extract=extract if extract else None,
                thumbnail_url=thumbnail_url,
                wikipedia_url=wikipedia_url,
                source="Wikipedia",
                source_url=wikipedia_url,
                summary_source="Wikipedia" if extract else None,
                summary_source_url=wikipedia_url if extract else None,
                scientific_name=None,
                conservation_status=None,
                cached_at=datetime.now()
            )
    except Exception as e:
        log.error("Error fetching Wikipedia summary", error=str(e), article=article_title)

    return SpeciesInfo(
        title=original_name,
        description=None,
        extract=None,
        thumbnail_url=None,
        wikipedia_url=None,
        source=None,
        source_url=None,
        scientific_name=None,
        conservation_status=None,
        cached_at=datetime.now()
    )
