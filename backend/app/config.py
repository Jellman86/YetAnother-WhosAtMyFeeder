import json
import os
import asyncio
import secrets as secrets_lib
import structlog
from typing import Optional
from pathlib import Path
import sys
import socket
import ipaddress
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, Field

log = structlog.get_logger()

# Use /config directory for persistent config (matches Docker volume mount)
# Allow override via environment variable for testing
if "pytest" in sys.modules or os.getenv("YA_WAMF_TESTING") == "1":
    # Tests run in a sandbox where writing to /config may be blocked.
    # Default to a writable location unless explicitly overridden.
    CONFIG_PATH = Path(os.getenv("CONFIG_FILE", "/tmp/yawamf-test-config.json"))
else:
    CONFIG_PATH = Path(os.getenv("CONFIG_FILE", "/config/config.json"))

LEGACY_DEFAULT_AI_ANALYSIS_PROMPT = """
You are an expert ornithologist and naturalist.
{frame_note}

Species identified by system: {species}
Time of detection: {time}
{weather_str}

Respond in Markdown with these exact section headings and short bullet points:
## Appearance
## Behavior
## Naturalist Note
## Seasonal Context

Keep the response concise (under 200 words). No extra sections.
{language_note}
""".strip()

DEFAULT_AI_ANALYSIS_PROMPT = """
You are an expert ornithologist and naturalist.
{frame_note}

Species identified by system: {species}
Time of detection: {time}
{weather_str}

Respond in Markdown with these exact section headings. Under each heading, write 1 short paragraph (no bullet lists):
## Appearance
## Behavior
## Naturalist Note
## Seasonal Context

Keep the response concise (under 200 words). No extra sections.
{language_note}
""".strip()

LEGACY_DEFAULT_AI_CONVERSATION_PROMPT = """
You are an expert ornithologist and naturalist. Continue a short Q&A about this detection.

Species identified by system: {species}
Previous analysis:
{analysis}

Conversation so far:
{history}

User question: {question}

Answer concisely in Markdown using the same headings as the analysis (## Appearance, ## Behavior, ## Naturalist Note, ## Seasonal Context).
If a section is not relevant, include it with a short "Not observed" bullet.
{language_note}
""".strip()

DEFAULT_AI_CONVERSATION_PROMPT = """
You are an expert ornithologist and naturalist. Continue a short Q&A about this detection.

Species identified by system: {species}
Previous analysis:
{analysis}

Conversation so far:
{history}

User question: {question}

Answer concisely in Markdown using the same headings as the analysis (## Appearance, ## Behavior, ## Naturalist Note, ## Seasonal Context).
Under each heading, write 1 short paragraph (no bullet lists). If a section is not relevant, write "Not observed."
{language_note}
""".strip()

DEFAULT_AI_CHART_PROMPT = """
You are a data analyst for bird feeder activity.
You are looking at a chart of detections over time.

Timeframe: {timeframe}
Total detections in range: {total_count}
Series shown: {series}
{weather_notes}
{sun_notes}

Respond in Markdown with these exact section headings and short bullet points:
## Overview
## Patterns
## Weather Correlations
## Notable Spikes/Dips
## Caveats

Keep it concise (under 200 words). No extra sections.
{language_note}
{notes}
""".strip()

# Default trusted proxy hosts for common reverse-proxy setups.
# These are only used when no env override or config value exists.
DEFAULT_TRUSTED_PROXY_HOSTS = [
    "yawamf-frontend",
    "nginx-rp",
    "cloudflare-tunnel",
]

def _expand_trusted_hosts(hosts: list[str]) -> list[str]:
    """Expand hostnames to IPs for ProxyHeadersMiddleware matching."""
    expanded: list[str] = []
    for host in hosts:
        if not host:
            continue
        host = host.strip()
        if not host:
            continue
        # Keep CIDR and valid IPs as-is
        try:
            if "/" in host:
                ipaddress.ip_network(host, strict=False)
                expanded.append(host)
                continue
            ipaddress.ip_address(host)
            expanded.append(host)
            continue
        except ValueError:
            pass

        # Resolve hostname to IPs
        try:
            _, _, ips = socket.gethostbyname_ex(host)
            expanded.extend(ips)
        except Exception:
            # Keep original hostname (may be used elsewhere)
            expanded.append(host)

    # De-duplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for host in expanded:
        if host not in seen:
            seen.add(host)
            result.append(host)
    return result

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
    video_classification_failure_threshold: int = Field(default=5, ge=1, description="Failures in window to open circuit breaker")
    video_classification_failure_window_minutes: int = Field(default=10, ge=1, description="Failure window size in minutes")
    video_classification_failure_cooldown_minutes: int = Field(default=15, ge=1, description="Cooldown minutes when circuit breaker is open")
    video_classification_timeout_seconds: int = Field(default=180, ge=30, description="Timeout for a single video classification run")
    video_classification_stale_minutes: int = Field(default=15, ge=1, description="Mark pending/processing as failed after this many minutes")

    # Classification output settings
    max_classification_results: int = Field(default=5, ge=1, le=20, description="Maximum number of top results to return from classifier")

    # Wildlife/general animal model settings
    wildlife_model: str = Field(default="wildlife_model.tflite", description="Wildlife classification model file")
    wildlife_labels: str = Field(default="wildlife_labels.txt", description="Wildlife labels file")

class MaintenanceSettings(BaseModel):
    retention_days: int = Field(default=0, ge=0, description="Days to keep detections (0 = unlimited)")
    cleanup_enabled: bool = Field(default=True, description="Enable automatic cleanup")
    auto_delete_missing_clips: bool = Field(
        default=False,
        description="Auto-delete detections when the Frigate event/clip is missing"
    )


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

class EbirdSettings(BaseModel):
    enabled: bool = Field(default=False, description="Enable eBird enrichment")
    api_key: Optional[str] = Field(default=None, description="eBird API key")
    default_radius_km: int = Field(default=25, ge=1, le=50, description="Default search radius in km (1-50)")
    default_days_back: int = Field(default=14, ge=1, le=30, description="Days back for recent observations (1-30)")
    max_results: int = Field(default=25, ge=1, le=200, description="Maximum results to return")
    locale: str = Field(default="en", description="Locale for species common names")

class InaturalistSettings(BaseModel):
    enabled: bool = Field(default=False, description="Enable iNaturalist submissions")
    client_id: Optional[str] = Field(default=None, description="iNaturalist OAuth Client ID")
    client_secret: Optional[str] = Field(default=None, description="iNaturalist OAuth Client Secret")
    default_latitude: Optional[float] = Field(default=None, description="Default latitude for submissions")
    default_longitude: Optional[float] = Field(default=None, description="Default longitude for submissions")
    default_place_guess: Optional[str] = Field(default=None, description="Default place guess for submissions")

class EnrichmentSettings(BaseModel):
    mode: str = Field(default="per_enrichment", description="Enrichment source mode: single or per_enrichment")
    single_provider: str = Field(default="wikipedia", description="Provider used when mode=single")
    summary_source: str = Field(default="wikipedia", description="Provider for summaries/description")
    taxonomy_source: str = Field(default="inaturalist", description="Provider for taxonomy/common names")
    sightings_source: str = Field(default="disabled", description="Provider for nearby sightings")
    seasonality_source: str = Field(default="disabled", description="Provider for seasonality")
    rarity_source: str = Field(default="disabled", description="Provider for rarity indicators")
    links_sources: list[str] = Field(default=["wikipedia", "inaturalist"], description="Providers for external links")

class LLMSettings(BaseModel):
    enabled: bool = Field(default=False, description="Enable LLM integration")
    provider: str = Field(default="gemini", description="AI provider (gemini, openai, claude)")
    api_key: Optional[str] = Field(default=None, description="API Key for the provider")
    model: str = Field(default="gemini-3-flash-preview", description="Model name to use")
    analysis_prompt_template: str = Field(default=DEFAULT_AI_ANALYSIS_PROMPT, description="Prompt template for detection analysis")
    conversation_prompt_template: str = Field(default=DEFAULT_AI_CONVERSATION_PROMPT, description="Prompt template for follow-up conversation")
    chart_prompt_template: str = Field(default=DEFAULT_AI_CHART_PROMPT, description="Prompt template for chart analysis")

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
    only_on_end: bool = Field(default=False, description="Only send email notifications on Frigate MQTT end events")
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
    notification_language: str = Field(default="en", description="Language for notifications (en, es, fr, de, ja, ru, pt, it)")
    mode: str = Field(default="standard", description="Notification mode: silent, final, standard, realtime, custom")
    notify_on_insert: bool = Field(default=True, description="Notify on new detection insert")
    notify_on_update: bool = Field(default=False, description="Notify on detection updates")
    delay_until_video: bool = Field(default=False, description="Delay notifications until video analysis completes (if enabled)")
    video_fallback_timeout: int = Field(default=45, description="Seconds to wait for video before falling back to snapshot notification")
    notification_cooldown_minutes: int = Field(default=0, description="Global cooldown between notifications in minutes (0 = disabled)")

class AccessibilitySettings(BaseModel):
    high_contrast: bool = Field(default=False, description="Enable high contrast mode")
    dyslexia_font: bool = Field(default=False, description="Enable dyslexia-friendly font")
    reduced_motion: bool = Field(default=False, description="Reduce motion/animations")
    zen_mode: bool = Field(default=False, description="Enable simplified zen mode")
    live_announcements: bool = Field(default=True, description="Enable screen reader live announcements")

class AppearanceSettings(BaseModel):
    # Mirrors the frontend font themes. Email clients may fall back to system fonts.
    font_theme: str = Field(
        default="classic",
        description="UI font theme: default, clean, studio, classic, compact"
    )

class SystemSettings(BaseModel):
    """System-level performance and resource settings"""
    broadcaster_max_queue_size: int = Field(default=100, ge=10, le=1000, description="Maximum SSE message queue size per subscriber")
    broadcaster_max_consecutive_full: int = Field(default=10, ge=1, le=100, description="Remove subscriber after this many consecutive backpressure failures")
    trusted_proxy_hosts: list[str] = Field(default_factory=lambda: ["*"], description="Trusted proxy hosts for X-Forwarded-* headers")
    debug_ui_enabled: bool = Field(default=False, description="Expose debug UI sections in the web app")


class AuthSettings(BaseModel):
    """Authentication configuration."""
    enabled: bool = Field(
        default=False,
        description="Require authentication for full access (disabled by default for backward compatibility)"
    )
    username: str = Field(
        default="admin",
        description="Admin username"
    )
    password_hash: Optional[str] = Field(
        default=None,
        description="Bcrypt hashed password (set via Settings UI or auth/initial-setup endpoint)"
    )
    session_secret: str = Field(
        default_factory=lambda: secrets_lib.token_urlsafe(32),
        description="Secret key for JWT tokens (auto-generated)"
    )
    session_expiry_hours: int = Field(
        default=168,  # 7 days
        ge=1,
        le=720,  # 30 days max
        description="Session token validity in hours"
    )


class PublicAccessSettings(BaseModel):
    """Public/guest access configuration."""
    enabled: bool = Field(
        default=False,
        description="Allow unauthenticated public access to view detections"
    )
    show_camera_names: bool = Field(
        default=True,
        description="Show camera names to public visitors"
    )
    show_ai_conversation: bool = Field(
        default=False,
        description="Allow public visitors to view AI conversation threads"
    )
    allow_clip_downloads: bool = Field(
        default=False,
        description="Allow public visitors to download clip files"
    )
    historical_days_mode: str = Field(
        default="retention",
        description="History window mode: retention or custom"
    )
    show_historical_days: int = Field(
        default=7,
        ge=0,
        le=365,
        description="Days of historical data visible to public (0 = live only)"
    )
    media_days_mode: str = Field(
        default="retention",
        description="Media window mode: retention or custom"
    )
    media_historical_days: int = Field(
        default=7,
        ge=0,
        le=365,
        description="Days of media (snapshots/clips) visible to public (0 = live only)"
    )
    rate_limit_per_minute: int = Field(
        default=30,
        ge=1,
        le=100,
        description="API calls per minute for public users"
    )
    external_base_url: Optional[str] = Field(
        default=None,
        description="Public-facing base URL used when generating share links"
    )


class Settings(BaseSettings):
    frigate: FrigateSettings
    classification: ClassificationSettings = ClassificationSettings()
    maintenance: MaintenanceSettings = MaintenanceSettings()
    media_cache: MediaCacheSettings = MediaCacheSettings()
    location: LocationSettings = LocationSettings()
    birdweather: BirdWeatherSettings = BirdWeatherSettings()
    ebird: EbirdSettings = EbirdSettings()
    inaturalist: InaturalistSettings = InaturalistSettings()
    enrichment: EnrichmentSettings = EnrichmentSettings()
    llm: LLMSettings = LLMSettings()
    telemetry: TelemetrySettings = TelemetrySettings()
    notifications: NotificationSettings = NotificationSettings()
    accessibility: AccessibilitySettings = AccessibilitySettings()
    appearance: AppearanceSettings = AppearanceSettings()
    system: SystemSettings = SystemSettings()
    auth: AuthSettings = AuthSettings()
    public_access: PublicAccessSettings = PublicAccessSettings()
    species_info_source: str = Field(default="auto", description="Species info source: auto, inat, or wikipedia")
    date_format: str = Field(default="locale", description="Date format: locale, mdy, dmy, ymd")

    # General app settings
    log_level: str = "INFO"
    api_key: Optional[str] = None
    
    model_config = SettingsConfigDict(env_nested_delimiter='__', env_file='.env', extra='ignore')

    async def save(self):
        # Avoid aiofiles here: in this environment it can hang indefinitely.
        # asyncio.to_thread keeps the API async without relying on aiofiles.
        payload = self.model_dump_json(indent=2)
        path = CONFIG_PATH

        # Tests run in a sandbox and config persistence isn't what we're validating.
        # Keep this simple and synchronous to avoid executor/FS edge cases.
        if "pytest" in sys.modules or os.getenv("YA_WAMF_TESTING") == "1":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")
            return

        def _write_atomic() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(path)

        await asyncio.to_thread(_write_atomic)
            
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
            'auto_delete_missing_clips': os.environ.get('MAINTENANCE__AUTO_DELETE_MISSING_CLIPS', 'false').lower() == 'true',
        }

        # Classification settings (loaded from file and selected env vars)
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
            'video_classification_max_concurrent': int(os.environ.get('CLASSIFICATION__VIDEO_CLASSIFICATION_MAX_CONCURRENT', '5')),
            'video_classification_failure_threshold': int(os.environ.get('CLASSIFICATION__VIDEO_FAILURE_THRESHOLD', '5')),
            'video_classification_failure_window_minutes': int(os.environ.get('CLASSIFICATION__VIDEO_FAILURE_WINDOW_MINUTES', '10')),
            'video_classification_failure_cooldown_minutes': int(os.environ.get('CLASSIFICATION__VIDEO_FAILURE_COOLDOWN_MINUTES', '15')),
            'max_classification_results': int(os.environ.get('CLASSIFICATION__MAX_CLASSIFICATION_RESULTS', '5')),
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

        # eBird settings
        ebird_data = {
            'enabled': os.environ.get('EBIRD__ENABLED', 'false').lower() == 'true',
            'api_key': os.environ.get('EBIRD__API_KEY', None),
            'default_radius_km': int(os.environ.get('EBIRD__DEFAULT_RADIUS_KM', '25')),
            'default_days_back': int(os.environ.get('EBIRD__DEFAULT_DAYS_BACK', '14')),
            'max_results': int(os.environ.get('EBIRD__MAX_RESULTS', '25')),
            'locale': os.environ.get('EBIRD__LOCALE', 'en'),
        }

        # iNaturalist settings
        inaturalist_data = {
            'enabled': os.environ.get('INATURALIST__ENABLED', 'false').lower() == 'true',
            'client_id': os.environ.get('INATURALIST__CLIENT_ID', None),
            'client_secret': os.environ.get('INATURALIST__CLIENT_SECRET', None),
            'default_latitude': None,
            'default_longitude': None,
            'default_place_guess': None,
        }

        # Enrichment settings
        enrichment_data = {
            'mode': os.environ.get('ENRICHMENT__MODE', 'per_enrichment'),
            'single_provider': os.environ.get('ENRICHMENT__SINGLE_PROVIDER', 'wikipedia'),
            'summary_source': os.environ.get('ENRICHMENT__SUMMARY_SOURCE', 'wikipedia'),
            'taxonomy_source': os.environ.get('ENRICHMENT__TAXONOMY_SOURCE', 'inaturalist'),
            'sightings_source': os.environ.get('ENRICHMENT__SIGHTINGS_SOURCE', 'disabled'),
            'seasonality_source': os.environ.get('ENRICHMENT__SEASONALITY_SOURCE', 'disabled'),
            'rarity_source': os.environ.get('ENRICHMENT__RARITY_SOURCE', 'disabled'),
            'links_sources': [s.strip() for s in os.environ.get('ENRICHMENT__LINKS_SOURCES', 'wikipedia,inaturalist').split(',') if s.strip()],
        }

        # LLM settings
        llm_data = {
            'enabled': os.environ.get('LLM__ENABLED', 'false').lower() == 'true',
            'provider': os.environ.get('LLM__PROVIDER', 'gemini'),
            'api_key': os.environ.get('LLM__API_KEY', None),
            'model': os.environ.get('LLM__MODEL', 'gemini-3-flash-preview'),
            'analysis_prompt_template': os.environ.get('LLM__ANALYSIS_PROMPT_TEMPLATE', DEFAULT_AI_ANALYSIS_PROMPT),
            'conversation_prompt_template': os.environ.get('LLM__CONVERSATION_PROMPT_TEMPLATE', DEFAULT_AI_CONVERSATION_PROMPT),
            'chart_prompt_template': os.environ.get('LLM__CHART_PROMPT_TEMPLATE', DEFAULT_AI_CHART_PROMPT),
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
                'only_on_end': os.environ.get('NOTIFICATIONS__EMAIL__ONLY_ON_END', 'false').lower() == 'true',
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
            'notification_language': os.environ.get('NOTIFICATIONS__NOTIFICATION_LANGUAGE', 'en'),
            'mode': os.environ.get('NOTIFICATIONS__MODE', 'standard'),
            'notify_on_insert': os.environ.get('NOTIFICATIONS__NOTIFY_ON_INSERT', 'true').lower() == 'true',
            'notify_on_update': os.environ.get('NOTIFICATIONS__NOTIFY_ON_UPDATE', 'false').lower() == 'true',
            'delay_until_video': os.environ.get('NOTIFICATIONS__DELAY_UNTIL_VIDEO', 'false').lower() == 'true',
            'video_fallback_timeout': int(os.environ.get('NOTIFICATIONS__VIDEO_FALLBACK_TIMEOUT', '45'))
        }

        # Accessibility settings
        accessibility_data = {
            'high_contrast': os.environ.get('ACCESSIBILITY__HIGH_CONTRAST', 'false').lower() == 'true',
            'dyslexia_font': os.environ.get('ACCESSIBILITY__DYSLEXIA_FONT', 'false').lower() == 'true',
            'reduced_motion': os.environ.get('ACCESSIBILITY__REDUCED_MOTION', 'false').lower() == 'true',
            'zen_mode': os.environ.get('ACCESSIBILITY__ZEN_MODE', 'false').lower() == 'true',
            'live_announcements': os.environ.get('ACCESSIBILITY__LIVE_ANNOUNCEMENTS', 'true').lower() == 'true',
        }

        # Authentication settings
        auth_data = {
            'enabled': os.environ.get('AUTH__ENABLED', 'false').lower() == 'true',
            'username': os.environ.get('AUTH__USERNAME', 'admin'),
            'password_hash': os.environ.get('AUTH__PASSWORD_HASH', None),
            'session_secret': os.environ.get('AUTH__SESSION_SECRET', secrets_lib.token_urlsafe(32)),
            'session_expiry_hours': int(os.environ.get('AUTH__SESSION_EXPIRY_HOURS', '168')),
        }

        # Public access settings
        public_access_data = {
            'enabled': os.environ.get('PUBLIC_ACCESS__ENABLED', 'false').lower() == 'true',
            'show_camera_names': os.environ.get('PUBLIC_ACCESS__SHOW_CAMERA_NAMES', 'true').lower() == 'true',
            'show_ai_conversation': os.environ.get('PUBLIC_ACCESS__SHOW_AI_CONVERSATION', 'false').lower() == 'true',
            'allow_clip_downloads': os.environ.get('PUBLIC_ACCESS__ALLOW_CLIP_DOWNLOADS', 'false').lower() == 'true',
            'historical_days_mode': os.environ.get('PUBLIC_ACCESS__HISTORICAL_DAYS_MODE', 'retention'),
            'show_historical_days': int(os.environ.get('PUBLIC_ACCESS__SHOW_HISTORICAL_DAYS', '7')),
            'media_days_mode': os.environ.get('PUBLIC_ACCESS__MEDIA_DAYS_MODE', 'retention'),
            'media_historical_days': int(os.environ.get('PUBLIC_ACCESS__MEDIA_HISTORICAL_DAYS', '7')),
            'rate_limit_per_minute': int(os.environ.get('PUBLIC_ACCESS__RATE_LIMIT_PER_MINUTE', '30')),
            'external_base_url': os.environ.get('PUBLIC_ACCESS__EXTERNAL_BASE_URL', None),
        }

        # System settings (existing but need to initialize)
        trusted_hosts_raw = os.environ.get('SYSTEM__TRUSTED_PROXY_HOSTS', '')
        trusted_hosts = (
            [host.strip() for host in trusted_hosts_raw.split(',') if host.strip()]
            if trusted_hosts_raw
            else DEFAULT_TRUSTED_PROXY_HOSTS.copy()
        )
        trusted_hosts = _expand_trusted_hosts(trusted_hosts)
        system_data = {
            'broadcaster_max_queue_size': int(os.environ.get('SYSTEM__BROADCASTER_MAX_QUEUE_SIZE', '100')),
            'broadcaster_max_consecutive_full': int(os.environ.get('SYSTEM__BROADCASTER_MAX_CONSECUTIVE_FULL', '10')),
            'trusted_proxy_hosts': trusted_hosts,
            'debug_ui_enabled': os.environ.get('SYSTEM__DEBUG_UI_ENABLED', 'false').lower() == 'true',
        }

        # Appearance settings
        appearance_data = {
            'font_theme': os.environ.get('APPEARANCE__FONT_THEME', 'classic'),
        }

        species_info_source = os.environ.get('SPECIES_INFO__SOURCE', 'auto')
        date_format = os.environ.get('DISPLAY__DATE_FORMAT', 'locale')

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

                if 'ebird' in file_data:
                    for key, value in file_data['ebird'].items():
                        env_key = f'EBIRD__{key.upper()}'
                        if env_key not in os.environ:
                            ebird_data[key] = value

                if 'inaturalist' in file_data:
                    for key, value in file_data['inaturalist'].items():
                        env_key = f'INATURALIST__{key.upper()}'
                        if env_key not in os.environ:
                            inaturalist_data[key] = value

                if 'enrichment' in file_data:
                    for key, value in file_data['enrichment'].items():
                        env_key = f'ENRICHMENT__{key.upper()}'
                        if env_key not in os.environ:
                            enrichment_data[key] = value
                        
                if 'llm' in file_data:
                    for key, value in file_data['llm'].items():
                        env_key = f'LLM__{key.upper()}'
                        if env_key not in os.environ:
                            llm_data[key] = value

                # If the user never customized prompts and is still on our legacy defaults,
                # upgrade them to the newer paragraph-based defaults.
                if llm_data.get('analysis_prompt_template') == LEGACY_DEFAULT_AI_ANALYSIS_PROMPT:
                    llm_data['analysis_prompt_template'] = DEFAULT_AI_ANALYSIS_PROMPT
                if llm_data.get('conversation_prompt_template') == LEGACY_DEFAULT_AI_CONVERSATION_PROMPT:
                    llm_data['conversation_prompt_template'] = DEFAULT_AI_CONVERSATION_PROMPT
                            
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

                    if 'mode' in n_file:
                        env_key = 'NOTIFICATIONS__MODE'
                        if env_key not in os.environ:
                            notifications_data['mode'] = n_file['mode']

                    if 'notify_on_insert' in n_file:
                        env_key = 'NOTIFICATIONS__NOTIFY_ON_INSERT'
                        if env_key not in os.environ:
                            notifications_data['notify_on_insert'] = n_file['notify_on_insert']
                    if 'notify_on_update' in n_file:
                        env_key = 'NOTIFICATIONS__NOTIFY_ON_UPDATE'
                        if env_key not in os.environ:
                            notifications_data['notify_on_update'] = n_file['notify_on_update']
                    if 'delay_until_video' in n_file:
                        env_key = 'NOTIFICATIONS__DELAY_UNTIL_VIDEO'
                        if env_key not in os.environ:
                            notifications_data['delay_until_video'] = n_file['delay_until_video']
                    if 'video_fallback_timeout' in n_file:
                        env_key = 'NOTIFICATIONS__VIDEO_FALLBACK_TIMEOUT'
                        if env_key not in os.environ:
                            notifications_data['video_fallback_timeout'] = n_file['video_fallback_timeout']
                    if 'notification_cooldown_minutes' in n_file:
                        env_key = 'NOTIFICATIONS__NOTIFICATION_COOLDOWN_MINUTES'
                        if env_key not in os.environ:
                            notifications_data['notification_cooldown_minutes'] = n_file['notification_cooldown_minutes']

                if 'accessibility' in file_data:
                    for k, v in file_data['accessibility'].items():
                        env_key = f'ACCESSIBILITY__{k.upper()}'
                        if env_key not in os.environ:
                            accessibility_data[k] = v

                if 'auth' in file_data:
                    for k, v in file_data['auth'].items():
                        env_key = f'AUTH__{k.upper()}'
                        if env_key not in os.environ:
                            auth_data[k] = v

                if 'public_access' in file_data:
                    for k, v in file_data['public_access'].items():
                        env_key = f'PUBLIC_ACCESS__{k.upper()}'
                        if env_key not in os.environ:
                            public_access_data[k] = v

                if 'system' in file_data:
                  for k, v in file_data['system'].items():
                        env_key = f'SYSTEM__{k.upper()}'
                        if env_key not in os.environ:
                            system_data[k] = v

                if 'appearance' in file_data:
                    for k, v in file_data['appearance'].items():
                        env_key = f'APPEARANCE__{k.upper()}'
                        if env_key not in os.environ:
                            appearance_data[k] = v

                if 'species_info_source' in file_data and 'SPECIES_INFO__SOURCE' not in os.environ:
                    species_info_source = file_data['species_info_source']
                    # Back-compat: if enrichment isn't explicitly configured, map species_info_source to summary source.
                    if 'enrichment' not in file_data and 'ENRICHMENT__SUMMARY_SOURCE' not in os.environ:
                        if species_info_source == "inat":
                            enrichment_data['summary_source'] = "inaturalist"
                        elif species_info_source == "wikipedia":
                            enrichment_data['summary_source'] = "wikipedia"
                        else:
                            enrichment_data['summary_source'] = "inaturalist"

                if 'date_format' in file_data and 'DISPLAY__DATE_FORMAT' not in os.environ:
                    date_format = file_data['date_format']

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
        log.info("eBird config", enabled=ebird_data['enabled'])
        log.info("iNaturalist config", enabled=inaturalist_data['enabled'])
        log.info("Enrichment config", mode=enrichment_data['mode'])
        log.info("LLM config", enabled=llm_data['enabled'], provider=llm_data['provider'])
        log.info("Telemetry config", enabled=telemetry_data['enabled'], installation_id=telemetry_data['installation_id'])
        log.info("Notification config",
                 discord=notifications_data['discord']['enabled'],
                 pushover=notifications_data['pushover']['enabled'],
                 telegram=notifications_data['telegram']['enabled'])
        log.info("Auth config",
                 enabled=auth_data['enabled'],
                 username=auth_data['username'],
                 has_password=auth_data['password_hash'] is not None)
        log.info("Public access config",
                 enabled=public_access_data['enabled'],
                 historical_days=public_access_data['show_historical_days'],
                 media_historical_days=public_access_data['media_historical_days'],
                 external_base_url=bool(public_access_data.get('external_base_url')))

        return cls(
            frigate=FrigateSettings(**frigate_data),
            classification=ClassificationSettings(**classification_data),
            maintenance=MaintenanceSettings(**maintenance_data),
            media_cache=MediaCacheSettings(**media_cache_data),
            location=LocationSettings(**location_data),
            birdweather=BirdWeatherSettings(**birdweather_data),
            ebird=EbirdSettings(**ebird_data),
            inaturalist=InaturalistSettings(**inaturalist_data),
            enrichment=EnrichmentSettings(**enrichment_data),
            llm=LLMSettings(**llm_data),
            telemetry=TelemetrySettings(**telemetry_data),
            notifications=NotificationSettings(**notifications_data),
            accessibility=AccessibilitySettings(**accessibility_data),
            appearance=AppearanceSettings(**appearance_data),
            system=SystemSettings(**system_data),
            auth=AuthSettings(**auth_data),
            public_access=PublicAccessSettings(**public_access_data),
            species_info_source=species_info_source,
            date_format=date_format,
            api_key=api_key
        )

settings = Settings.load()
