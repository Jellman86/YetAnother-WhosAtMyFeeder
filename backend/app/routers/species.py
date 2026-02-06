from fastapi import APIRouter, HTTPException, Request, Depends
from datetime import datetime, timedelta
from urllib.parse import quote
import httpx
import structlog

from app.database import get_db
from app.repositories.detection_repository import DetectionRepository
from app.models import SpeciesStats, SpeciesInfo, CameraStats, Detection, SpeciesRangeMap
from app.config import settings
from app.services.taxonomy.taxonomy_service import taxonomy_service
from app.services.i18n_service import i18n_service
from app.services.classifier_service import get_classifier
from app.services.ebird_service import ebird_service
from app.utils.language import get_user_language
from app.utils.enrichment import get_effective_enrichment_settings
from app.auth import require_owner, AuthContext
from app.auth_legacy import get_auth_context_with_legacy
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

# Species names that should NOT trigger Wikipedia lookup (no valid article exists)
SKIP_WIKIPEDIA_LOOKUP = {
    "Unknown Bird",
    "Background",
    "Unknown",
    "No Detection",
    "Unidentified"
}

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

async def _lookup_taxa_id(species_name: str) -> int | None:
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT taxa_id FROM taxonomy_cache
               WHERE lower(scientific_name) = lower(?) OR lower(common_name) = lower(?)
               LIMIT 1""",
            (species_name, species_name)
        )
        row = await cursor.fetchone()
    if row and row[0] is not None:
        return int(row[0])
    return None

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
    auth: AuthContext = Depends(get_auth_context_with_legacy)
):
    """Search for species labels (from classifier) and return with taxonomy info."""
    q = (q or "").strip()
    limit = max(1, min(limit, 100))

    q_lower = q.lower() if q else ""
    classifier = get_classifier()
    labels = classifier.labels
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

        results = []
        for label in matches:
            async with db.execute(
                "SELECT scientific_name, common_name, taxa_id FROM taxonomy_cache WHERE scientific_name = ? OR common_name = ?",
                (label, label)
            ) as cursor:
                row = await cursor.fetchone()

            sci_name = row[0] if row else None
            common_name = row[1] if row else None
            taxa_id = row[2] if row else None

            if lang != "en" and taxa_id:
                async with db.execute(
                    "SELECT common_name FROM taxonomy_translations WHERE taxa_id = ? AND language_code = ?",
                    (taxa_id, lang)
                ) as cursor:
                    translated = await cursor.fetchone()
                if translated and translated[0]:
                    common_name = translated[0]

            results.append({
                "id": label,  # The value to save
                "display_name": label,  # Fallback display
                "scientific_name": sci_name,
                "common_name": common_name
            })

    return results

def _is_bird_article(data: dict) -> bool:
    """
    Strictly validate that a Wikipedia article is about a bird species.
    Uses the description field which is very reliable for bird articles.
    """
    description = data.get("description", "").lower()
    extract = data.get("extract", "").lower()

    # Strong indicators in description - Wikipedia bird articles almost always have these
    # Examples: "species of bird", "species of passerine bird", "species of songbird"
    bird_description_phrases = [
        "species of bird",
        "species of passerine",
        "species of songbird",
        "species of finch",
        "species of sparrow",
        "species of warbler",
        "species of thrush",
        "species of wren",
        "species of crow",
        "species of jay",
        "species of tit",
        "species of duck",
        "species of goose",
        "species of owl",
        "species of hawk",
        "species of eagle",
        "species of heron",
        "species of gull",
        "species of woodpecker",
        "species of hummingbird",
        "genus of bird",
        "genus of birds",
        "family of bird",
        "family of birds",
        "order of bird",
        "order of birds",
        "class of bird",
        "class of birds",
        "subfamily of bird",
        "subfamily of birds",
        "subspecies of bird",
        "subspecies of birds",
        # German
        "vogelart",
        "art der vögel",
        "familie der vögel",
        "gattung der vögel",
        # French
        "espèce d'oiseau",
        "famille d'oiseaux",
        "genre d'oiseaux",
        # Spanish
        "especie de ave",
        "especie de pájaro",
        "familia de aves",
        "género de aves",
        # Italian
        "specie di uccello",
        "famiglia di uccelli",
        "genere di uccelli",
        # Dutch
        "vogelsoort",
        "familie van vogels",
        # Portuguese
        "espécie de ave",
        "família de aves",
        # Polish
        "gatunek ptaka",
        "rodzina ptaków",
        # Russian
        "вид птиц",
        "семейство птиц",
    ]

    # Check description first - this is very reliable
    for phrase in bird_description_phrases:
        if phrase in description:
            return True

    # Standalone bird groups that often appear at the beginning of descriptions
    # e.g., "Thrush native to Europe"
    standalone_bird_groups = [
        "thrush", "finch", "sparrow", "warbler", "wren", "tit", "duck", "goose",
        "owl", "hawk", "eagle", "heron", "gull", "woodpecker", "hummingbird",
        "corvid", "pigeon", "dove", "swift", "swallow", "falcon", "plover",
        "sandpiper", "kingfisher", "starling", "nuthatch", "creeper", "bulbul",
        "blackbird", "mockingbird", "thrasher", "waxwing", "tanager", "bunting",
        "cardinal", "grosbeak", "oriole", "blackbird", "grackle", "cowbird"
    ]

    # Check for standalone groups in description
    description_words = description.split()
    if description_words and any(word.strip(",.;") in standalone_bird_groups for word in description_words):
        return True

    # If description doesn't match, check for bird-specific terms in extract
    # But be stricter - require multiple bird-related terms
    bird_extract_keywords = [
        "bird", "avian", "ornithology", "plumage", "wingspan", "migratory",
        "nesting", "beak", "bill", "talon", "passerine", "songbird"
    ]
    taxonomy_keywords = [
        "passeriformes", "aves", "passerine", "oscine", "corvidae", "paridae",
        "fringillidae", "turdidae", "accipitridae", "anatidae", "picidae",
        "strigidae", "columbidae", "hirundinidae", "emberizidae", "ictenidae"
    ]

    # Count how many bird-specific keywords are present
    bird_keyword_count = sum(1 for kw in bird_extract_keywords if kw in extract)
    taxonomy_count = sum(1 for kw in taxonomy_keywords if kw in extract)

    # Higher ranks often mention "birds" in the plural
    if "birds" in extract or "birds" in description:
        return True

    # Require at least 2 bird keywords OR 1 taxonomy term to be confident
    if bird_keyword_count >= 2 or taxonomy_count >= 1:
        return True

    return False


@router.get("/species")
async def get_species_list(request: Request):
    """Get list of all species with counts."""
    lang = get_user_language(request)
    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.ensure_recent_rollups(90)
        stats = await repo.get_species_leaderboard_base()
        rollup_metrics = await repo.get_rollup_metrics()

        # Transform unknown bird labels for display and aggregate counts
        unknown_labels = settings.classification.unknown_bird_labels
        filtered_stats = []

        for s in stats:
            if s["species"] in unknown_labels:
                continue
            metrics = rollup_metrics.get(s["species"], {})
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
        unknown_stats = await repo.get_species_aggregate_for_labels(unknown_labels)
        if unknown_stats:
            unknown_rollup = await repo.get_rollup_metrics_for_species(unknown_labels)
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

        if is_unknown_query:
            # Aggregate stats for all unknown bird labels
            query_labels = list(unknown_labels)
        else:
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
                    if total_stats["first_seen"] is None or basic_stats["first_seen"] < total_stats["first_seen"]:
                        total_stats["first_seen"] = basic_stats["first_seen"]
                if basic_stats["last_seen"]:
                    if total_stats["last_seen"] is None or basic_stats["last_seen"] > total_stats["last_seen"]:
                        total_stats["last_seen"] = basic_stats["last_seen"]
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
        recent.sort(key=lambda x: x.detection_time, reverse=True)
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

            recent_detections.append(Detection(
                id=d.id,
                detection_time=d.detection_time,
                detection_index=d.detection_index,
                score=d.score,
                display_name="Unknown Bird" if d.display_name in unknown_labels else d.display_name,
                category_name=d.category_name,
                frigate_event=d.frigate_event,
                camera_name="Hidden" if hide_camera_names else d.camera_name,
                is_hidden=d.is_hidden,
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
                scientific_name=d.scientific_name,
                common_name=common_name,
                taxa_id=d.taxa_id
            ))

        # Get taxonomy names for the main species
        taxonomy = await repo.get_taxonomy_names(species_name)
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

    taxa_id = await _lookup_taxa_id(species_name)
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
            inat_info = await _fetch_inaturalist_info(species_name, lang)
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
            wiki_info = await _fetch_wikipedia_info(search_name, lang)
            # If search by eBird name failed, try original name
            if not wiki_info.extract and search_name != species_name:
                 wiki_info = await _fetch_wikipedia_info(species_name, lang)

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
            inat_info = await _fetch_inaturalist_info(search_name, lang)
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
        info = await _fetch_inaturalist_info(species_name, lang)
        if not info.extract or not info.thumbnail_url:
            wiki_info = None
            if info.wikipedia_url:
                wiki_info = await _fetch_wikipedia_info_from_url(info.wikipedia_url, species_name, lang)
            if not wiki_info:
                wiki_info = await _fetch_wikipedia_info(species_name, lang)
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
            fallback = await _fetch_wikipedia_info(species_name, "en")
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
        code = await ebird_service.resolve_species_code(species_name)
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


async def _fetch_wikipedia_info(species_name: str, lang: str) -> SpeciesInfo:
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
            article_title = await _find_wikipedia_article(client, species_name, lang)

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


async def _fetch_inaturalist_info(species_name: str, lang: str) -> SpeciesInfo:
    """Fetch species information from iNaturalist API."""
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(
                "https://api.inaturalist.org/v1/taxa",
                params={"q": species_name, "per_page": 1, "locale": lang}
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            if not results:
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

            taxon = results[0]
            taxa_id = taxon.get("id")
            scientific_name = taxon.get("name")
            preferred_common = taxon.get("preferred_common_name")
            title = preferred_common or scientific_name or species_name
            extract = taxon.get("wikipedia_summary")
            wikipedia_url = taxon.get("wikipedia_url")
            source_url = taxon.get("uri") or (f"https://www.inaturalist.org/taxa/{taxa_id}" if taxa_id else None)
            thumbnail_url = None
            default_photo = taxon.get("default_photo")
            if isinstance(default_photo, dict):
                thumbnail_url = default_photo.get("medium_url") or default_photo.get("square_url") or default_photo.get("url")

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
                taxa_id=taxa_id,
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


async def _find_wikipedia_article(client: httpx.AsyncClient, species_name: str, lang: str) -> str | None:
    """Try multiple strategies to find the correct Wikipedia article title."""
    base_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary"

    # Build list of title variations to try
    titles_to_try = []

    # Original name (with proper URL encoding)
    titles_to_try.append(species_name)

    # Try lowercase version (Wikipedia often uses sentence case)
    words = species_name.split()
    if len(words) >= 2:
        # Sentence case: "Eurasian blue tit" instead of "Eurasian Blue Tit"
        sentence_case = words[0] + " " + " ".join(w.lower() for w in words[1:])
        if sentence_case != species_name:
            titles_to_try.append(sentence_case)

        # Try without common regional prefixes (e.g., "Eurasian Blue Tit" -> "Blue Tit")
        regional_prefixes = ["Eurasian", "European", "American", "African", "Asian",
                            "Common", "Northern", "Southern", "Eastern", "Western",
                            "Greater", "Lesser", "Little", "Great"]
        if words[0] in regional_prefixes:
            short_name = " ".join(words[1:])
            titles_to_try.append(short_name)
            # Also try sentence case of short name
            if len(words) > 2:
                short_sentence = words[1] + " " + " ".join(w.lower() for w in words[2:])
                titles_to_try.append(short_sentence)

    # Add "(bird)" suffix variations
    base_titles = titles_to_try.copy()
    for title in base_titles:
        titles_to_try.append(f"{title} (bird)")

    log.debug("Trying Wikipedia title variations", species=species_name, variations=titles_to_try)

    # Strategy 1: Direct page summary lookup
    for title in titles_to_try:
        encoded = quote(title.replace(" ", "_"))
        url = f"{base_url}/{encoded}"
        try:
            log.debug("Trying Wikipedia URL", url=url)
            response = await client.get(url)
            log.debug("Wikipedia response", status=response.status_code, title=title)

            if response.status_code == 200:
                data = response.json()
                # Verify it's about a bird using strict validation
                if _is_bird_article(data):
                    log.info("Found Wikipedia article via direct lookup",
                            species=species_name, article=data.get("title"), tried=title)
                    return data.get("title")
                else:
                    log.debug("Article found but doesn't appear to be about birds",
                             title=title, description=data.get("description"))
            elif response.status_code == 404:
                log.debug("Wikipedia page not found", title=title)
            else:
                log.warning("Unexpected Wikipedia response", status=response.status_code, title=title)

        except Exception as e:
            log.warning("Error checking Wikipedia title", title=title, error=str(e))
            continue

    # Strategy 2: Use Wikipedia search API as fallback
    log.debug("Falling back to Wikipedia search API", species=species_name)
    search_url = f"https://{lang}.wikipedia.org/w/api.php"
    search_queries = [
        f"{species_name} bird",
        f'"{species_name}"',  # Exact phrase search
        species_name,
    ]

    for search_query in search_queries:
        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": search_query,
            "format": "json",
            "srlimit": 10
        }

        try:
            response = await client.get(search_url, params=search_params)
            log.debug("Wikipedia search response", status=response.status_code, query=search_query)

            if response.status_code == 200:
                data = response.json()
                results = data.get("query", {}).get("search", [])
                log.debug("Wikipedia search results", count=len(results), query=search_query)

                for result in results:
                    title = result.get("title", "")
                    snippet = result.get("snippet", "").lower()

                    # Quick check on snippet before making another API call
                    if any(word in snippet for word in ["bird", "species", "passerine", "avian"]):
                        # Verify with a page summary lookup using strict validation
                        verify_url = f"{base_url}/{quote(title.replace(' ', '_'))}"
                        try:
                            verify_response = await client.get(verify_url)
                            if verify_response.status_code == 200:
                                verify_data = verify_response.json()
                                # Use strict validation
                                if _is_bird_article(verify_data):
                                    log.info("Found Wikipedia article via search",
                                            species=species_name, article=title, query=search_query)
                                    return title
                        except Exception:
                            pass
        except Exception as e:
            log.warning("Wikipedia search failed", error=str(e), species=species_name, query=search_query)

    log.warning("All Wikipedia search strategies exhausted", species=species_name)
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
