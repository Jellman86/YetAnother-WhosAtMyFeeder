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
async def get_species_info(species_name: str):
    """Get Wikipedia information for a species."""
    # Check cache first
    if species_name in _wiki_cache:
        info, cached_at = _wiki_cache[species_name]
        if datetime.now() - cached_at < CACHE_TTL:
            return info

    # Fetch from Wikipedia
    info = await _fetch_wikipedia_info(species_name)

    # Cache the result
    _wiki_cache[species_name] = (info, datetime.now())

    return info

async def _fetch_wikipedia_info(species_name: str) -> SpeciesInfo:
    """Fetch species information from Wikipedia API."""
    base_url = "https://en.wikipedia.org/api/rest_v1/page/summary"

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Try exact match first
        encoded_name = quote(species_name.replace(" ", "_"))
        url = f"{base_url}/{encoded_name}"

        try:
            response = await client.get(url)

            # If not found, try with "(bird)" suffix
            if response.status_code == 404:
                encoded_name_bird = quote(f"{species_name}_(bird)".replace(" ", "_"))
                url = f"{base_url}/{encoded_name_bird}"
                response = await client.get(url)

            if response.status_code == 200:
                data = response.json()

                # Extract scientific name from description or extract if present
                scientific_name = None
                extract = data.get("extract", "")

                # Try to find italicized binomial nomenclature pattern
                # Common patterns: "Genus species" at start of description
                description = data.get("description", "")

                # Get the best available image - prefer originalimage, fall back to thumbnail
                # and request a larger size
                thumbnail_url = None
                if "originalimage" in data:
                    thumbnail_url = data["originalimage"].get("source")
                elif "thumbnail" in data:
                    # Get thumbnail URL and try to get a larger version
                    thumb_url = data["thumbnail"].get("source", "")
                    # Wikipedia thumbnail URLs have format: .../320px-Image.jpg
                    # We can request a larger size by changing the number
                    if "/thumb/" in thumb_url and "px-" in thumb_url:
                        # Replace the size with 800px for a larger image
                        import re
                        thumbnail_url = re.sub(r'/\d+px-', '/800px-', thumb_url)
                    else:
                        thumbnail_url = thumb_url

                return SpeciesInfo(
                    title=data.get("title", species_name),
                    description=description if description else None,
                    extract=extract if extract else None,
                    thumbnail_url=thumbnail_url,
                    wikipedia_url=data.get("content_urls", {}).get("desktop", {}).get("page"),
                    scientific_name=scientific_name,
                    conservation_status=None,  # Would need additional parsing
                    cached_at=datetime.now()
                )
            else:
                log.warning("Wikipedia API returned non-200", status=response.status_code, species=species_name)
        except httpx.RequestError as e:
            log.error("Wikipedia API request failed", error=str(e), species=species_name)
        except Exception as e:
            log.error("Error parsing Wikipedia response", error=str(e), species=species_name)

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
