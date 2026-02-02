from pydantic import BaseModel
from datetime import datetime

class Detection(BaseModel):
    id: int | None = None
    detection_time: datetime
    detection_index: int
    score: float
    display_name: str
    category_name: str
    frigate_event: str
    camera_name: str
    is_hidden: bool = False
    frigate_score: float | None = None
    sub_label: str | None = None
    manual_tagged: bool = False
    # Audio correlation fields
    audio_confirmed: bool = False
    audio_species: str | None = None
    audio_score: float | None = None
    # Weather fields
    temperature: float | None = None
    weather_condition: str | None = None
    weather_cloud_cover: float | None = None
    weather_wind_speed: float | None = None
    weather_wind_direction: float | None = None
    weather_precipitation: float | None = None
    weather_rain: float | None = None
    weather_snowfall: float | None = None
    # Taxonomy fields
    scientific_name: str | None = None
    common_name: str | None = None
    taxa_id: int | None = None
    # Video classification fields
    video_classification_score: float | None = None
    video_classification_label: str | None = None
    video_classification_timestamp: datetime | None = None
    video_classification_status: str | None = None
    video_classification_error: str | None = None
    # AI naturalist analysis fields
    ai_analysis: str | None = None
    ai_analysis_timestamp: datetime | None = None

class DetectionResponse(Detection):
    has_clip: bool = False  # Clip availability from Frigate

class FrigateEvent(BaseModel):
    id: str
    camera: str
    label: str
    start_time: float
    top_score: float | None = None
    false_positive: bool | None = None

# Species detail models
class CameraStats(BaseModel):
    camera_name: str
    count: int
    percentage: float

class SpeciesStats(BaseModel):
    species_name: str
    scientific_name: str | None = None
    common_name: str | None = None
    total_sightings: int
    first_seen: datetime | None
    last_seen: datetime | None
    cameras: list[CameraStats]
    hourly_distribution: list[int]  # 24 elements (0-23 hours)
    daily_distribution: list[int]   # 7 elements (0=Sunday, 6=Saturday)
    monthly_distribution: list[int] # 12 elements (1-12 months)
    avg_confidence: float
    max_confidence: float
    min_confidence: float
    recent_sightings: list[Detection]

class SpeciesInfo(BaseModel):
    title: str
    description: str | None = None
    extract: str | None = None
    thumbnail_url: str | None = None
    wikipedia_url: str | None = None
    source: str | None = None
    source_url: str | None = None
    summary_source: str | None = None
    summary_source_url: str | None = None
    scientific_name: str | None = None
    conservation_status: str | None = None
    taxa_id: int | None = None
    cached_at: datetime | None = None
