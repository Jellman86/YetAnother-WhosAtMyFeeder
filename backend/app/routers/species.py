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
CACHE_TTL_SUCCESS = timedelta(hours=24)
CACHE_TTL_FAILURE = timedelta(minutes=15)  # Short TTL for failures to allow retries

# User-Agent is required by Wikipedia API - they block requests without it
WIKIPEDIA_USER_AGENT = "YA-WAMF/2.0 (Bird Watching App; https://github.com/Jellman86/YetAnother-WhosAtMyFeeder)"

# Species names that should NOT trigger Wikipedia lookup (no valid article exists)
SKIP_WIKIPEDIA_LOOKUP = {"Unknown Bird", "unknown bird", "background", "Background"}


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

@router.delete("/species/{species_name}/cache")
async def clear_species_cache(species_name: str):
    """Clear the Wikipedia cache for a species."""
    if species_name in _wiki_cache:
        del _wiki_cache[species_name]
        log.info("Cleared species cache", species=species_name)
        return {"status": "cleared", "species": species_name}
    return {"status": "not_cached", "species": species_name}


@router.get("/species/{species_name}/info", response_model=SpeciesInfo)
async def get_species_info(species_name: str, refresh: bool = False):
    """Get Wikipedia information for a species. Use refresh=true to bypass cache."""
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
            scientific_name=None,
            conservation_status=None,
            cached_at=datetime.now()
        )

    # Check cache first (unless refresh requested)
    if not refresh and species_name in _wiki_cache:
        info, cached_at = _wiki_cache[species_name]
        age = datetime.now() - cached_at
        is_success = bool(info.thumbnail_url or info.extract)

        # Use appropriate TTL based on whether the cached result was successful
        cache_ttl = CACHE_TTL_SUCCESS if is_success else CACHE_TTL_FAILURE

        if age < cache_ttl:
            log.debug("Returning cached species info", species=species_name, is_success=is_success, age_seconds=age.total_seconds())
            return info
        else:
            log.debug("Cache expired", species=species_name, age_seconds=age.total_seconds())

    # Fetch from Wikipedia
    info = await _fetch_wikipedia_info(species_name)

    # Cache the result
    _wiki_cache[species_name] = (info, datetime.now())

    is_success = bool(info.thumbnail_url or info.extract)
    log.info("Wikipedia fetch complete", species=species_name, success=is_success, has_thumbnail=bool(info.thumbnail_url), has_extract=bool(info.extract))

    return info

async def _fetch_wikipedia_info(species_name: str) -> SpeciesInfo:
    """Fetch species information from Wikipedia API."""
    import re

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
