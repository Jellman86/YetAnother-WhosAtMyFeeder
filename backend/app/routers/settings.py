import platform
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
import structlog

from app.config import settings
from app.auth import require_owner, AuthContext
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository

from app.services.taxonomy.taxonomy_service import taxonomy_service
from app.services.telemetry_service import telemetry_service
from app.services.notification_service import notification_service
from app.services.auto_video_classifier_service import auto_video_classifier
from app.services.birdweather_service import birdweather_service

from fastapi import BackgroundTasks

router = APIRouter()
log = structlog.get_logger()

@router.get("/maintenance/taxonomy/status")
async def get_taxonomy_status(auth: AuthContext = Depends(require_owner)):
    """Get status of the taxonomy synchronization process. Owner only."""
    return taxonomy_service.get_sync_status()

@router.post("/maintenance/taxonomy/sync")
async def start_taxonomy_sync(
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_owner)
):
    """Start the background process to normalize all detection names. Owner only."""
    status = taxonomy_service.get_sync_status()
    if status["is_running"]:
        return {"status": "already_running"}

    background_tasks.add_task(taxonomy_service.run_background_sync)
    return {"status": "started"}

@router.post("/settings/birdnet/test")
async def test_birdnet(
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_owner)
):
    """Test BirdNET-Go integration by injecting a mock detection. Owner only."""
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
async def test_mqtt_publish(auth: AuthContext = Depends(require_owner)):
    """Publish a test message to the MQTT broker to verify connectivity. Owner only."""
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

class NotificationTestRequest(BaseModel):
    platform: str  # discord, pushover, telegram
    # Optional overrides for testing uncommitted settings
    webhook_url: Optional[str] = None
    user_key: Optional[str] = None
    api_token: Optional[str] = None
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None

@router.post("/settings/notifications/test")
async def test_notification(
    request: NotificationTestRequest,
    auth: AuthContext = Depends(require_owner)
):
    """Test notification platform with optional credential overrides. Owner only."""
    
    # Create mock detection data
    species = "Cyanistes caeruleus"
    common_name = "Eurasian Blue Tit (Test)"
    confidence = 0.95
    camera = "test_camera"
    timestamp = datetime.now()
    snapshot_url = "https://placehold.co/600x400.jpg"
    
    try:
        if request.platform == "discord":
            # Temporarily override settings if provided
            original_url = settings.notifications.discord.webhook_url
            if request.webhook_url and request.webhook_url != "***REDACTED***":
                settings.notifications.discord.webhook_url = request.webhook_url
            
            try:
                await notification_service._send_discord(
                    common_name,
                    confidence,
                    camera,
                    timestamp,
                    snapshot_url,
                    True,
                    settings.notifications.notification_language,
                    None
                )
            finally:
                if request.webhook_url and request.webhook_url != "***REDACTED***":
                    settings.notifications.discord.webhook_url = original_url
                    
        elif request.platform == "pushover":
            orig_user = settings.notifications.pushover.user_key
            orig_token = settings.notifications.pushover.api_token
            
            if request.user_key and request.user_key != "***REDACTED***": 
                settings.notifications.pushover.user_key = request.user_key
            if request.api_token and request.api_token != "***REDACTED***": 
                settings.notifications.pushover.api_token = request.api_token
            
            try:
                await notification_service._send_pushover(
                    species, common_name, confidence, camera, timestamp, snapshot_url, None
                )
            finally:
                if request.user_key and request.user_key != "***REDACTED***": 
                    settings.notifications.pushover.user_key = orig_user
                if request.api_token and request.api_token != "***REDACTED***": 
                    settings.notifications.pushover.api_token = orig_token

        elif request.platform == "telegram":
            orig_bot = settings.notifications.telegram.bot_token
            orig_chat = settings.notifications.telegram.chat_id
            
            if request.bot_token and request.bot_token != "***REDACTED***": 
                settings.notifications.telegram.bot_token = request.bot_token
            if request.chat_id and request.chat_id != "***REDACTED***": 
                settings.notifications.telegram.chat_id = request.chat_id
            
            try:
                await notification_service._send_telegram(
                    species, common_name, confidence, camera, timestamp, snapshot_url, None
                )
            finally:
                if request.bot_token and request.bot_token != "***REDACTED***": 
                    settings.notifications.telegram.bot_token = orig_bot
                if request.chat_id and request.chat_id != "***REDACTED***": 
                    settings.notifications.telegram.chat_id = orig_chat
        
        else:
            return {"status": "error", "message": f"Unknown platform: {request.platform}"}

        return {"status": "ok", "message": f"Test notification sent to {request.platform}"}
    except Exception as e:
        log.error("Notification test failed", error=str(e))
        return {"status": "error", "message": str(e)}


class BirdWeatherTestRequest(BaseModel):
    token: Optional[str] = None


@router.post("/settings/birdweather/test")
async def test_birdweather(
    request: BirdWeatherTestRequest,
    auth: AuthContext = Depends(require_owner)
):
    """Test BirdWeather integration with an optional token override. Owner only."""
    token = request.token if request.token and request.token != "***REDACTED***" else None
    if not token and not settings.birdweather.station_token:
        return {"status": "error", "message": "Missing BirdWeather station token"}
    if token is None and not settings.birdweather.enabled:
        return {"status": "error", "message": "BirdWeather is disabled"}

    success = await birdweather_service.report_detection(
        scientific_name="Cyanistes caeruleus",
        common_name="Eurasian Blue Tit (Test)",
        confidence=0.95,
        timestamp=datetime.now(),
        token=token
    )

    if success:
        return {"status": "ok", "message": "BirdWeather test succeeded"}
    return {"status": "error", "message": "BirdWeather test failed. Check token and station permissions."}

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
    audio_buffer_hours: int = Field(24, ge=1, le=168, description="Hours to keep audio detections in buffer for correlation (1-168)")
    audio_correlation_window_seconds: int = Field(300, ge=5, le=3600, description="Time window in seconds for audio-visual correlation (±N seconds from detection)")
    clips_enabled: bool = Field(True, description="Enable fetching of video clips from Frigate")
    classification_threshold: float = Field(..., ge=0.0, le=1.0, description="Classification confidence threshold (0-1)")
    classification_min_confidence: float = Field(0.4, ge=0.0, le=1.0, description="Minimum confidence floor (0-1)")
    cameras: List[str] = Field(default_factory=list, description="List of cameras to monitor")
    retention_days: int = Field(0, ge=0, description="Days to keep detections (0 = unlimited)")
    blocked_labels: List[str] = Field(default_factory=list, description="Labels to filter out from detections")
    trust_frigate_sublabel: bool = Field(True, description="Trust Frigate sublabels when available")
    display_common_names: bool = Field(True, description="Display common names instead of scientific")
    scientific_name_primary: bool = Field(False, description="Show scientific name as the primary label in UI")
    # Auto Video Classification
    auto_video_classification: Optional[bool] = Field(False, description="Automatically classify video clips")
    video_classification_delay: Optional[int] = Field(30, ge=0, description="Seconds to wait before checking for clip")
    video_classification_max_retries: Optional[int] = Field(3, ge=0, description="Max retries for clip availability")
    # Media cache settings
    media_cache_enabled: bool = Field(True, description="Enable local media caching")
    media_cache_snapshots: bool = Field(True, description="Cache snapshot images locally")
    media_cache_clips: bool = Field(False, description="Cache video clips locally (may cause initial playback delay)")
    media_cache_retention_days: int = Field(0, ge=0, description="Days to keep cached media (0 = follow detection)")
    # Location settings
    location_latitude: Optional[float] = Field(None, description="Latitude")
    location_longitude: Optional[float] = Field(None, description="Longitude")
    location_automatic: Optional[bool] = Field(True, description="Auto-detect location")
    location_temperature_unit: Optional[str] = Field("celsius", description="Temperature unit: 'celsius' or 'fahrenheit'")
    # BirdWeather settings
    birdweather_enabled: Optional[bool] = Field(False, description="Enable BirdWeather reporting")
    birdweather_station_token: Optional[str] = Field(None, description="BirdWeather Station Token")
    # LLM settings
    llm_enabled: Optional[bool] = Field(False, description="Enable AI behavior analysis")
    llm_provider: Optional[str] = Field("gemini", description="AI provider")
    llm_api_key: Optional[str] = Field(None, description="API key")
    llm_model: Optional[str] = Field("gemini-2.0-flash-exp", description="AI model")
    
    # Telemetry
    telemetry_enabled: Optional[bool] = Field(False, description="Enable anonymous usage statistics")

    # Notifications
    notifications_discord_enabled: Optional[bool] = False
    notifications_discord_webhook_url: Optional[str] = None
    notifications_discord_username: Optional[str] = "YA-WAMF"
    
    notifications_pushover_enabled: Optional[bool] = False
    notifications_pushover_user_key: Optional[str] = None
    notifications_pushover_api_token: Optional[str] = None
    notifications_pushover_priority: Optional[int] = 0
    
    notifications_telegram_enabled: Optional[bool] = False
    notifications_telegram_bot_token: Optional[str] = None
    notifications_telegram_chat_id: Optional[str] = None

    notifications_email_enabled: Optional[bool] = False
    notifications_email_use_oauth: Optional[bool] = False
    notifications_email_oauth_provider: Optional[str] = None
    notifications_email_gmail_client_id: Optional[str] = None
    notifications_email_gmail_client_secret: Optional[str] = None
    notifications_email_outlook_client_id: Optional[str] = None
    notifications_email_outlook_client_secret: Optional[str] = None
    notifications_email_smtp_host: Optional[str] = None
    notifications_email_smtp_port: Optional[int] = 587
    notifications_email_smtp_username: Optional[str] = None
    notifications_email_smtp_password: Optional[str] = None
    notifications_email_smtp_use_tls: Optional[bool] = True
    notifications_email_from_email: Optional[str] = None
    notifications_email_to_email: Optional[str] = None
    notifications_email_include_snapshot: Optional[bool] = True
    notifications_email_dashboard_url: Optional[str] = None
    
    notifications_filter_species_whitelist: Optional[List[str]] = []
    notifications_filter_min_confidence: Optional[float] = 0.7
    notifications_filter_audio_confirmed_only: Optional[bool] = False
    notification_language: Optional[str] = "en"
    notifications_notify_on_insert: Optional[bool] = True
    notifications_notify_on_update: Optional[bool] = False
    notifications_delay_until_video: Optional[bool] = False
    notifications_video_fallback_timeout: Optional[int] = 45

    # Accessibility
    accessibility_high_contrast: Optional[bool] = False
    accessibility_dyslexia_font: Optional[bool] = False
    accessibility_reduced_motion: Optional[bool] = False
    accessibility_zen_mode: Optional[bool] = False
    accessibility_live_announcements: Optional[bool] = True

    species_info_source: Optional[str] = "auto"

    @field_validator('location_temperature_unit')
    @classmethod
    def validate_location_temperature_unit(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        normalized = v.strip().lower()
        if normalized not in ("celsius", "fahrenheit"):
            raise ValueError("location_temperature_unit must be 'celsius' or 'fahrenheit'")
        return normalized

    @field_validator('frigate_url')
    @classmethod
    def validate_frigate_url(cls, v: str) -> str:
        if not v.startswith(('http://', 'https://')):
            raise ValueError('frigate_url must start with http:// or https://')
        return v.rstrip('/')

@router.get("/settings")
async def get_settings(auth: AuthContext = Depends(require_owner)):
    """
    Get application settings with secrets redacted. Owner only.
    Secrets are never returned via API for security reasons.
    """
    from app.services.smtp_service import smtp_service

    oauth_status = await smtp_service.get_oauth_status(settings.notifications.email.oauth_provider)
    if not oauth_status:
        oauth_status = await smtp_service.get_oauth_status()
    connected_email = oauth_status["email"] if oauth_status else None
    connected_provider = oauth_status["provider"] if oauth_status else settings.notifications.email.oauth_provider

    circuit_status = auto_video_classifier.get_circuit_status()
    return {
        "frigate_url": settings.frigate.frigate_url,
        "mqtt_server": settings.frigate.mqtt_server,
        "mqtt_port": settings.frigate.mqtt_port,
        "mqtt_auth": settings.frigate.mqtt_auth,
        "mqtt_username": settings.frigate.mqtt_username,
        # SECURITY: Never expose passwords via API
        "mqtt_password": "***REDACTED***" if settings.frigate.mqtt_password else None,
        "birdnet_enabled": settings.frigate.birdnet_enabled,
        "audio_topic": settings.frigate.audio_topic,
        "camera_audio_mapping": settings.frigate.camera_audio_mapping,
        "audio_buffer_hours": settings.frigate.audio_buffer_hours,
        "audio_correlation_window_seconds": settings.frigate.audio_correlation_window_seconds,
        "clips_enabled": settings.frigate.clips_enabled,
        "classification_threshold": settings.classification.threshold,
        "classification_min_confidence": settings.classification.min_confidence,
        "cameras": settings.frigate.camera,
        "retention_days": settings.maintenance.retention_days,
        "blocked_labels": settings.classification.blocked_labels,
        "trust_frigate_sublabel": settings.classification.trust_frigate_sublabel,
        "display_common_names": settings.classification.display_common_names,
        "scientific_name_primary": settings.classification.scientific_name_primary,
        "auto_video_classification": settings.classification.auto_video_classification,
        "video_classification_delay": settings.classification.video_classification_delay,
        "video_classification_max_retries": settings.classification.video_classification_max_retries,
        "video_classification_circuit_open": circuit_status.get("open", False),
        "video_classification_circuit_until": circuit_status.get("open_until"),
        "video_classification_circuit_failures": circuit_status.get("failure_count", 0),
        # Media cache settings
        "media_cache_enabled": settings.media_cache.enabled,
        "media_cache_snapshots": settings.media_cache.cache_snapshots,
        "media_cache_clips": settings.media_cache.cache_clips,
        "media_cache_retention_days": settings.media_cache.retention_days,
        # Location settings
        "location_latitude": settings.location.latitude,
        "location_longitude": settings.location.longitude,
        "location_automatic": settings.location.automatic,
        "location_temperature_unit": settings.location.temperature_unit,
        # BirdWeather settings
        "birdweather_enabled": settings.birdweather.enabled,
        # SECURITY: Never expose station tokens via API
        "birdweather_station_token": "***REDACTED***" if settings.birdweather.station_token else None,
        # LLM settings
        "llm_enabled": settings.llm.enabled,
        "llm_provider": settings.llm.provider,
        # SECURITY: Never expose API keys via API
        "llm_api_key": "***REDACTED***" if settings.llm.api_key else None,
        "llm_model": settings.llm.model,
        # Telemetry
        "telemetry_enabled": settings.telemetry.enabled,
        "telemetry_installation_id": settings.telemetry.installation_id,
        "telemetry_platform": f"{platform.system()} {platform.machine()}",

        # Notifications
        "notifications_discord_enabled": settings.notifications.discord.enabled,
        "notifications_discord_webhook_url": "***REDACTED***" if settings.notifications.discord.webhook_url else None,
        "notifications_discord_username": settings.notifications.discord.username,

        "notifications_pushover_enabled": settings.notifications.pushover.enabled,
        "notifications_pushover_user_key": "***REDACTED***" if settings.notifications.pushover.user_key else None,
        "notifications_pushover_api_token": "***REDACTED***" if settings.notifications.pushover.api_token else None,
        "notifications_pushover_priority": settings.notifications.pushover.priority,

        "notifications_telegram_enabled": settings.notifications.telegram.enabled,
        "notifications_telegram_bot_token": "***REDACTED***" if settings.notifications.telegram.bot_token else None,
        "notifications_telegram_chat_id": "***REDACTED***" if settings.notifications.telegram.chat_id else None,

        "notifications_email_enabled": settings.notifications.email.enabled,
        "notifications_email_use_oauth": settings.notifications.email.use_oauth,
        "notifications_email_oauth_provider": connected_provider,
        "notifications_email_connected_email": connected_email,
        "notifications_email_gmail_client_id": settings.notifications.email.gmail_client_id,
        "notifications_email_gmail_client_secret": "***REDACTED***" if settings.notifications.email.gmail_client_secret else None,
        "notifications_email_outlook_client_id": settings.notifications.email.outlook_client_id,
        "notifications_email_outlook_client_secret": "***REDACTED***" if settings.notifications.email.outlook_client_secret else None,
        "notifications_email_smtp_host": settings.notifications.email.smtp_host,
        "notifications_email_smtp_port": settings.notifications.email.smtp_port,
        "notifications_email_smtp_username": settings.notifications.email.smtp_username,
        "notifications_email_smtp_password": "***REDACTED***" if settings.notifications.email.smtp_password else None,
        "notifications_email_smtp_use_tls": settings.notifications.email.smtp_use_tls,
        "notifications_email_from_email": settings.notifications.email.from_email,
        "notifications_email_to_email": settings.notifications.email.to_email,
        "notifications_email_include_snapshot": settings.notifications.email.include_snapshot,
        "notifications_email_dashboard_url": settings.notifications.email.dashboard_url,

        "notifications_filter_species_whitelist": settings.notifications.filters.species_whitelist,
        "notifications_filter_min_confidence": settings.notifications.filters.min_confidence,
        "notifications_filter_audio_confirmed_only": settings.notifications.filters.audio_confirmed_only,
        "notification_language": settings.notifications.notification_language,
        "notifications_notify_on_insert": settings.notifications.notify_on_insert,
        "notifications_notify_on_update": settings.notifications.notify_on_update,
        "notifications_delay_until_video": settings.notifications.delay_until_video,
        "notifications_video_fallback_timeout": settings.notifications.video_fallback_timeout,

        # Accessibility
        "accessibility_high_contrast": settings.accessibility.high_contrast,
        "accessibility_dyslexia_font": settings.accessibility.dyslexia_font,
        "accessibility_reduced_motion": settings.accessibility.reduced_motion,
        "accessibility_zen_mode": settings.accessibility.zen_mode,
        "accessibility_live_announcements": settings.accessibility.live_announcements,
        "species_info_source": settings.species_info_source,
    }

@router.post("/settings")
async def update_settings(
    update: SettingsUpdate,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_owner)
):
    """Update application settings. Owner only."""
    settings.frigate.frigate_url = update.frigate_url
    settings.frigate.mqtt_server = update.mqtt_server
    settings.frigate.mqtt_port = update.mqtt_port
    settings.frigate.mqtt_auth = update.mqtt_auth
    if update.mqtt_username is not None:
        settings.frigate.mqtt_username = update.mqtt_username
    # Only update password if it's not the redacted placeholder
    if update.mqtt_password and update.mqtt_password != "***REDACTED***":
        settings.frigate.mqtt_password = update.mqtt_password
    settings.frigate.birdnet_enabled = update.birdnet_enabled if update.birdnet_enabled is not None else True
    settings.frigate.audio_topic = update.audio_topic
    settings.frigate.camera_audio_mapping = update.camera_audio_mapping
    settings.frigate.audio_buffer_hours = update.audio_buffer_hours
    settings.frigate.audio_correlation_window_seconds = update.audio_correlation_window_seconds

    settings.frigate.clips_enabled = update.clips_enabled
    settings.frigate.camera = update.cameras
    settings.classification.threshold = update.classification_threshold
    settings.classification.min_confidence = update.classification_min_confidence
    settings.maintenance.retention_days = update.retention_days
    settings.classification.blocked_labels = update.blocked_labels
    settings.classification.trust_frigate_sublabel = update.trust_frigate_sublabel
    settings.classification.display_common_names = update.display_common_names
    settings.classification.scientific_name_primary = update.scientific_name_primary
    
    if update.auto_video_classification is not None:
        settings.classification.auto_video_classification = update.auto_video_classification
    if update.video_classification_delay is not None:
        settings.classification.video_classification_delay = update.video_classification_delay
    if update.video_classification_max_retries is not None:
        settings.classification.video_classification_max_retries = update.video_classification_max_retries

    # Media cache settings
    settings.media_cache.enabled = update.media_cache_enabled
    settings.media_cache.cache_snapshots = update.media_cache_snapshots
    settings.media_cache.cache_clips = update.media_cache_clips
    settings.media_cache.retention_days = update.media_cache_retention_days
    
    # Location settings
    settings.location.latitude = update.location_latitude
    settings.location.longitude = update.location_longitude
    settings.location.automatic = update.location_automatic if update.location_automatic is not None else True
    if update.location_temperature_unit is not None:
        settings.location.temperature_unit = update.location_temperature_unit

    # BirdWeather settings
    settings.birdweather.enabled = update.birdweather_enabled if update.birdweather_enabled is not None else False
    # Only update token if it's not the redacted placeholder
    if update.birdweather_station_token and update.birdweather_station_token != "***REDACTED***":
        settings.birdweather.station_token = update.birdweather_station_token

    # LLM settings
    settings.llm.enabled = update.llm_enabled if update.llm_enabled is not None else False
    settings.llm.provider = update.llm_provider if update.llm_provider else "gemini"
    # Only update API key if it's not the redacted placeholder
    if update.llm_api_key and update.llm_api_key != "***REDACTED***":
        settings.llm.api_key = update.llm_api_key
    settings.llm.model = update.llm_model if update.llm_model else "gemini-2.0-flash-exp"
    
    # Telemetry
    settings.telemetry.enabled = update.telemetry_enabled if update.telemetry_enabled is not None else True

    # Notifications - Discord
    if update.notifications_discord_enabled is not None:
        settings.notifications.discord.enabled = update.notifications_discord_enabled
    # Only update webhook URL if it's not the redacted placeholder
    if update.notifications_discord_webhook_url and update.notifications_discord_webhook_url != "***REDACTED***":
        settings.notifications.discord.webhook_url = update.notifications_discord_webhook_url
    if update.notifications_discord_username:
        settings.notifications.discord.username = update.notifications_discord_username

    # Notifications - Pushover
    if update.notifications_pushover_enabled is not None:
        settings.notifications.pushover.enabled = update.notifications_pushover_enabled
    # Only update keys/tokens if they're not the redacted placeholder
    if update.notifications_pushover_user_key and update.notifications_pushover_user_key != "***REDACTED***":
        settings.notifications.pushover.user_key = update.notifications_pushover_user_key
    if update.notifications_pushover_api_token and update.notifications_pushover_api_token != "***REDACTED***":
        settings.notifications.pushover.api_token = update.notifications_pushover_api_token
    if update.notifications_pushover_priority is not None:
        settings.notifications.pushover.priority = update.notifications_pushover_priority

    # Notifications - Telegram
    if update.notifications_telegram_enabled is not None:
        settings.notifications.telegram.enabled = update.notifications_telegram_enabled
    # Only update bot token if it's not the redacted placeholder
    if update.notifications_telegram_bot_token and update.notifications_telegram_bot_token != "***REDACTED***":
        settings.notifications.telegram.bot_token = update.notifications_telegram_bot_token
    # Only update chat ID if it's not the redacted placeholder
    if update.notifications_telegram_chat_id and update.notifications_telegram_chat_id != "***REDACTED***":
        settings.notifications.telegram.chat_id = update.notifications_telegram_chat_id

    # Notifications - Email
    if update.notifications_email_enabled is not None:
        settings.notifications.email.enabled = update.notifications_email_enabled
    if update.notifications_email_use_oauth is not None:
        settings.notifications.email.use_oauth = update.notifications_email_use_oauth
    if update.notifications_email_oauth_provider is not None:
        settings.notifications.email.oauth_provider = update.notifications_email_oauth_provider
    if update.notifications_email_gmail_client_id is not None:
        settings.notifications.email.gmail_client_id = update.notifications_email_gmail_client_id
    if update.notifications_email_gmail_client_secret and update.notifications_email_gmail_client_secret != "***REDACTED***":
        settings.notifications.email.gmail_client_secret = update.notifications_email_gmail_client_secret
    if update.notifications_email_outlook_client_id is not None:
        settings.notifications.email.outlook_client_id = update.notifications_email_outlook_client_id
    if update.notifications_email_outlook_client_secret and update.notifications_email_outlook_client_secret != "***REDACTED***":
        settings.notifications.email.outlook_client_secret = update.notifications_email_outlook_client_secret
    if update.notifications_email_smtp_host is not None:
        settings.notifications.email.smtp_host = update.notifications_email_smtp_host
    if update.notifications_email_smtp_port is not None:
        settings.notifications.email.smtp_port = update.notifications_email_smtp_port
    if update.notifications_email_smtp_username is not None:
        settings.notifications.email.smtp_username = update.notifications_email_smtp_username
    if update.notifications_email_smtp_password and update.notifications_email_smtp_password != "***REDACTED***":
        settings.notifications.email.smtp_password = update.notifications_email_smtp_password
    if update.notifications_email_smtp_use_tls is not None:
        settings.notifications.email.smtp_use_tls = update.notifications_email_smtp_use_tls
    if update.notifications_email_from_email is not None:
        settings.notifications.email.from_email = update.notifications_email_from_email
    if update.notifications_email_to_email is not None:
        settings.notifications.email.to_email = update.notifications_email_to_email
    if update.notifications_email_include_snapshot is not None:
        settings.notifications.email.include_snapshot = update.notifications_email_include_snapshot
    if update.notifications_email_dashboard_url is not None:
        settings.notifications.email.dashboard_url = update.notifications_email_dashboard_url
    
    # Notifications - Filters
    if update.notifications_filter_species_whitelist is not None:
        settings.notifications.filters.species_whitelist = update.notifications_filter_species_whitelist
    if update.notifications_filter_min_confidence is not None:
        settings.notifications.filters.min_confidence = update.notifications_filter_min_confidence
    if update.notifications_filter_audio_confirmed_only is not None:
        settings.notifications.filters.audio_confirmed_only = update.notifications_filter_audio_confirmed_only

    if update.notification_language:
        settings.notifications.notification_language = update.notification_language

    if update.notifications_notify_on_insert is not None:
        settings.notifications.notify_on_insert = update.notifications_notify_on_insert
    if update.notifications_notify_on_update is not None:
        settings.notifications.notify_on_update = update.notifications_notify_on_update
    if update.notifications_delay_until_video is not None:
        settings.notifications.delay_until_video = update.notifications_delay_until_video
    if update.notifications_video_fallback_timeout is not None:
        settings.notifications.video_fallback_timeout = update.notifications_video_fallback_timeout

    # Accessibility
    if update.accessibility_high_contrast is not None:
        settings.accessibility.high_contrast = update.accessibility_high_contrast
    if update.accessibility_dyslexia_font is not None:
        settings.accessibility.dyslexia_font = update.accessibility_dyslexia_font
    if update.accessibility_reduced_motion is not None:
        settings.accessibility.reduced_motion = update.accessibility_reduced_motion
    if update.accessibility_zen_mode is not None:
        settings.accessibility.zen_mode = update.accessibility_zen_mode
    if update.accessibility_live_announcements is not None:
        settings.accessibility.live_announcements = update.accessibility_live_announcements

    if update.species_info_source:
        settings.species_info_source = update.species_info_source

    if settings.telemetry.enabled:
        background_tasks.add_task(telemetry_service.force_heartbeat)

    await settings.save()
    return {"status": "updated"}

@router.get("/maintenance/stats")
async def get_maintenance_stats(auth: AuthContext = Depends(require_owner)):
    """Get database maintenance statistics. Owner only."""
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
async def run_cleanup(auth: AuthContext = Depends(require_owner)):
    """Manually trigger cleanup of old detections. Owner only."""
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
async def get_cache_stats(auth: AuthContext = Depends(require_owner)):
    """Get media cache statistics. Owner only."""
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
async def run_cache_cleanup(auth: AuthContext = Depends(require_owner)):
    """Manually trigger cleanup of old cached media. Owner only."""
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
