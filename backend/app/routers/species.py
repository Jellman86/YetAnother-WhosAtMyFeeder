from fastapi import APIRouter, HTTPException, Request, Depends
from datetime import datetime, timedelta
from urllib.parse import quote
import httpx
import structlog

from app.database import get_db
from app.repositories.detection_repository import DetectionRepository
from app.models import SpeciesStats, SpeciesInfo, CameraStats, Detection
from app.config import settings
from app.services.taxonomy.taxonomy_service import taxonomy_service
from app.services.i18n_service import i18n_service
from app.services.classifier_service import get_classifier
from app.utils.language import get_user_language

router = APIRouter()
log = structlog.get_logger()

# Species info cache with TTL
_wiki_cache: dict[str, tuple[SpeciesInfo, datetime]] = {}
CACHE_TTL_SUCCESS = timedelta(hours=24)
CACHE_TTL_FAILURE = timedelta(minutes=15)  # Short TTL for failures to allow retries

# User-Agent is required by Wikipedia API - they block requests without it
WIKIPEDIA_USER_AGENT = "YA-WAMF/2.0 (Bird Watching App; https://github.com/Jellman86/YetAnother-WhosAtMyFeeder)"

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

async def _get_cached_species_info(species_name: str, taxa_id: int | None, refresh: bool) -> SpeciesInfo | None:
    if refresh:
        return None

    if species_name in _wiki_cache:
        info, cached_at = _wiki_cache[species_name]
        if _is_cache_valid(info, cached_at):
            log.debug("Returning cached species info (memory)", species=species_name)
            return info

    async with get_db() as db:
        if taxa_id:
            cursor = await db.execute(
                """SELECT title, description, extract, thumbnail_url, wikipedia_url, source, source_url,
                          scientific_name, conservation_status, cached_at
                   FROM species_info_cache WHERE taxa_id = ?
                   ORDER BY cached_at DESC LIMIT 1""",
                (taxa_id,)
            )
        else:
            cursor = await db.execute(
                """SELECT title, description, extract, thumbnail_url, wikipedia_url, source, source_url,
                          scientific_name, conservation_status, cached_at
                   FROM species_info_cache WHERE species_name = ?""",
                (species_name,)
            )
        row = await cursor.fetchone()

    if not row:
        return None

    cached_at = _parse_cached_at(row[9])
    info = SpeciesInfo(
        title=row[0] or species_name,
        description=row[1],
        extract=row[2],
        thumbnail_url=row[3],
        wikipedia_url=row[4],
        source=row[5],
        source_url=row[6],
        scientific_name=row[7],
        conservation_status=row[8],
        cached_at=cached_at
    )

    if _is_cache_valid(info, cached_at):
        _wiki_cache[species_name] = (info, cached_at or datetime.now())
        log.debug("Returning cached species info (db)", species=species_name)
        return info

    return None

async def _save_species_info(species_name: str, taxa_id: int | None, info: SpeciesInfo) -> None:
    cached_at = datetime.now()
    info.cached_at = cached_at
    async with get_db() as db:
        if taxa_id:
            cursor = await db.execute(
                "SELECT id FROM species_info_cache WHERE taxa_id = ? LIMIT 1",
                (taxa_id,)
            )
            existing = await cursor.fetchone()
        else:
            existing = None

        if existing:
            await db.execute(
                """UPDATE species_info_cache SET
                     species_name = ?,
                     title = ?,
                     taxa_id = ?,
                     description = ?,
                     extract = ?,
                     thumbnail_url = ?,
                     wikipedia_url = ?,
                     source = ?,
                     source_url = ?,
                     scientific_name = ?,
                     conservation_status = ?,
                     cached_at = ?
                   WHERE id = ?""",
                (
                    species_name,
                    info.title,
                    taxa_id,
                    info.description,
                    info.extract,
                    info.thumbnail_url,
                    info.wikipedia_url,
                    info.source,
                    info.source_url,
                    info.scientific_name,
                    info.conservation_status,
                    cached_at,
                    existing[0]
                )
            )
        else:
            await db.execute(
                """INSERT INTO species_info_cache
                   (species_name, title, taxa_id, description, extract, thumbnail_url, wikipedia_url, source, source_url,
                    scientific_name, conservation_status, cached_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(species_name) DO UPDATE SET
                     title = excluded.title,
                     taxa_id = excluded.taxa_id,
                     description = excluded.description,
                     extract = excluded.extract,
                     thumbnail_url = excluded.thumbnail_url,
                     wikipedia_url = excluded.wikipedia_url,
                     source = excluded.source,
                     source_url = excluded.source_url,
                     scientific_name = excluded.scientific_name,
                     conservation_status = excluded.conservation_status,
                     cached_at = excluded.cached_at""",
                (
                    species_name,
                    info.title,
                    taxa_id,
                    info.description,
                    info.extract,
                    info.thumbnail_url,
                    info.wikipedia_url,
                    info.source,
                    info.source_url,
                    info.scientific_name,
                    info.conservation_status,
                    cached_at
                )
            )
        await db.commit()

@router.get("/species/search")
async def search_species(q: str):
    """Search for species labels (from classifier) and return with taxonomy info."""
    if not q:
        return []
    
    q_lower = q.lower()
    classifier = get_classifier()
    labels = classifier.labels
    
    # Filter labels (limit to 50 matches)
    matches = [l for l in labels if q_lower in l.lower()][:50]
    
    results = []
    async with get_db() as db:
        for label in matches:
            # Lookup taxonomy (check cache only to be fast)
            # We use taxonomy_service.get_names but strictly from cache/DB if possible to avoid 50 API calls
            # Actually, taxonomy_service.get_names checks cache first.
            # But we don't want to trigger iNaturalist lookups for 50 items if they aren't cached.
            # So we will inspect the cache directly or use a helper.
            
            # For now, let's just query the cache table manually for speed
            async with db.execute(
                "SELECT scientific_name, common_name FROM taxonomy_cache WHERE scientific_name = ? OR common_name = ?", 
                (label, label)
            ) as cursor:
                row = await cursor.fetchone()
                
            sci_name = row[0] if row else None
            common_name = row[1] if row else label
            
            results.append({
                "id": label, # The value to save
                "display_name": label, # Fallback display
                "scientific_name": sci_name,
                "common_name": common_name
            })
            
    return results

# ... existing code ...
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
        "family of bird",
        "order of bird",
    ]

    # Check description first - this is very reliable
    for phrase in bird_description_phrases:
        if phrase in description:
            return True

    # If description doesn't match, check for bird-specific terms in extract
    # But be stricter - require multiple bird-related terms
    bird_extract_keywords = ["bird", "avian", "ornithology", "plumage", "wingspan", "migratory"]
    taxonomy_keywords = ["passeriformes", "aves", "passerine", "oscine", "corvidae", "paridae", "fringillidae"]

    # Count how many bird-specific keywords are present
    bird_keyword_count = sum(1 for kw in bird_extract_keywords if kw in extract)
    taxonomy_count = sum(1 for kw in taxonomy_keywords if kw in extract)

    # Require at least 2 bird keywords OR 1 taxonomy term to be confident
    if bird_keyword_count >= 2 or taxonomy_count >= 1:
        return True

    # Special case: if "bird" is in description (not just extract), that's usually good enough
    if "bird" in description:
        return True

    return False


@router.get("/species")
async def get_species_list(request: Request):
    """Get list of all species with counts."""
    lang = get_user_language(request)
    async with get_db() as db:
        repo = DetectionRepository(db)
        stats = await repo.get_species_counts()

        # Transform unknown bird labels for display and aggregate counts
        unknown_labels = settings.classification.unknown_bird_labels
        unknown_count = 0
        filtered_stats = []

        for s in stats:
            if s["species"] in unknown_labels:
                unknown_count += s["count"]
            else:
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
                    "taxa_id": taxa_id
                })

        # Add aggregated "Unknown Bird" entry if any were found
        if unknown_count > 0:
            filtered_stats.append({
                "species": "Unknown Bird", 
                "count": unknown_count,
                "scientific_name": None,
                "common_name": None
            })
            # Re-sort by count descending
            filtered_stats.sort(key=lambda x: x["count"], reverse=True)

        return filtered_stats

@router.get("/species/{species_name}/stats", response_model=SpeciesStats)
async def get_species_stats(species_name: str, request: Request):
    """Get comprehensive statistics for a species."""
    lang = get_user_language(request)
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
                camera_name=d.camera_name,
                is_hidden=d.is_hidden,
                frigate_score=d.frigate_score,
                sub_label=d.sub_label,
                audio_confirmed=d.audio_confirmed,
                audio_species=d.audio_species,
                audio_score=d.audio_score,
                temperature=d.temperature,
                weather_condition=d.weather_condition,
                scientific_name=d.scientific_name,
                common_name=common_name,
                taxa_id=d.taxa_id
            ))

        # Get taxonomy names for the main species
        taxonomy = await repo.get_taxonomy_names(species_name)
        common_name = taxonomy["common_name"]
        
        # Localize main common name if needed
        taxa_id = None
        if recent:
            taxa_id = recent[0].taxa_id
        
        if lang != 'en' and taxa_id:
            localized = await taxonomy_service.get_localized_common_name(taxa_id, lang, db=db)
            if localized:
                common_name = localized

        return SpeciesStats(
            species_name=species_name,
            scientific_name=taxonomy["scientific_name"],
            common_name=common_name,
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
async def clear_species_cache(species_name: str):
    """Clear the Wikipedia cache for a species."""
    if species_name in _wiki_cache:
        del _wiki_cache[species_name]
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
async def get_species_info(species_name: str, refresh: bool = False):
    """Get species information for a species. Use refresh=true to bypass cache."""
    log.info("Fetching species info", species=species_name, refresh=refresh)

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
    cached_info = await _get_cached_species_info(species_name, taxa_id, refresh)
    if cached_info:
        return cached_info

    # Fetch from iNaturalist first, then fill gaps with Wikipedia
    info = await _fetch_inaturalist_info(species_name)
    if not info.extract or not info.thumbnail_url:
        wiki_info = await _fetch_wikipedia_info(species_name)
        if not info.extract and wiki_info.extract:
            info.extract = wiki_info.extract
            info.source = wiki_info.source
            info.source_url = wiki_info.source_url
        if not info.thumbnail_url and wiki_info.thumbnail_url:
            info.thumbnail_url = wiki_info.thumbnail_url
        if not info.wikipedia_url and wiki_info.wikipedia_url:
            info.wikipedia_url = wiki_info.wikipedia_url
        if not info.scientific_name and wiki_info.scientific_name:
            info.scientific_name = wiki_info.scientific_name

    # Cache the result
    await _save_species_info(species_name, taxa_id, info)
    _wiki_cache[species_name] = (info, info.cached_at or datetime.now())

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

async def _fetch_wikipedia_info(species_name: str) -> SpeciesInfo:
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
            article_title = await _find_wikipedia_article(client, species_name)

            if article_title:
                log.info("Found Wikipedia article", species=species_name, article=article_title)
                return await _get_wikipedia_summary(client, article_title, species_name)
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


async def _fetch_inaturalist_info(species_name: str) -> SpeciesInfo:
    """Fetch species information from iNaturalist API."""
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(
                "https://api.inaturalist.org/v1/taxa",
                params={"q": species_name, "per_page": 1}
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
            scientific_name = taxon.get("name")
            preferred_common = taxon.get("preferred_common_name")
            title = preferred_common or scientific_name or species_name
            extract = taxon.get("wikipedia_summary")
            wikipedia_url = taxon.get("wikipedia_url")
            source_url = taxon.get("uri") or (f"https://www.inaturalist.org/taxa/{taxon.get('id')}" if taxon.get("id") else None)
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
                scientific_name=scientific_name,
                conservation_status=None,
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


async def _find_wikipedia_article(client: httpx.AsyncClient, species_name: str) -> str | None:
    """Try multiple strategies to find the correct Wikipedia article title."""
    base_url = "https://en.wikipedia.org/api/rest_v1/page/summary"

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
    search_url = "https://en.wikipedia.org/w/api.php"
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


async def _get_wikipedia_summary(client: httpx.AsyncClient, article_title: str, original_name: str) -> SpeciesInfo:
    """Fetch the summary for a Wikipedia article."""
    import re

    base_url = "https://en.wikipedia.org/api/rest_v1/page/summary"
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
