import json
import os
import structlog
from typing import Optional
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, Field

log = structlog.get_logger()

# Use /config directory for persistent config (matches Docker volume mount)
# Allow override via environment variable for testing
CONFIG_PATH = Path(os.getenv("CONFIG_FILE", "/config/config.json"))

class FrigateSettings(BaseModel):
    frigate_url: str = Field(..., description="URL of the Frigate instance")
    frigate_auth_token: Optional[str] = Field(None, description="Optional Bearer token for Frigate proxy auth")
    main_topic: str = "frigate"
    camera: list[str] = Field(default_factory=list, description="List of cameras to monitor")
    clips_enabled: bool = Field(default=True, description="Enable fetching of video clips from Frigate")
    mqtt_server: str = "mqtt"
    mqtt_port: int = 1883
    mqtt_auth: bool = False
    mqtt_username: str = ""
    mqtt_password: str = ""
    birdnet_enabled: bool = Field(default=True, description="Enable BirdNET-Go integration")
    audio_topic: str = "birdnet/text"
    camera_audio_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Map Frigate camera name to BirdNET-Go sensor ID (e.g. {'front_feeder': 'front_mic'})"
    )
    audio_buffer_hours: int = Field(default=24, ge=1, le=168, description="Hours to keep audio detections in buffer for correlation (1-168)")
    audio_correlation_window_seconds: int = Field(default=300, ge=5, le=3600, description="Time window in seconds for audio-visual correlation (±N seconds from detection)")

class ClassificationSettings(BaseModel):
    model: str = "model.tflite"
    threshold: float = 0.7
    min_confidence: float = Field(default=0.4, ge=0.0, le=1.0, description="Minimum confidence floor (reject below this)")
    blocked_labels: list[str] = Field(
        default=[],
        description="Labels to filter out completely (won't be saved)"
    )
    unknown_bird_labels: list[str] = Field(
        default=["background", "Background"],
        description="Labels to relabel as 'Unknown Bird' (unidentifiable detections)"
    )
    trust_frigate_sublabel: bool = Field(
        default=True,
        description="Fall back to Frigate sublabel when YA-WAMF classification fails threshold"
    )
    display_common_names: bool = Field(
        default=True,
        description="Display common names instead of scientific names when available"
    )
    scientific_name_primary: bool = Field(
        default=False,
        description="Show scientific name as the primary label in UI"
    )
    # Auto Video Classification
    auto_video_classification: bool = Field(default=False, description="Automatically classify video clips when available")
    video_classification_delay: int = Field(default=30, description="Seconds to wait before checking for clip (allow Frigate to finalize)")
    video_classification_max_retries: int = Field(default=3, description="Max retries for clip availability")
    video_classification_retry_interval: int = Field(default=15, description="Seconds between retries")
    video_classification_max_concurrent: int = Field(default=5, ge=1, le=20, description="Maximum concurrent video classification tasks")

    # Classification output settings
    max_classification_results: int = Field(default=5, ge=1, le=20, description="Maximum number of top results to return from classifier")

    # Wildlife/general animal model settings
    wildlife_model: str = Field(default="wildlife_model.tflite", description="Wildlife classification model file")
    wildlife_labels: str = Field(default="wildlife_labels.txt", description="Wildlife labels file")

class MaintenanceSettings(BaseModel):
    retention_days: int = Field(default=0, ge=0, description="Days to keep detections (0 = unlimited)")
    cleanup_enabled: bool = Field(default=True, description="Enable automatic cleanup")


class MediaCacheSettings(BaseModel):
    enabled: bool = Field(default=True, description="Enable local media caching")
    cache_snapshots: bool = Field(default=True, description="Cache snapshot images locally")
    cache_clips: bool = Field(default=False, description="Cache video clips locally (may cause initial playback delay)")
    retention_days: int = Field(default=0, ge=0, description="Days to keep cached media (0 = follow detection retention)")

class LocationSettings(BaseModel):
    latitude: Optional[float] = Field(None, description="Latitude for weather/sun data")
    longitude: Optional[float] = Field(None, description="Longitude for weather/sun data")
    automatic: bool = Field(True, description="Attempt to detect location automatically via IP")
    temperature_unit: str = Field(default="celsius", description="Temperature unit: 'celsius' or 'fahrenheit'")

class BirdWeatherSettings(BaseModel):
    enabled: bool = Field(default=False, description="Enable BirdWeather reporting")
    station_token: Optional[str] = Field(None, description="BirdWeather Station Token")

class LLMSettings(BaseModel):
    enabled: bool = Field(default=False, description="Enable LLM integration")
    provider: str = Field(default="gemini", description="AI provider (gemini, openai, claude)")
    api_key: Optional[str] = Field(default=None, description="API Key for the provider")
    model: str = Field(default="gemini-3-flash-preview", description="Model name to use")

class TelemetrySettings(BaseModel):
    enabled: bool = Field(default=False, description="Enable anonymous usage statistics")
    url: Optional[str] = Field(default="https://yawamf-telemetry.ya-wamf.workers.dev/heartbeat", description="Telemetry endpoint URL")
    installation_id: Optional[str] = Field(default=None, description="Unique anonymous installation ID")

class DiscordSettings(BaseModel):
    enabled: bool = Field(default=False, description="Enable Discord notifications")
    webhook_url: Optional[str] = Field(default=None, description="Discord Webhook URL")
    username: str = Field(default="YA-WAMF", description="Username for the bot")
    include_snapshot: bool = Field(default=True, description="Include snapshot image")

class PushoverSettings(BaseModel):
    enabled: bool = Field(default=False, description="Enable Pushover notifications")
    user_key: Optional[str] = Field(default=None, description="Pushover User Key")
    api_token: Optional[str] = Field(default=None, description="Pushover API Token")
    priority: int = Field(default=0, ge=-2, le=2, description="Notification priority (-2 to 2)")
    include_snapshot: bool = Field(default=True, description="Include snapshot image")

class TelegramSettings(BaseModel):
    enabled: bool = Field(default=False, description="Enable Telegram notifications")
    bot_token: Optional[str] = Field(default=None, description="Telegram Bot Token")
    chat_id: Optional[str] = Field(default=None, description="Telegram Chat ID")
    include_snapshot: bool = Field(default=True, description="Include snapshot image")

class EmailSettings(BaseModel):
    enabled: bool = Field(default=False, description="Enable Email notifications")
    # OAuth2 Settings
    use_oauth: bool = Field(default=False, description="Use OAuth2 authentication (Gmail/Outlook)")
    oauth_provider: Optional[str] = Field(default=None, description="OAuth provider: 'gmail' or 'outlook'")
    gmail_client_id: Optional[str] = Field(default=None, description="Gmail OAuth Client ID")
    gmail_client_secret: Optional[str] = Field(default=None, description="Gmail OAuth Client Secret")
    outlook_client_id: Optional[str] = Field(default=None, description="Outlook OAuth Client ID")
    outlook_client_secret: Optional[str] = Field(default=None, description="Outlook OAuth Client Secret")
    # Traditional SMTP Settings
    smtp_host: Optional[str] = Field(default=None, description="SMTP server hostname")
    smtp_port: int = Field(default=587, description="SMTP server port")
    smtp_username: Optional[str] = Field(default=None, description="SMTP username")
    smtp_password: Optional[str] = Field(default=None, description="SMTP password")
    smtp_use_tls: bool = Field(default=True, description="Use TLS for SMTP connection")
    # Email Settings
    from_email: Optional[str] = Field(default=None, description="Sender email address")
    to_email: Optional[str] = Field(default=None, description="Recipient email address")
    include_snapshot: bool = Field(default=True, description="Include bird snapshot image")
    dashboard_url: Optional[str] = Field(default=None, description="Dashboard URL for email links")

class NotificationFilterSettings(BaseModel):
    species_whitelist: list[str] = Field(default=[], description="Only notify for these species (empty = all)")
    min_confidence: float = Field(default=0.7, description="Minimum confidence to trigger notification")
    audio_confirmed_only: bool = Field(default=False, description="Only notify if audio confirmed")
    camera_filters: dict[str, dict] = Field(default={}, description="Per-camera overrides")

class NotificationSettings(BaseModel):
    discord: DiscordSettings = DiscordSettings()
    pushover: PushoverSettings = PushoverSettings()
    telegram: TelegramSettings = TelegramSettings()
    email: EmailSettings = EmailSettings()
    filters: NotificationFilterSettings = NotificationFilterSettings()
    notification_language: str = Field(default="en", description="Language for notifications (en, es, fr, de, ja)")

class AccessibilitySettings(BaseModel):
    high_contrast: bool = Field(default=False, description="Enable high contrast mode")
    dyslexia_font: bool = Field(default=False, description="Enable dyslexia-friendly font")
    reduced_motion: bool = Field(default=False, description="Reduce motion/animations")
    zen_mode: bool = Field(default=False, description="Enable simplified zen mode")
    live_announcements: bool = Field(default=True, description="Enable screen reader live announcements")

class SystemSettings(BaseModel):
    """System-level performance and resource settings"""
    broadcaster_max_queue_size: int = Field(default=100, ge=10, le=1000, description="Maximum SSE message queue size per subscriber")
    broadcaster_max_consecutive_full: int = Field(default=10, ge=1, le=100, description="Remove subscriber after this many consecutive backpressure failures")

class Settings(BaseSettings):
    frigate: FrigateSettings
    classification: ClassificationSettings = ClassificationSettings()
    maintenance: MaintenanceSettings = MaintenanceSettings()
    media_cache: MediaCacheSettings = MediaCacheSettings()
    location: LocationSettings = LocationSettings()
    birdweather: BirdWeatherSettings = BirdWeatherSettings()
    llm: LLMSettings = LLMSettings()
    telemetry: TelemetrySettings = TelemetrySettings()
    notifications: NotificationSettings = NotificationSettings()
    accessibility: AccessibilitySettings = AccessibilitySettings()
    system: SystemSettings = SystemSettings()
    species_info_source: str = Field(default="auto", description="Species info source: auto, inat, or wikipedia")

    # General app settings
    log_level: str = "INFO"
    api_key: Optional[str] = None
    
    model_config = SettingsConfigDict(env_nested_delimiter='__', env_file='.env', extra='ignore')

    async def save(self):
        import aiofiles
        async with aiofiles.open(CONFIG_PATH, 'w') as f:
            await f.write(self.model_dump_json(indent=2))
            
    @classmethod
    def load(cls):
        # API Key
        api_key = os.environ.get('YA_WAMF_API_KEY', None)

        # Build frigate settings from environment variables
        frigate_data = {
            'frigate_url': os.environ.get('FRIGATE__FRIGATE_URL', 'http://frigate:5000'),
            'frigate_auth_token': os.environ.get('FRIGATE__FRIGATE_AUTH_TOKEN', None),
            'main_topic': os.environ.get('FRIGATE__MAIN_TOPIC', 'frigate'),
            'clips_enabled': os.environ.get('FRIGATE__CLIPS_ENABLED', 'true').lower() == 'true',
            'mqtt_server': os.environ.get('FRIGATE__MQTT_SERVER', 'mqtt'),
            'mqtt_port': int(os.environ.get('FRIGATE__MQTT_PORT', '1883')),
            'mqtt_auth': os.environ.get('FRIGATE__MQTT_AUTH', 'false').lower() == 'true',
            'mqtt_username': os.environ.get('FRIGATE__MQTT_USERNAME', ''),
            'mqtt_password': os.environ.get('FRIGATE__MQTT_PASSWORD', ''),
            'birdnet_enabled': os.environ.get('FRIGATE__BIRDNET_ENABLED', 'true').lower() == 'true',
            'audio_topic': os.environ.get('FRIGATE__AUDIO_TOPIC', 'birdnet/text'),
            'camera_audio_mapping': {},
        }

        # Maintenance settings
        maintenance_data = {
            'retention_days': int(os.environ.get('MAINTENANCE__RETENTION_DAYS', '0')),
            'cleanup_enabled': os.environ.get('MAINTENANCE__CLEANUP_ENABLED', 'true').lower() == 'true',
        }

        # Classification settings (loaded from file only, no env vars)
        classification_data = {
            'model': 'model.tflite',
            'threshold': 0.7,
            'min_confidence': 0.4,
            'blocked_labels': [],
            'unknown_bird_labels': ["background", "Background"],
            'trust_frigate_sublabel': True,
            'display_common_names': True,
            'scientific_name_primary': False,
            'auto_video_classification': os.environ.get('CLASSIFICATION__AUTO_VIDEO_CLASSIFICATION', 'false').lower() == 'true',
            'video_classification_delay': int(os.environ.get('CLASSIFICATION__VIDEO_CLASSIFICATION_DELAY', '30')),
            'video_classification_max_retries': int(os.environ.get('CLASSIFICATION__VIDEO_CLASSIFICATION_MAX_RETRIES', '3')),
            'video_classification_retry_interval': int(os.environ.get('CLASSIFICATION__VIDEO_CLASSIFICATION_RETRY_INTERVAL', '15')),
        }

        # Media cache settings
        media_cache_data = {
            'enabled': os.environ.get('MEDIA_CACHE__ENABLED', 'true').lower() == 'true',
            'cache_snapshots': os.environ.get('MEDIA_CACHE__CACHE_SNAPSHOTS', 'true').lower() == 'true',
            'cache_clips': os.environ.get('MEDIA_CACHE__CACHE_CLIPS', 'false').lower() == 'true',  # Disabled by default to avoid blocking
            'retention_days': int(os.environ.get('MEDIA_CACHE__RETENTION_DAYS', '0')),
        }

        # Location settings
        location_data = {
            'latitude': None,
            'longitude': None,
            'automatic': True,
            'temperature_unit': 'celsius'
        }

        # BirdWeather settings
        birdweather_data = {
            'enabled': os.environ.get('BIRDWEATHER__ENABLED', 'false').lower() == 'true',
            'station_token': os.environ.get('BIRDWEATHER__STATION_TOKEN', None),
        }

        # LLM settings
        llm_data = {
            'enabled': os.environ.get('LLM__ENABLED', 'false').lower() == 'true',
                    'provider': os.environ.get('LLM__PROVIDER', 'gemini'),
                    'api_key': os.environ.get('LLM__API_KEY', None),
                    'model': os.environ.get('LLM__MODEL', 'gemini-2.0-flash-exp'),
                }
        
        # Telemetry settings
        telemetry_data = {
            'enabled': os.environ.get('TELEMETRY__ENABLED', 'false').lower() == 'true',
            'url': os.environ.get('TELEMETRY__URL', 'https://yawamf-telemetry.ya-wamf.workers.dev/heartbeat'),
            'installation_id': os.environ.get('TELEMETRY__INSTALLATION_ID', None)
        }

        # Notification settings
        notifications_data = {
            'discord': {
                'enabled': os.environ.get('NOTIFICATIONS__DISCORD__ENABLED', 'false').lower() == 'true',
                'webhook_url': os.environ.get('NOTIFICATIONS__DISCORD__WEBHOOK_URL', None),
                'username': os.environ.get('NOTIFICATIONS__DISCORD__USERNAME', 'YA-WAMF'),
                'include_snapshot': os.environ.get('NOTIFICATIONS__DISCORD__INCLUDE_SNAPSHOT', 'true').lower() == 'true',
            },
            'pushover': {
                'enabled': os.environ.get('NOTIFICATIONS__PUSHOVER__ENABLED', 'false').lower() == 'true',
                'user_key': os.environ.get('NOTIFICATIONS__PUSHOVER__USER_KEY', None),
                'api_token': os.environ.get('NOTIFICATIONS__PUSHOVER__API_TOKEN', None),
                'priority': int(os.environ.get('NOTIFICATIONS__PUSHOVER__PRIORITY', '0')),
                'include_snapshot': os.environ.get('NOTIFICATIONS__PUSHOVER__INCLUDE_SNAPSHOT', 'true').lower() == 'true',
            },
            'telegram': {
                'enabled': os.environ.get('NOTIFICATIONS__TELEGRAM__ENABLED', 'false').lower() == 'true',
                'bot_token': os.environ.get('NOTIFICATIONS__TELEGRAM__BOT_TOKEN', None),
                'chat_id': os.environ.get('NOTIFICATIONS__TELEGRAM__CHAT_ID', None),
                'include_snapshot': os.environ.get('NOTIFICATIONS__TELEGRAM__INCLUDE_SNAPSHOT', 'true').lower() == 'true',
            },
            'email': {
                'enabled': os.environ.get('NOTIFICATIONS__EMAIL__ENABLED', 'false').lower() == 'true',
                'use_oauth': os.environ.get('NOTIFICATIONS__EMAIL__USE_OAUTH', 'false').lower() == 'true',
                'oauth_provider': os.environ.get('NOTIFICATIONS__EMAIL__OAUTH_PROVIDER', None),
                'gmail_client_id': os.environ.get('NOTIFICATIONS__EMAIL__GMAIL_CLIENT_ID', None),
                'gmail_client_secret': os.environ.get('NOTIFICATIONS__EMAIL__GMAIL_CLIENT_SECRET', None),
                'outlook_client_id': os.environ.get('NOTIFICATIONS__EMAIL__OUTLOOK_CLIENT_ID', None),
                'outlook_client_secret': os.environ.get('NOTIFICATIONS__EMAIL__OUTLOOK_CLIENT_SECRET', None),
                'smtp_host': os.environ.get('NOTIFICATIONS__EMAIL__SMTP_HOST', None),
                'smtp_port': int(os.environ.get('NOTIFICATIONS__EMAIL__SMTP_PORT', '587')),
                'smtp_username': os.environ.get('NOTIFICATIONS__EMAIL__SMTP_USERNAME', None),
                'smtp_password': os.environ.get('NOTIFICATIONS__EMAIL__SMTP_PASSWORD', None),
                'smtp_use_tls': os.environ.get('NOTIFICATIONS__EMAIL__SMTP_USE_TLS', 'true').lower() == 'true',
                'from_email': os.environ.get('NOTIFICATIONS__EMAIL__FROM_EMAIL', None),
                'to_email': os.environ.get('NOTIFICATIONS__EMAIL__TO_EMAIL', None),
                'include_snapshot': os.environ.get('NOTIFICATIONS__EMAIL__INCLUDE_SNAPSHOT', 'true').lower() == 'true',
                'dashboard_url': os.environ.get('NOTIFICATIONS__EMAIL__DASHBOARD_URL', None),
            },
            'filters': {
                'species_whitelist': [],
                'min_confidence': 0.7,
                'audio_confirmed_only': False,
                'camera_filters': {}
            },
            'notification_language': os.environ.get('NOTIFICATIONS__NOTIFICATION_LANGUAGE', 'en')
        }

        # Accessibility settings
        accessibility_data = {
            'high_contrast': os.environ.get('ACCESSIBILITY__HIGH_CONTRAST', 'false').lower() == 'true',
            'dyslexia_font': os.environ.get('ACCESSIBILITY__DYSLEXIA_FONT', 'false').lower() == 'true',
            'reduced_motion': os.environ.get('ACCESSIBILITY__REDUCED_MOTION', 'false').lower() == 'true',
            'zen_mode': os.environ.get('ACCESSIBILITY__ZEN_MODE', 'false').lower() == 'true',
            'live_announcements': os.environ.get('ACCESSIBILITY__LIVE_ANNOUNCEMENTS', 'true').lower() == 'true',
        }

        species_info_source = os.environ.get('SPECIES_INFO__SOURCE', 'auto')

        # Load from config file if it exists, env vars take precedence
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, 'r') as f:
                    file_data = json.load(f)
                # Merge file data with env vars (env vars win)
                # Only use file values if the env var is not set at all
                # (checking 'in os.environ' ensures empty strings from compose defaults are respected)
                if 'frigate' in file_data:
                    for key, value in file_data['frigate'].items():
                        if key == 'camera_audio_mapping':
                            frigate_data[key] = value
                            continue
                        env_key = f'FRIGATE__{key.upper()}'
                        if env_key not in os.environ:
                            frigate_data[key] = value

                if 'maintenance' in file_data:
                    for key, value in file_data['maintenance'].items():
                        env_key = f'MAINTENANCE__{key.upper()}'
                        if env_key not in os.environ:
                            maintenance_data[key] = value

                if 'classification' in file_data:
                    for key, value in file_data['classification'].items():
                        if value is not None:  # Guard against null values in config
                            classification_data[key] = value

                if 'media_cache' in file_data:
                    for key, value in file_data['media_cache'].items():
                        env_key = f'MEDIA_CACHE__{key.upper()}'
                        if env_key not in os.environ:
                            media_cache_data[key] = value
                            
                if 'location' in file_data:
                    for key, value in file_data['location'].items():
                        if value is not None:
                            location_data[key] = value

                if 'birdweather' in file_data:
                    for key, value in file_data['birdweather'].items():
                        env_key = f'BIRDWEATHER__{key.upper()}'
                        if env_key not in os.environ:
                            birdweather_data[key] = value
                        
                if 'llm' in file_data:
                    for key, value in file_data['llm'].items():
                        env_key = f'LLM__{key.upper()}'
                        if env_key not in os.environ:
                            llm_data[key] = value
                            
                if 'telemetry' in file_data:
                    for key, value in file_data['telemetry'].items():
                        env_key = f'TELEMETRY__{key.upper()}'
                        if env_key not in os.environ:
                            telemetry_data[key] = value
                
                if 'notifications' in file_data:
                    # Deep merge notification settings
                    n_file = file_data['notifications']
                    
                    # Discord
                    if 'discord' in n_file:
                        for k, v in n_file['discord'].items():
                            env_key = f'NOTIFICATIONS__DISCORD__{k.upper()}'
                            if env_key not in os.environ:
                                notifications_data['discord'][k] = v
                                
                    # Pushover
                    if 'pushover' in n_file:
                        for k, v in n_file['pushover'].items():
                            env_key = f'NOTIFICATIONS__PUSHOVER__{k.upper()}'
                            if env_key not in os.environ:
                                notifications_data['pushover'][k] = v
                                
                    # Telegram
                    if 'telegram' in n_file:
                        for k, v in n_file['telegram'].items():
                            env_key = f'NOTIFICATIONS__TELEGRAM__{k.upper()}'
                            if env_key not in os.environ:
                                notifications_data['telegram'][k] = v

                    # Email
                    if 'email' in n_file:
                        for k, v in n_file['email'].items():
                            env_key = f'NOTIFICATIONS__EMAIL__{k.upper()}'
                            if env_key not in os.environ:
                                notifications_data['email'][k] = v
                                
                    # Filters (file only)
                    if 'filters' in n_file:
                         notifications_data['filters'] = n_file['filters']
                    
                    if 'notification_language' in n_file:
                        env_key = 'NOTIFICATIONS__NOTIFICATION_LANGUAGE'
                        if env_key not in os.environ:
                            notifications_data['notification_language'] = n_file['notification_language']

                if 'accessibility' in file_data:
                    for k, v in file_data['accessibility'].items():
                        env_key = f'ACCESSIBILITY__{k.upper()}'
                        if env_key not in os.environ:
                            accessibility_data[k] = v

                if 'species_info_source' in file_data and 'SPECIES_INFO__SOURCE' not in os.environ:
                    species_info_source = file_data['species_info_source']

                log.info("Loaded config from file", path=str(CONFIG_PATH))
            except Exception as e:
                log.warning("Failed to load config from file", path=str(CONFIG_PATH), error=str(e))

        log.info("MQTT config", server=frigate_data['mqtt_server'], port=frigate_data['mqtt_port'], auth=frigate_data['mqtt_auth'])
        log.info("Maintenance config", retention_days=maintenance_data['retention_days'])
        log.info("Classification config",
                 threshold=classification_data['threshold'],
                 min_confidence=classification_data['min_confidence'],
                 blocked_labels=classification_data['blocked_labels'],
                 unknown_bird_labels=classification_data['unknown_bird_labels'],
                 trust_frigate_sublabel=classification_data['trust_frigate_sublabel'],
                 display_common_names=classification_data['display_common_names'],
                 scientific_name_primary=classification_data['scientific_name_primary'])
        log.info("Media cache config",
                 enabled=media_cache_data['enabled'],
                 cache_snapshots=media_cache_data['cache_snapshots'],
                 cache_clips=media_cache_data['cache_clips'],
                 retention_days=media_cache_data['retention_days'])
        log.info("BirdWeather config", enabled=birdweather_data['enabled'])
        log.info("LLM config", enabled=llm_data['enabled'], provider=llm_data['provider'])
        log.info("Telemetry config", enabled=telemetry_data['enabled'], installation_id=telemetry_data['installation_id'])
        log.info("Notification config", 
                 discord=notifications_data['discord']['enabled'],
                 pushover=notifications_data['pushover']['enabled'],
                 telegram=notifications_data['telegram']['enabled'])

        return cls(
            frigate=FrigateSettings(**frigate_data),
            classification=ClassificationSettings(**classification_data),
            maintenance=MaintenanceSettings(**maintenance_data),
            media_cache=MediaCacheSettings(**media_cache_data),
            location=LocationSettings(**location_data),
            birdweather=BirdWeatherSettings(**birdweather_data),
            llm=LLMSettings(**llm_data),
            telemetry=TelemetrySettings(**telemetry_data),
            notifications=NotificationSettings(**notifications_data),
            accessibility=AccessibilitySettings(**accessibility_data),
            species_info_source=species_info_source,
            api_key=api_key
        )

settings = Settings.load()
