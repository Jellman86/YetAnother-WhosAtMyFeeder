from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator
import structlog

from app.config import settings
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository

from app.services.taxonomy.taxonomy_service import taxonomy_service

from fastapi import BackgroundTasks

router = APIRouter()
log = structlog.get_logger()

@router.get("/maintenance/taxonomy/status")
async def get_taxonomy_status():
    """Get status of the taxonomy synchronization process."""
    return taxonomy_service.get_sync_status()

@router.post("/maintenance/taxonomy/sync")
async def start_taxonomy_sync(background_tasks: BackgroundTasks):
    """Start the background process to normalize all detection names."""
    status = taxonomy_service.get_sync_status()
    if status["is_running"]:
        return {"status": "already_running"}
    
    background_tasks.add_task(taxonomy_service.run_background_sync)
    return {"status": "started"}

@router.post("/settings/birdnet/test")
async def test_birdnet(background_tasks: BackgroundTasks):
    """Test BirdNET-Go integration by injecting a mock detection."""
    from app.services.audio.audio_service import audio_service
    
    mock_data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "species": "Cyanistes caeruleus",
        "common_name": "Eurasian Blue Tit (BirdNET Test)",
        "confidence": 0.95,
        "sensor_id": "test_mic"
    }
    
    # Process it directly through audio service as if it came from MQTT
    background_tasks.add_task(audio_service.add_detection, mock_data)
    
    return {"status": "ok", "message": "Mock audio detection injected. Check Discovery feed for updates."}

@router.post("/settings/mqtt/test-publish")
async def test_mqtt_publish():
    """Publish a test message to the MQTT broker to verify connectivity."""
    from app.services.broadcaster import broadcaster
    # Broadcaster uses the shared mqtt_service internally for non-SSE tasks if needed,
    # but here we should use the mqtt_service directly.
    from app.services.mqtt_service import mqtt_service
    
    try:
        success = await mqtt_service.publish(
            "yawamf/test", 
            {"message": "Hello from YA-WAMF Backend!", "timestamp": datetime.now().isoformat()}
        )
        if success:
            return {"status": "ok", "message": "Test message published to 'yawamf/test'"}
        else:
            return {"status": "error", "message": "Failed to publish MQTT message. Check logs."}
    except Exception as e:
        log.error("MQTT Test Publish Failed", error=str(e))
        return {"status": "error", "message": str(e)}

class BirdWeatherTestRequest(BaseModel):
    token: Optional[str] = None

@router.post("/settings/birdweather/test")
async def test_birdweather(request: BirdWeatherTestRequest = None):
    """Test BirdWeather connectivity and station token."""
    from app.services.birdweather_service import birdweather_service
    
    token = request.token if request else None
    
    # Send a dummy test detection
    success = await birdweather_service.report_detection(
        scientific_name="Passer domesticus",
        common_name="House Sparrow (Test)",
        confidence=1.0,
        timestamp=datetime.now(),
        token=token
    )
    
    if success:
        return {"status": "ok", "message": "Test detection reported successfully"}
    else:
        return {"status": "error", "message": "Failed to report test detection. Check your token and logs."}

class SettingsUpdate(BaseModel):
    frigate_url: str = Field(..., min_length=1, description="Frigate instance URL")
    mqtt_server: str = Field(..., min_length=1, description="MQTT server hostname")
    mqtt_port: int = Field(1883, ge=1, le=65535, description="MQTT server port")
    mqtt_auth: bool = Field(False, description="Enable MQTT authentication")
    mqtt_username: Optional[str] = Field(None, description="MQTT username")
    mqtt_password: Optional[str] = Field(None, description="MQTT password")
    birdnet_enabled: Optional[bool] = Field(True, description="Enable BirdNET-Go integration")
    audio_topic: str = Field("birdnet/text", description="MQTT topic for audio detections")
    camera_audio_mapping: dict[str, str] = Field(default_factory=dict, description="Map Frigate camera to BirdNET ID")
    clips_enabled: bool = Field(True, description="Enable fetching of video clips from Frigate")
    classification_threshold: float = Field(..., ge=0.0, le=1.0, description="Classification confidence threshold (0-1)")
    classification_min_confidence: float = Field(0.4, ge=0.0, le=1.0, description="Minimum confidence floor (0-1)")
    cameras: List[str] = Field(default_factory=list, description="List of cameras to monitor")
    retention_days: int = Field(0, ge=0, description="Days to keep detections (0 = unlimited)")
    blocked_labels: List[str] = Field(default_factory=list, description="Labels to filter out from detections")
    trust_frigate_sublabel: bool = Field(True, description="Trust Frigate sublabels when available")
    display_common_names: bool = Field(True, description="Display common names instead of scientific")
    scientific_name_primary: bool = Field(False, description="Show scientific name as the primary label in UI")
    # Media cache settings
    media_cache_enabled: bool = Field(True, description="Enable local media caching")
    media_cache_snapshots: bool = Field(True, description="Cache snapshot images locally")
    media_cache_clips: bool = Field(False, description="Cache video clips locally (may cause initial playback delay)")
    media_cache_retention_days: int = Field(0, ge=0, description="Days to keep cached media (0 = follow detection)")
    # Location settings
    location_latitude: Optional[float] = Field(None, description="Latitude")
    location_longitude: Optional[float] = Field(None, description="Longitude")
    location_automatic: Optional[bool] = Field(True, description="Auto-detect location")
    # BirdWeather settings
    birdweather_enabled: Optional[bool] = Field(False, description="Enable BirdWeather reporting")
    birdweather_station_token: Optional[str] = Field(None, description="BirdWeather Station Token")
    # LLM settings
    llm_enabled: Optional[bool] = Field(False, description="Enable AI behavior analysis")
    llm_provider: Optional[str] = Field("gemini", description="AI provider")
    llm_api_key: Optional[str] = Field(None, description="API key")
    llm_model: Optional[str] = Field("gemini-1.5-flash", description="AI model")

    @field_validator('frigate_url')
    @classmethod
    def validate_frigate_url(cls, v: str) -> str:
        if not v.startswith(('http://', 'https://')):
            raise ValueError('frigate_url must start with http:// or https://')
        return v.rstrip('/')

@router.get("/settings")
async def get_settings():
    return {
        "frigate_url": settings.frigate.frigate_url,
        "mqtt_server": settings.frigate.mqtt_server,
        "mqtt_port": settings.frigate.mqtt_port,
        "mqtt_auth": settings.frigate.mqtt_auth,
        "mqtt_username": settings.frigate.mqtt_username,
        "mqtt_password": settings.frigate.mqtt_password,
        "birdnet_enabled": settings.frigate.birdnet_enabled,
        "audio_topic": settings.frigate.audio_topic,
        "camera_audio_mapping": settings.frigate.camera_audio_mapping,
        "clips_enabled": settings.frigate.clips_enabled,
        "classification_threshold": settings.classification.threshold,
        "classification_min_confidence": settings.classification.min_confidence,
        "cameras": settings.frigate.camera,
        "retention_days": settings.maintenance.retention_days,
        "blocked_labels": settings.classification.blocked_labels,
        "trust_frigate_sublabel": settings.classification.trust_frigate_sublabel,
        "display_common_names": settings.classification.display_common_names,
        "scientific_name_primary": settings.classification.scientific_name_primary,
        # Media cache settings
        "media_cache_enabled": settings.media_cache.enabled,
        "media_cache_snapshots": settings.media_cache.cache_snapshots,
        "media_cache_clips": settings.media_cache.cache_clips,
        "media_cache_retention_days": settings.media_cache.retention_days,
        # Location settings
        "location_latitude": settings.location.latitude,
        "location_longitude": settings.location.longitude,
        "location_automatic": settings.location.automatic,
        # BirdWeather settings
        "birdweather_enabled": settings.birdweather.enabled,
        "birdweather_station_token": settings.birdweather.station_token,
        # LLM settings
        "llm_enabled": settings.llm.enabled,
        "llm_provider": settings.llm.provider,
        "llm_api_key": settings.llm.api_key,
        "llm_model": settings.llm.model
    }

@router.post("/settings")
async def update_settings(update: SettingsUpdate):
    settings.frigate.frigate_url = update.frigate_url
    settings.frigate.mqtt_server = update.mqtt_server
    settings.frigate.mqtt_port = update.mqtt_port
    settings.frigate.mqtt_auth = update.mqtt_auth
    if update.mqtt_username is not None:
        settings.frigate.mqtt_username = update.mqtt_username
    settings.frigate.mqtt_password = update.mqtt_password
    settings.frigate.birdnet_enabled = update.birdnet_enabled if update.birdnet_enabled is not None else True
    settings.frigate.audio_topic = update.audio_topic
    settings.frigate.camera_audio_mapping = update.camera_audio_mapping

    settings.frigate.clips_enabled = update.clips_enabled
    settings.frigate.camera = update.cameras
    settings.classification.threshold = update.classification_threshold
    settings.classification.min_confidence = update.classification_min_confidence
    settings.maintenance.retention_days = update.retention_days
    settings.classification.blocked_labels = update.blocked_labels
    settings.classification.trust_frigate_sublabel = update.trust_frigate_sublabel
    settings.classification.display_common_names = update.display_common_names
    settings.classification.scientific_name_primary = update.scientific_name_primary

    # Media cache settings
    settings.media_cache.enabled = update.media_cache_enabled
    settings.media_cache.cache_snapshots = update.media_cache_snapshots
    settings.media_cache.cache_clips = update.media_cache_clips
    settings.media_cache.retention_days = update.media_cache_retention_days
    
    # Location settings
    settings.location.latitude = update.location_latitude
    settings.location.longitude = update.location_longitude
    settings.location.automatic = update.location_automatic if update.location_automatic is not None else True

    # BirdWeather settings
    settings.birdweather.enabled = update.birdweather_enabled if update.birdweather_enabled is not None else False
    settings.birdweather.station_token = update.birdweather_station_token

    # LLM settings
    settings.llm.enabled = update.llm_enabled if update.llm_enabled is not None else False
    settings.llm.provider = update.llm_provider if update.llm_provider else "gemini"
    settings.llm.api_key = update.llm_api_key
    settings.llm.model = update.llm_model if update.llm_model else "gemini-1.5-flash"

    settings.save()
    return {"status": "updated"}

@router.get("/maintenance/stats")
async def get_maintenance_stats():
    """Get database maintenance statistics."""
    async with get_db() as db:
        repo = DetectionRepository(db)
        total_count = await repo.get_count()
        oldest_date = await repo.get_oldest_detection_date()

        # Calculate how many would be deleted with current retention
        to_delete = 0
        if settings.maintenance.retention_days > 0:
            cutoff = datetime.now() - timedelta(days=settings.maintenance.retention_days)
            to_delete = await repo.get_count(end_date=cutoff)

        return {
            "total_detections": total_count,
            "oldest_detection": oldest_date.isoformat() if oldest_date else None,
            "retention_days": settings.maintenance.retention_days,
            "detections_to_cleanup": to_delete
        }

@router.post("/maintenance/cleanup")
async def run_cleanup():
    """Manually trigger cleanup of old detections."""
    if settings.maintenance.retention_days <= 0:
        return {
            "status": "skipped",
            "message": "Retention is set to unlimited (0 days)",
            "deleted_count": 0
        }

    cutoff = datetime.now() - timedelta(days=settings.maintenance.retention_days)

    async with get_db() as db:
        repo = DetectionRepository(db)
        deleted_count = await repo.delete_older_than(cutoff)

    log.info("Manual cleanup completed", deleted_count=deleted_count, cutoff=cutoff.isoformat())

    return {
        "status": "completed",
        "deleted_count": deleted_count,
        "cutoff_date": cutoff.isoformat()
    }


# =============================================================================
# Media Cache Endpoints
# =============================================================================

@router.get("/cache/stats")
async def get_cache_stats():
    """Get media cache statistics."""
    from app.services.media_cache import media_cache

    stats = media_cache.get_cache_stats()

    # Add retention info
    retention = settings.media_cache.retention_days
    if retention == 0:
        retention = settings.maintenance.retention_days

    return {
        **stats,
        "cache_enabled": settings.media_cache.enabled,
        "cache_snapshots": settings.media_cache.cache_snapshots,
        "cache_clips": settings.media_cache.cache_clips,
        "retention_days": retention,
        "retention_source": "media_cache" if settings.media_cache.retention_days > 0 else "detection"
    }


@router.post("/cache/cleanup")
async def run_cache_cleanup():
    """Manually trigger cleanup of old cached media."""
    from app.services.media_cache import media_cache

    # Determine retention period
    retention = settings.media_cache.retention_days
    if retention == 0:
        retention = settings.maintenance.retention_days

    # Even if retention is 0, we still run cleanup to remove empty files
    stats = await media_cache.cleanup_old_media(retention)

    # Also run orphaned media cleanup (files not in DB)
    async with get_db() as db:
        # Fetch all valid event IDs
        async with db.execute("SELECT frigate_event FROM detections") as cursor:
            rows = await cursor.fetchall()
            valid_ids = {row[0] for row in rows}
                
    orphan_stats = await media_cache.cleanup_orphaned_media(valid_ids)
        
    # Merge stats
    stats["snapshots_deleted"] += orphan_stats["snapshots_deleted"]
    stats["clips_deleted"] += orphan_stats["clips_deleted"]
    stats["bytes_freed"] += orphan_stats["bytes_freed"]

    return {
        "status": "completed",
        **stats,
        "retention_days": retention
    }