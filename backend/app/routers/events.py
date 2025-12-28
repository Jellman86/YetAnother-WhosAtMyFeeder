from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Literal
from datetime import datetime, date
from io import BytesIO
from pydantic import BaseModel, Field
import structlog
from PIL import Image

from app.database import get_db
from app.models import DetectionResponse
from app.repositories.detection_repository import DetectionRepository
from app.config import settings
from app.services.classifier_service import get_classifier, ClassifierService
from app.services.frigate_client import frigate_client

router = APIRouter()
log = structlog.get_logger()


async def batch_check_clips(event_ids: list[str]) -> dict[str, bool]:
    """
    Check clip availability for multiple events from Frigate.
    Returns a dict mapping event_id -> has_clip boolean.
    """
    if not event_ids:
        return {}

    result = {}
    for event_id in event_ids:
        try:
            event_data = await frigate_client.get_event(event_id)
            result[event_id] = event_data.get("has_clip", False) if event_data else False
        except Exception:
            result[event_id] = False

    return result

# get_classifier is now imported from classifier_service


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
    sort: Literal["newest", "oldest", "confidence"] = Query(default="newest", description="Sort order"),
    include_hidden: bool = Query(default=False, description="Include hidden/ignored detections")
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
            sort=sort,
            include_hidden=include_hidden
        )

        # Batch fetch clip availability from Frigate (eliminates N individual HEAD requests)
        event_ids = [e.frigate_event for e in events]
        clip_availability = await batch_check_clips(event_ids)

        # Get labels that should be displayed as "Unknown Bird"
        unknown_labels = settings.classification.unknown_bird_labels

        # Convert to response models with clip info
        response_events = []
        for event in events:
            # Transform unknown bird labels for display
            display_name = event.display_name
            if display_name in unknown_labels:
                display_name = "Unknown Bird"

            response_event = DetectionResponse(
                id=event.id,
                detection_time=event.detection_time,
                detection_index=event.detection_index,
                score=event.score,
                display_name=display_name,
                category_name=event.category_name,
                frigate_event=event.frigate_event,
                camera_name=event.camera_name,
                has_clip=clip_availability.get(event.frigate_event, False),
                is_hidden=event.is_hidden,
                frigate_score=event.frigate_score,
                sub_label=event.sub_label
            )
            response_events.append(response_event)

        return response_events


class HiddenCountResponse(BaseModel):
    """Response for hidden count endpoint."""
    hidden_count: int


@router.get("/events/hidden-count", response_model=HiddenCountResponse)
async def get_hidden_count():
    """Get count of hidden detections."""
    async with get_db() as db:
        repo = DetectionRepository(db)
        count = await repo.get_hidden_count()
        return HiddenCountResponse(hidden_count=count)


@router.get("/events/count", response_model=EventsCountResponse)
async def get_events_count(
    start_date: Optional[date] = Query(default=None, description="Filter events from this date (inclusive)"),
    end_date: Optional[date] = Query(default=None, description="Filter events until this date (inclusive)"),
    species: Optional[str] = Query(default=None, description="Filter by species name"),
    camera: Optional[str] = Query(default=None, description="Filter by camera name"),
    include_hidden: bool = Query(default=False, description="Include hidden/ignored detections")
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
            camera=camera,
            include_hidden=include_hidden
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


class HideResponse(BaseModel):
    """Response for hide/unhide action."""
    status: str
    event_id: str
    is_hidden: bool


@router.post("/events/{event_id}/hide", response_model=HideResponse)
async def toggle_hide_event(event_id: str):
    """Toggle the hidden/ignored status of a detection."""
    async with get_db() as db:
        repo = DetectionRepository(db)
        new_status = await repo.toggle_hidden(event_id)

        if new_status is None:
            raise HTTPException(status_code=404, detail="Detection not found")

        action = "hidden" if new_status else "unhidden"
        log.info(f"Detection {action}", event_id=event_id, is_hidden=new_status)

        return HideResponse(
            status="updated",
            event_id=event_id,
            is_hidden=new_status
        )


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

        # Fetch snapshot from Frigate using centralized client
        snapshot_data = await frigate_client.get_snapshot(event_id, crop=True, quality=95)
        if not snapshot_data:
            raise HTTPException(status_code=502, detail="Failed to fetch snapshot from Frigate")

        # Classify the image
        image = Image.open(BytesIO(snapshot_data))
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
            # Execute update directly for reliability
            await db.execute("""
                UPDATE detections
                SET display_name = ?, category_name = ?, score = ?, detection_index = ?
                WHERE frigate_event = ?
            """, (new_species, new_species, new_score, top['index'], event_id))
            await db.commit()
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

        log.debug("Manual tag request",
                  event_id=event_id,
                  old_species=old_species,
                  new_species=new_species,
                  frigate_event=detection.frigate_event)

        if old_species == new_species:
            return {
                "status": "unchanged",
                "event_id": event_id,
                "species": new_species
            }

        # Update the detection - create new object to ensure all fields are set
        detection.display_name = new_species
        detection.category_name = new_species

        # Execute update directly for reliability
        await db.execute("""
            UPDATE detections
            SET display_name = ?, category_name = ?
            WHERE frigate_event = ?
        """, (new_species, new_species, event_id))
        await db.commit()

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


class WildlifeClassification(BaseModel):
    """A single wildlife classification result."""
    label: str
    score: float
    index: int


class WildlifeClassifyResponse(BaseModel):
    """Response from wildlife classification."""
    status: str
    event_id: str
    classifications: List[WildlifeClassification]


@router.post("/events/{event_id}/classify-wildlife", response_model=WildlifeClassifyResponse)
async def classify_wildlife(event_id: str):
    """
    Classify a detection using the general wildlife model.
    Fetches the snapshot from Frigate and runs it through the wildlife classifier.
    Does NOT update the database - user can manually tag if desired.
    """
    async with get_db() as db:
        repo = DetectionRepository(db)
        detection = await repo.get_by_frigate_event(event_id)

        if not detection:
            raise HTTPException(status_code=404, detail="Detection not found")

        # Fetch snapshot from Frigate using centralized client
        snapshot_data = await frigate_client.get_snapshot(event_id, crop=True, quality=95)
        if not snapshot_data:
            raise HTTPException(status_code=502, detail="Failed to fetch snapshot from Frigate")

        # Classify with wildlife model
        image = Image.open(BytesIO(snapshot_data))
        classifier = get_classifier()
        results = classifier.classify_wildlife(image)

        if not results:
            # Wildlife model not available or no results
            wildlife_status = classifier.get_wildlife_status()
            if not wildlife_status.get("enabled"):
                raise HTTPException(
                    status_code=503,
                    detail="Wildlife model not available. Please download the wildlife model first."
                )
            raise HTTPException(status_code=500, detail="Classification returned no results")

        classifications = [
            WildlifeClassification(
                label=r['label'],
                score=r['score'],
                index=r['index']
            )
            for r in results
        ]

        log.info("Wildlife classification complete",
                 event_id=event_id,
                 top_result=results[0]['label'] if results else None,
                 top_score=results[0]['score'] if results else None)

        return WildlifeClassifyResponse(
            status="success",
            event_id=event_id,
            classifications=classifications
        )
