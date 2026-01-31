from fastapi import APIRouter, Request, Depends
from datetime import datetime, time, date, timedelta
from typing import List, Optional
from collections import Counter
from pydantic import BaseModel

from app.database import get_db
from app.repositories.detection_repository import DetectionRepository
from app.models import DetectionResponse
from app.config import settings
from app.services.taxonomy.taxonomy_service import taxonomy_service
from app.services.weather_service import weather_service
from app.auth import AuthContext
from app.auth_legacy import get_auth_context_with_legacy
from app.ratelimit import guest_rate_limit

router = APIRouter()

class DailySpeciesSummary(BaseModel):
    species: str
    count: int
    latest_event: str # Used for thumbnail
    scientific_name: str | None = None
    common_name: str | None = None
    taxa_id: int | None = None

class DailySummaryResponse(BaseModel):
    hourly_distribution: List[int]
    top_species: List[DailySpeciesSummary]
    latest_detection: Optional[DetectionResponse]
    total_count: int
    audio_confirmations: int

class DailyCount(BaseModel):
    date: str
    count: int

class DailyWeatherSummary(BaseModel):
    date: str
    condition: Optional[str] = None
    precip_total: Optional[float] = None
    rain_total: Optional[float] = None
    snow_total: Optional[float] = None
    wind_max: Optional[float] = None
    cloud_avg: Optional[float] = None
    am_condition: Optional[str] = None
    am_rain: Optional[float] = None
    am_snow: Optional[float] = None
    am_wind: Optional[float] = None
    am_cloud: Optional[float] = None
    pm_condition: Optional[str] = None
    pm_rain: Optional[float] = None
    pm_snow: Optional[float] = None
    pm_wind: Optional[float] = None
    pm_cloud: Optional[float] = None

class DetectionsTimelineResponse(BaseModel):
    days: int
    total_count: int
    daily: List[DailyCount]
    weather: Optional[List[DailyWeatherSummary]] = None

@router.get("/stats/daily-summary", response_model=DailySummaryResponse)
@guest_rate_limit()
async def get_daily_summary(
    request: Request,
    auth: AuthContext = Depends(get_auth_context_with_legacy)
):
    """Get a summary of detections for today."""
    lang = getattr(request.state, 'language', 'en')
    hide_camera_names = (
        not auth.is_owner
        and settings.public_access.enabled
        and not settings.public_access.show_camera_names
    )
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(hours=24)
    
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
                common_name = s.get("common_name")
                taxa_id = s.get("taxa_id")
                if lang != 'en' and taxa_id:
                    localized = await taxonomy_service.get_localized_common_name(taxa_id, lang, db=db)
                    if localized:
                        common_name = localized

                summary_species.append(DailySpeciesSummary(
                    species=s["species"],
                    count=s["count"],
                    latest_event=s["latest_event"],
                    scientific_name=s.get("scientific_name"),
                    common_name=common_name,
                    taxa_id=taxa_id
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
        latest_raw = await repo.get_all(limit=1, start_date=start_dt, end_date=end_dt)
        latest_detection = None
        if latest_raw:
            d = latest_raw[0]
            display_name = d.display_name
            if display_name in unknown_labels:
                display_name = "Unknown Bird"
            
            common_name = d.common_name
            if lang != 'en' and d.taxa_id:
                localized = await taxonomy_service.get_localized_common_name(d.taxa_id, lang, db=db)
                if localized:
                    common_name = localized
                
            latest_detection = DetectionResponse(
                id=d.id,
                detection_time=d.detection_time,
                detection_index=d.detection_index,
                score=d.score,
                display_name=display_name,
                category_name=d.category_name,
                frigate_event=d.frigate_event,
                camera_name="Hidden" if hide_camera_names else d.camera_name,
                is_hidden=d.is_hidden,
                frigate_score=d.frigate_score,
                sub_label=d.sub_label,
                manual_tagged=d.manual_tagged,
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
            )
            
        total_today = sum(hourly)
        audio_confirmations = await repo.get_audio_confirmations_count(start_dt, end_dt)
        
        return DailySummaryResponse(
            hourly_distribution=hourly,
            top_species=summary_species,
            latest_detection=latest_detection,
            total_count=total_today,
            audio_confirmations=audio_confirmations
        )

@router.get("/stats/detections/daily", response_model=DetectionsTimelineResponse)
@guest_rate_limit()
async def get_detection_timeline(request: Request, days: int = 30):
    """Get total detections per day for the last N days (inclusive)."""
    if days < 1 or days > 365:
        days = 30

    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.ensure_recent_rollups(max(days, 90))
        daily = await repo.get_total_daily_counts(days=days)
        total = sum(item["count"] for item in daily)
        weather_summary: List[DailyWeatherSummary] = []

        if daily:
            start_date = datetime.strptime(daily[0]["date"], "%Y-%m-%d")
            end_date = datetime.strptime(daily[-1]["date"], "%Y-%m-%d")
            hourly = await weather_service.get_hourly_weather(start_date, end_date)

            if hourly:
                stats: dict[str, dict] = {}
                for time_str, weather in hourly.items():
                    try:
                        dt = datetime.fromisoformat(time_str)
                        date_key = dt.date().isoformat()
                    except ValueError:
                        continue

                    entry = stats.setdefault(date_key, {
                        "precip_total": 0.0,
                        "rain_total": 0.0,
                        "snow_total": 0.0,
                        "wind_max": None,
                        "cloud_sum": 0.0,
                        "cloud_count": 0,
                        "conditions": []
                    })

                    precip = weather.get("precipitation")
                    rain = weather.get("rain")
                    snow = weather.get("snowfall")
                    wind = weather.get("wind_speed")
                    cloud = weather.get("cloud_cover")
                    condition = weather.get("condition_text")

                    if precip is not None:
                        entry["precip_total"] += float(precip)
                    if rain is not None:
                        entry["rain_total"] += float(rain)
                    if snow is not None:
                        entry["snow_total"] += float(snow)
                    if wind is not None:
                        entry["wind_max"] = wind if entry["wind_max"] is None else max(entry["wind_max"], wind)
                    if cloud is not None:
                        entry["cloud_sum"] += float(cloud)
                        entry["cloud_count"] += 1
                    if condition:
                        entry["conditions"].append(condition)

                for item in daily:
                    date_key = item["date"]
                    entry = stats.get(date_key)
                    if not entry:
                        continue
                    conditions = entry["conditions"]
                    condition = Counter(conditions).most_common(1)[0][0] if conditions else None
                    cloud_avg = None
                    if entry["cloud_count"]:
                        cloud_avg = entry["cloud_sum"] / entry["cloud_count"]

                    am_key = f"{date_key}T10:00"
                    pm_key = f"{date_key}T17:00"
                    am_weather = hourly.get(am_key, {})
                    pm_weather = hourly.get(pm_key, {})

                    weather_summary.append(DailyWeatherSummary(
                        date=date_key,
                        condition=condition,
                        precip_total=entry["precip_total"],
                        rain_total=entry["rain_total"],
                        snow_total=entry["snow_total"],
                        wind_max=entry["wind_max"],
                        cloud_avg=cloud_avg,
                        am_condition=am_weather.get("condition_text"),
                        am_rain=am_weather.get("rain"),
                        am_snow=am_weather.get("snowfall"),
                        am_wind=am_weather.get("wind_speed"),
                        am_cloud=am_weather.get("cloud_cover"),
                        pm_condition=pm_weather.get("condition_text"),
                        pm_rain=pm_weather.get("rain"),
                        pm_snow=pm_weather.get("snowfall"),
                        pm_wind=pm_weather.get("wind_speed"),
                        pm_cloud=pm_weather.get("cloud_cover")
                    ))

        return DetectionsTimelineResponse(
            days=days,
            total_count=total,
            daily=[DailyCount(**item) for item in daily],
            weather=weather_summary or None
        )
