from fastapi import APIRouter
from datetime import datetime, time, date
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from app.database import get_db
from app.repositories.detection_repository import DetectionRepository, Detection
from app.models import DetectionResponse
from app.config import settings

router = APIRouter()

class DailySpeciesSummary(BaseModel):
    species: str
    count: int
    latest_event: str # Used for thumbnail
    scientific_name: str | None = None
    common_name: str | None = None

class DailySummaryResponse(BaseModel):
    hourly_distribution: List[int]
    top_species: List[DailySpeciesSummary]
    latest_detection: Optional[DetectionResponse]
    total_count: int

@router.get("/stats/daily-summary", response_model=DailySummaryResponse)
async def get_daily_summary():
    """Get a summary of detections for today."""
    today = date.today()
    start_dt = datetime.combine(today, time.min)
    end_dt = datetime.combine(today, time.max)
    
    async with get_db() as db:
        repo = DetectionRepository(db)
        
        # 1. Hourly distribution
        hourly = await repo.get_global_hourly_distribution(start_dt, end_dt)
        
        # 2. Species counts
        species_raw = await repo.get_daily_species_counts(start_dt, end_dt)
        
        # Transform unknowns
        unknown_labels = settings.classification.unknown_bird_labels
        unknown_count = 0
        latest_unknown_event = None
        
        summary_species = []
        for s in species_raw:
            if s["species"] in unknown_labels:
                unknown_count += s["count"]
                # Keep the absolute latest event ID among unknowns
                if not latest_unknown_event or s["latest_event"] > latest_unknown_event:
                    latest_unknown_event = s["latest_event"]
            else:
                summary_species.append(DailySpeciesSummary(
                    species=s["species"],
                    count=s["count"],
                    latest_event=s["latest_event"],
                    scientific_name=s.get("scientific_name"),
                    common_name=s.get("common_name")
                ))
        
        if unknown_count > 0:
            summary_species.append(DailySpeciesSummary(
                species="Unknown Bird",
                count=unknown_count,
                latest_event=latest_unknown_event
            ))
            # Sort again after aggregation
            summary_species.sort(key=lambda x: x.count, reverse=True)
            
        # 3. Latest detection
        latest_raw = await repo.get_all(limit=1)
        latest_detection = None
        if latest_raw:
            d = latest_raw[0]
            display_name = d.display_name
            if display_name in unknown_labels:
                display_name = "Unknown Bird"
                
            latest_detection = DetectionResponse(
                id=d.id,
                detection_time=d.detection_time,
                detection_index=d.detection_index,
                score=d.score,
                display_name=display_name,
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
                common_name=d.common_name,
                taxa_id=d.taxa_id
            )
            
        total_today = sum(hourly)
        
        return DailySummaryResponse(
            hourly_distribution=hourly,
            top_species=summary_species,
            latest_detection=latest_detection,
            total_count=total_today
        )
