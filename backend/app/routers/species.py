from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta
from urllib.parse import quote
import httpx
import structlog

from app.database import get_db
from app.repositories.detection_repository import DetectionRepository
from app.models import SpeciesStats, SpeciesInfo, CameraStats, Detection

router = APIRouter()
log = structlog.get_logger()

# Wikipedia info cache with TTL
_wiki_cache: dict[str, tuple[SpeciesInfo, datetime]] = {}
CACHE_TTL = timedelta(hours=24)

@router.get("/species")
async def get_species_list():
    """Get list of all species with counts."""
    async with get_db() as db:
        repo = DetectionRepository(db)
        stats = await repo.get_species_counts()
        return stats

@router.get("/species/{species_name}/stats", response_model=SpeciesStats)
async def get_species_stats(species_name: str):
    """Get comprehensive statistics for a species."""
    async with get_db() as db:
        repo = DetectionRepository(db)

        # Get all stats in parallel-ish (they're all DB queries)
        basic_stats = await repo.get_species_basic_stats(species_name)

        if basic_stats["total"] == 0:
            raise HTTPException(status_code=404, detail=f"No sightings found for species: {species_name}")

        camera_breakdown = await repo.get_camera_breakdown(species_name)
        hourly = await repo.get_hourly_distribution(species_name)
        daily = await repo.get_daily_distribution(species_name)
        monthly = await repo.get_monthly_distribution(species_name)
        recent = await repo.get_recent_by_species(species_name, limit=5)

        # Convert dataclass detections to Pydantic models
        recent_detections = [
            Detection(
                id=d.id,
                detection_time=d.detection_time,
                detection_index=d.detection_index,
                score=d.score,
                display_name=d.display_name,
                category_name=d.category_name,
                frigate_event=d.frigate_event,
                camera_name=d.camera_name
            )
            for d in recent
        ]

        return SpeciesStats(
            species_name=species_name,
            total_sightings=basic_stats["total"],
            first_seen=basic_stats["first_seen"],
            last_seen=basic_stats["last_seen"],
            cameras=[CameraStats(**c) for c in camera_breakdown],
            hourly_distribution=hourly,
            daily_distribution=daily,
            monthly_distribution=monthly,
            avg_confidence=basic_stats["avg_confidence"],
            max_confidence=basic_stats["max_confidence"],
            min_confidence=basic_stats["min_confidence"],
            recent_sightings=recent_detections
        )

@router.get("/species/{species_name}/info", response_model=SpeciesInfo)
async def get_species_info(species_name: str, refresh: bool = False):
    """Get Wikipedia information for a species."""
    # Check cache first (unless refresh requested)
    if not refresh and species_name in _wiki_cache:
        info, cached_at = _wiki_cache[species_name]
        if datetime.now() - cached_at < CACHE_TTL:
            # Only return cached result if it has actual data
            if info.thumbnail_url or info.extract:
                return info
            # For failed lookups, only cache for 1 hour
            elif datetime.now() - cached_at < timedelta(hours=1):
                return info

    # Fetch from Wikipedia
    info = await _fetch_wikipedia_info(species_name)

    # Cache the result
    _wiki_cache[species_name] = (info, datetime.now())

    return info

async def _fetch_wikipedia_info(species_name: str) -> SpeciesInfo:
    """Fetch species information from Wikipedia API."""
    import re

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        # Try multiple strategies to find the Wikipedia article
        article_title = await _find_wikipedia_article(client, species_name)

        if article_title:
            return await _get_wikipedia_summary(client, article_title, species_name)

    # Return minimal info if Wikipedia lookup failed
    log.warning("Could not find Wikipedia article", species=species_name)
    return SpeciesInfo(
        title=species_name,
        description=None,
        extract=None,
        thumbnail_url=None,
        wikipedia_url=None,
        scientific_name=None,
        conservation_status=None,
        cached_at=datetime.now()
    )


async def _find_wikipedia_article(client: httpx.AsyncClient, species_name: str) -> str | None:
    """Try multiple strategies to find the correct Wikipedia article title."""
    base_url = "https://en.wikipedia.org/api/rest_v1/page/summary"

    # Strategy 1: Try exact name
    titles_to_try = [
        species_name,
        f"{species_name} (bird)",
    ]

    # Strategy 2: If name has multiple words, try variations
    words = species_name.split()
    if len(words) >= 2:
        # Try without common regional prefixes (e.g., "Eurasian Blue Tit" -> "Blue Tit")
        regional_prefixes = ["Eurasian", "European", "American", "African", "Asian", "Common", "Northern", "Southern", "Eastern", "Western"]
        if words[0] in regional_prefixes:
            short_name = " ".join(words[1:])
            titles_to_try.append(short_name)
            titles_to_try.append(f"{short_name} (bird)")

    for title in titles_to_try:
        encoded = quote(title.replace(" ", "_"))
        url = f"{base_url}/{encoded}"
        try:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                # Verify it's about a bird by checking the extract
                extract = data.get("extract", "").lower()
                if any(word in extract for word in ["bird", "species", "passerine", "family", "genus"]):
                    log.info("Found Wikipedia article", species=species_name, article=data.get("title"))
                    return data.get("title")
        except Exception:
            continue

    # Strategy 3: Use Wikipedia search API as fallback
    search_url = "https://en.wikipedia.org/w/api.php"
    search_params = {
        "action": "query",
        "list": "search",
        "srsearch": f"{species_name} bird",
        "format": "json",
        "srlimit": 5
    }

    try:
        response = await client.get(search_url, params=search_params)
        if response.status_code == 200:
            data = response.json()
            results = data.get("query", {}).get("search", [])
            for result in results:
                title = result.get("title", "")
                # Verify this result is related to our bird
                snippet = result.get("snippet", "").lower()
                if any(word in snippet for word in ["bird", "species", "passerine"]):
                    log.info("Found Wikipedia article via search", species=species_name, article=title)
                    return title
    except Exception as e:
        log.warning("Wikipedia search failed", error=str(e), species=species_name)

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

            return SpeciesInfo(
                title=data.get("title", original_name),
                description=description if description else None,
                extract=extract if extract else None,
                thumbnail_url=thumbnail_url,
                wikipedia_url=data.get("content_urls", {}).get("desktop", {}).get("page"),
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
        scientific_name=None,
        conservation_status=None,
        cached_at=datetime.now()
    )
