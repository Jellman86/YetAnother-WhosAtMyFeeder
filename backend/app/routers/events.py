from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Literal
from datetime import datetime, date
from pydantic import BaseModel
from app.database import get_db
from app.models import DetectionResponse
from app.repositories.detection_repository import DetectionRepository

router = APIRouter()


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
