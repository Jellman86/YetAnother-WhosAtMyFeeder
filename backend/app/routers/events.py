from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Literal
from datetime import datetime, date
from io import BytesIO
from pydantic import BaseModel, Field
import httpx
import structlog
from PIL import Image

from app.database import get_db
from app.models import DetectionResponse
from app.repositories.detection_repository import DetectionRepository
from app.config import settings
from app.services.classifier_service import ClassifierService

router = APIRouter()
log = structlog.get_logger()

# Classifier instance for reclassification
_classifier = None

def get_classifier() -> ClassifierService:
    global _classifier
    if _classifier is None:
        _classifier = ClassifierService()
    return _classifier


class EventFilters(BaseModel):
    """Available filter options for events."""
    species: List[str]
    cameras: List[str]


class EventsCountResponse(BaseModel):
    """Response for events count endpoint."""
    count: int
    filtered: bool


@router.get("/events/filters", response_model=EventFilters)
async def get_event_filters():
    """Get available filter options (species and cameras) from the database."""
    async with get_db() as db:
        repo = DetectionRepository(db)
        species = await repo.get_unique_species()
        cameras = await repo.get_unique_cameras()
        return EventFilters(species=species, cameras=cameras)


@router.get("/events", response_model=List[DetectionResponse])
async def get_events(
    limit: int = Query(default=50, ge=1, le=500, description="Number of events to return"),
    offset: int = Query(default=0, ge=0, description="Number of events to skip"),
    start_date: Optional[date] = Query(default=None, description="Filter events from this date (inclusive)"),
    end_date: Optional[date] = Query(default=None, description="Filter events until this date (inclusive)"),
    species: Optional[str] = Query(default=None, description="Filter by species name"),
    camera: Optional[str] = Query(default=None, description="Filter by camera name"),
    sort: Literal["newest", "oldest", "confidence"] = Query(default="newest", description="Sort order")
):
    """Get paginated events with optional filters."""
    async with get_db() as db:
        repo = DetectionRepository(db)

        # Convert dates to datetime for filtering
        start_datetime = datetime.combine(start_date, datetime.min.time()) if start_date else None
        end_datetime = datetime.combine(end_date, datetime.max.time()) if end_date else None

        events = await repo.get_all(
            limit=limit,
            offset=offset,
            start_date=start_datetime,
            end_date=end_datetime,
            species=species,
            camera=camera,
            sort=sort
        )
        return events


@router.get("/events/count", response_model=EventsCountResponse)
async def get_events_count(
    start_date: Optional[date] = Query(default=None, description="Filter events from this date (inclusive)"),
    end_date: Optional[date] = Query(default=None, description="Filter events until this date (inclusive)"),
    species: Optional[str] = Query(default=None, description="Filter by species name"),
    camera: Optional[str] = Query(default=None, description="Filter by camera name")
):
    """Get total count of events (optionally filtered)."""
    async with get_db() as db:
        repo = DetectionRepository(db)

        start_datetime = datetime.combine(start_date, datetime.min.time()) if start_date else None
        end_datetime = datetime.combine(end_date, datetime.max.time()) if end_date else None

        count = await repo.get_count(
            start_date=start_datetime,
            end_date=end_datetime,
            species=species,
            camera=camera
        )

        # Determine if any filters are applied
        filtered = any([start_date, end_date, species, camera])

        return EventsCountResponse(count=count, filtered=filtered)

@router.delete("/events/{event_id}")
async def delete_event(event_id: str):
    """Delete a detection by its Frigate event ID."""
    async with get_db() as db:
        repo = DetectionRepository(db)
        deleted = await repo.delete_by_frigate_event(event_id)
        if deleted:
            return {"status": "deleted", "event_id": event_id}
        raise HTTPException(status_code=404, detail="Detection not found")


class UpdateDetectionRequest(BaseModel):
    """Request to manually update a detection's species."""
    display_name: str = Field(..., min_length=1, description="New species name")


class ReclassifyResponse(BaseModel):
    """Response from reclassification."""
    status: str
    event_id: str
    old_species: str
    new_species: str
    new_score: float
    updated: bool


@router.post("/events/{event_id}/reclassify", response_model=ReclassifyResponse)
async def reclassify_event(event_id: str):
    """
    Re-run the classifier on an existing detection.
    Fetches the snapshot from Frigate and runs it through the ML model again.
    """
    async with get_db() as db:
        repo = DetectionRepository(db)
        detection = await repo.get_by_frigate_event(event_id)

        if not detection:
            raise HTTPException(status_code=404, detail="Detection not found")

        old_species = detection.display_name

        # Fetch snapshot from Frigate
        frigate_url = settings.frigate.frigate_url
        snapshot_url = f"{frigate_url}/api/events/{event_id}/snapshot.jpg"

        headers = {}
        if settings.frigate.frigate_auth_token:
            headers['Authorization'] = f'Bearer {settings.frigate.frigate_auth_token}'

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    snapshot_url,
                    params={"crop": 1, "quality": 95},
                    headers=headers,
                    timeout=30.0
                )

                if response.status_code != 200:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Failed to fetch snapshot from Frigate: {response.status_code}"
                    )

                # Classify the image
                image = Image.open(BytesIO(response.content))
                classifier = get_classifier()
                results = classifier.classify(image)

                if not results:
                    raise HTTPException(status_code=500, detail="Classification returned no results")

                top = results[0]
                new_species = top['label']
                new_score = top['score']

                # Update if species changed
                updated = False
                if new_species != old_species:
                    detection.display_name = new_species
                    detection.category_name = new_species
                    detection.score = new_score
                    detection.detection_index = top['index']
                    await repo.update(detection)
                    updated = True
                    log.info("Reclassified detection",
                             event_id=event_id,
                             old_species=old_species,
                             new_species=new_species,
                             score=new_score)

                return ReclassifyResponse(
                    status="success",
                    event_id=event_id,
                    old_species=old_species,
                    new_species=new_species,
                    new_score=new_score,
                    updated=updated
                )

        except httpx.RequestError as e:
            log.error("Failed to fetch snapshot", event_id=event_id, error=str(e))
            raise HTTPException(status_code=502, detail=f"Failed to connect to Frigate: {str(e)}")


@router.patch("/events/{event_id}")
async def update_event(event_id: str, request: UpdateDetectionRequest):
    """
    Manually update a detection's species name.
    Use this to correct misidentifications.
    """
    async with get_db() as db:
        repo = DetectionRepository(db)
        detection = await repo.get_by_frigate_event(event_id)

        if not detection:
            raise HTTPException(status_code=404, detail="Detection not found")

        old_species = detection.display_name
        new_species = request.display_name.strip()

        if old_species == new_species:
            return {
                "status": "unchanged",
                "event_id": event_id,
                "species": new_species
            }

        # Update the detection
        detection.display_name = new_species
        detection.category_name = new_species
        await repo.update(detection)

        log.info("Manually updated detection species",
                 event_id=event_id,
                 old_species=old_species,
                 new_species=new_species)

        return {
            "status": "updated",
            "event_id": event_id,
            "old_species": old_species,
            "new_species": new_species
        }
