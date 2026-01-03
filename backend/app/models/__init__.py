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
    # Audio correlation fields
    audio_confirmed: bool = False
    audio_species: str | None = None
    audio_score: float | None = None
    # Weather fields
    temperature: float | None = None
    weather_condition: str | None = None
    # Taxonomy fields
    scientific_name: str | None = None
    common_name: str | None = None
    taxa_id: int | None = None

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
    scientific_name: str | None = None
    conservation_status: str | None = None
    cached_at: datetime | None = None
