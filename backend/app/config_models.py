import ipaddress
import secrets as secrets_lib
import socket
from typing import Any, Literal, Optional

import structlog
from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.bird_model_region_resolver import normalize_bird_model_region

log = structlog.get_logger()

FrigateMissingBehavior = Literal["mark_missing", "keep", "delete"]


def normalize_crop_model_override(value: Any) -> str:
    normalized = str(value or "default").strip().lower()
    return normalized if normalized in {"default", "on", "off"} else "default"


def normalize_crop_source_override(value: Any) -> str:
    normalized = str(value or "default").strip().lower()
    return normalized if normalized in {"default", "standard", "high_quality"} else "default"


def normalize_crop_override_map(
    raw_value: Any,
    *,
    value_normalizer,
) -> dict[str, str]:
    if not isinstance(raw_value, dict):
        return {}
    normalized: dict[str, str] = {}
    for raw_key, raw_override in raw_value.items():
        key = str(raw_key or "").strip()
        if not key:
            continue
        normalized[key] = value_normalizer(raw_override)
    return normalized

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
    recording_clip_enabled: bool = Field(
        default=False,
        description="Enable full-visit recording clips from Frigate continuous recordings",
    )
    recording_clip_before_seconds: int = Field(
        default=30,
        ge=0,
        le=3600,
        description="Seconds of recording to include before the detection timestamp",
    )
    recording_clip_after_seconds: int = Field(
        default=90,
        ge=0,
        le=3600,
        description="Seconds of recording to include after the detection timestamp",
    )
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
    model: str = "rope_vit_b14_inat21"
    threshold: float = 0.7
    min_confidence: float = Field(default=0.4, ge=0.0, le=1.0, description="Minimum confidence floor (reject below this)")
    bird_crop_detector_tier: Literal["fast", "accurate"] = Field(
        default="fast",
        description="Bird crop detector tier: fast|accurate",
    )
    bird_crop_source_priority: Literal[
        "frigate_hints_first",
        "crop_model_first",
        "crop_model_only",
        "frigate_hints_only",
    ] = Field(
        default="frigate_hints_first",
        description="Bird crop source priority: frigate_hints_first|crop_model_first|crop_model_only|frigate_hints_only",
    )
    blocked_labels: list[str] = Field(
        default=[],
        description="Labels to filter out completely (won't be saved)"
    )
    blocked_species: list["BlockedSpeciesEntry"] = Field(
        default_factory=list,
        description="Structured blocked species entries keyed by taxonomy identity",
    )
    unknown_bird_labels: list[str] = Field(
        default=["background", "Background"],
        description="Labels to relabel as 'Unknown Bird' (unidentifiable detections)"
    )
    trust_frigate_sublabel: bool = Field(
        default=True,
        description="Fall back to Frigate sublabel when YA-WAMF classification fails threshold"
    )
    write_frigate_sublabel: bool = Field(
        default=True,
        description="Write YA-WAMF species labels back to Frigate as event sublabels"
    )
    display_common_names: bool = Field(
        default=True,
        description="Display common names instead of scientific names when available"
    )
    scientific_name_primary: bool = Field(
        default=False,
        description="Show scientific name as the primary label in UI"
    )
    personalized_rerank_enabled: bool = Field(
        default=False,
        description="Enable personalized camera/model-aware reranking from manual tags"
    )
    # Auto Video Classification
    auto_video_classification: bool = Field(default=False, description="Automatically classify video clips when available")
    video_classification_delay: int = Field(default=30, description="Seconds to wait before checking for clip (allow Frigate to finalize)")
    video_classification_max_retries: int = Field(default=3, description="Max retries for clip availability")
    video_classification_retry_interval: int = Field(default=15, description="Seconds between retries")
    video_classification_max_concurrent: int = Field(default=1, ge=1, le=20, description="Maximum concurrent video classification tasks")
    video_classification_failure_threshold: int = Field(default=5, ge=1, description="Failures in window to open circuit breaker")
    video_classification_failure_window_minutes: int = Field(default=10, ge=1, description="Failure window size in minutes")
    video_classification_failure_cooldown_minutes: int = Field(default=15, ge=1, description="Cooldown minutes when circuit breaker is open")
    video_classification_timeout_seconds: int = Field(default=180, ge=30, description="Timeout for a single video classification run")
    video_classification_stale_minutes: int = Field(default=15, ge=1, description="Mark pending/processing as failed after this many minutes")
    video_classification_frames: int = Field(default=15, ge=5, le=100, description="Number of frames to sample for video classification")
    strict_non_finite_output: bool = Field(
        default=True,
        description="Reject all-non-finite model output vectors and trigger runtime recovery/fallback",
    )
    inference_provider: str = Field(default="auto", description="Preferred inference provider: auto|cpu|cuda|intel_gpu|intel_cpu")
    image_execution_mode: str = Field(
        default="in_process",
        description="Image inference execution mode: in_process|subprocess",
    )
    live_worker_count: int = Field(default=2, ge=1, le=8, description="Live classifier worker process count")
    background_worker_count: int = Field(default=1, ge=1, le=4, description="Background classifier worker process count")
    worker_heartbeat_timeout_seconds: float = Field(default=5.0, ge=0.5, le=60.0, description="Classifier worker heartbeat timeout in seconds")
    worker_hard_deadline_seconds: float = Field(default=60.0, ge=1.0, le=300.0, description="Hard deadline before killing a stuck classifier worker")
    background_worker_hard_deadline_seconds: float = Field(default=120.0, ge=1.0, le=600.0, description="Hard deadline before killing a stuck background classifier worker")
    worker_ready_timeout_seconds: float = Field(default=60.0, ge=1.0, le=300.0, description="Timeout while waiting for a classifier worker to load and report ready")
    worker_restart_window_seconds: float = Field(default=60.0, ge=1.0, le=3600.0, description="Rolling window for classifier worker restart budget")
    worker_restart_threshold: int = Field(default=3, ge=1, le=100, description="Restart count in window before classifier circuit breaker opens")
    worker_breaker_cooldown_seconds: float = Field(default=60.0, ge=1.0, le=3600.0, description="Cooldown while classifier worker circuit breaker is open")
    live_event_stale_drop_seconds: float = Field(default=30.0, ge=1.0, le=3600.0, description="Drop live events older than this before classifier admission")
    live_event_coalescing_enabled: bool = Field(default=True, description="Coalesce duplicate live image classification requests before admission")
    ai_pricing_json: str = Field(default="[]", description="JSON string containing AI pricing overrides")
    bird_model_region_override: str = Field(
        default="auto",
        description="Bird model region override: auto|eu|na",
    )
    crop_model_overrides: dict[str, str] = Field(
        default_factory=dict,
        description="Crop enablement overrides keyed by model/family id or variant id",
    )
    crop_source_overrides: dict[str, str] = Field(
        default_factory=dict,
        description="Crop source overrides keyed by model/family id or variant id",
    )

    # Classification output settings
    max_classification_results: int = Field(default=5, ge=1, le=20, description="Maximum number of top results to return from classifier")

    # Wildlife/general animal model settings
    wildlife_model: str = Field(default="wildlife_model.tflite", description="Wildlife classification model file")
    wildlife_labels: str = Field(default="wildlife_labels.txt", description="Wildlife labels file")

    @field_validator("inference_provider")
    @classmethod
    def validate_inference_provider(cls, v: str) -> str:
        normalized = (v or "auto").strip().lower()
        allowed = {"auto", "cpu", "cuda", "intel_gpu", "intel_cpu"}
        if normalized not in allowed:
            log.warning("Invalid inference_provider in config; falling back to auto", value=v)
            return "auto"
        return normalized

    @field_validator("image_execution_mode")
    @classmethod
    def validate_image_execution_mode(cls, v: str) -> str:
        normalized = (v or "in_process").strip().lower()
        allowed = {"in_process", "subprocess"}
        if normalized not in allowed:
            log.warning("Invalid image_execution_mode in config; falling back to in_process", value=v)
            return "in_process"
        return normalized

    @field_validator("bird_model_region_override")
    @classmethod
    def validate_bird_model_region_override(cls, v: str) -> str:
        normalized = normalize_bird_model_region(v)
        if normalized != (v or "auto").strip().lower():
            log.warning("Invalid bird_model_region_override in config; falling back to auto", value=v)
        return normalized

    @field_validator("crop_model_overrides", mode="before")
    @classmethod
    def validate_crop_model_overrides(cls, value: Any) -> dict[str, str]:
        return normalize_crop_override_map(value, value_normalizer=normalize_crop_model_override)

    @field_validator("crop_source_overrides", mode="before")
    @classmethod
    def validate_crop_source_overrides(cls, value: Any) -> dict[str, str]:
        return normalize_crop_override_map(value, value_normalizer=normalize_crop_source_override)

class MaintenanceSettings(BaseModel):
    retention_days: int = Field(default=0, ge=0, description="Days to keep detections (0 = unlimited)")
    cleanup_enabled: bool = Field(default=True, description="Enable automatic cleanup")
    max_concurrent: int = Field(
        default=1,
        ge=1,
        le=8,
        description="Per-kind maintenance concurrency default. Each kind (backfill, weather_backfill, video_classification, taxonomy_sync, timezone_repair, analyze_unknowns) gets this many slots unless overridden by per_kind_capacity. Different kinds no longer contend for a single global slot.",
    )
    per_kind_capacity: dict[str, int] = Field(
        default_factory=dict,
        description="Optional per-kind capacity overrides (e.g. {\"video_classification\": 2}). Kinds not listed use max_concurrent.",
    )
    total_max_concurrent: int = Field(
        default=3,
        ge=0,
        le=32,
        description="Overall cap on concurrent maintenance holders across all kinds (0 = unlimited). Default 3 gives ~2x headroom over steady-state load (1 continuous video_classification + occasional user-triggered kind) while preventing the 6-way pile-up that could saturate the DB pool.",
    )
    auto_delete_missing_clips: bool = Field(
        default=False,
        description="Auto-delete detections when the Frigate event/clip is missing"
    )
    frigate_missing_behavior: FrigateMissingBehavior = Field(
        default="mark_missing",
        description="How YA-WAMF should react when Frigate no longer has an event or retained media",
    )
    auto_purge_missing_clips: bool = Field(
        default=False,
        description="Purge detections without clips during scheduled cleanup"
    )
    auto_purge_missing_snapshots: bool = Field(
        default=False,
        description="Purge detections without snapshots during scheduled cleanup"
    )
    auto_analyze_unknowns: bool = Field(
        default=False,
        description="Analyze unknown detections during scheduled cleanup"
    )

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_missing_behavior(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        behavior = str(normalized.get("frigate_missing_behavior") or "").strip().lower()
        if behavior:
            normalized["frigate_missing_behavior"] = behavior
            return normalized
        if bool(normalized.get("auto_delete_missing_clips")):
            normalized["frigate_missing_behavior"] = "delete"
        else:
            normalized["frigate_missing_behavior"] = "mark_missing"
        return normalized


class MediaCacheSettings(BaseModel):
    enabled: bool = Field(default=True, description="Enable local media caching")
    cache_snapshots: bool = Field(default=True, description="Cache snapshot images locally")
    cache_clips: bool = Field(default=False, description="Cache video clips locally (may cause initial playback delay)")
    high_quality_event_snapshots: bool = Field(
        default=False,
        description="Asynchronously replace cached event snapshots with a frame derived from the Frigate clip",
    )
    high_quality_event_snapshot_bird_crop: bool = Field(
        default=False,
        description="Run the bird crop detector on derived high-quality event snapshots before caching",
    )
    high_quality_event_snapshot_jpeg_quality: int = Field(
        default=95,
        ge=70,
        le=100,
        description="JPEG quality for derived high-quality event snapshots",
    )
    retention_days: int = Field(default=0, ge=0, description="Days to keep cached media (0 = follow detection retention)")

class LocationSettings(BaseModel):
    latitude: Optional[float] = Field(None, description="Latitude for weather/sun data")
    longitude: Optional[float] = Field(None, description="Longitude for weather/sun data")
    state: Optional[str] = Field(None, description="Optional state/region for eBird export")
    country: Optional[str] = Field(None, description="Optional country for eBird export")
    automatic: bool = Field(True, description="Attempt to detect location automatically via IP")
    weather_unit_system: Literal["metric", "imperial", "british"] = Field(
        default="metric",
        description="Weather measurement unit system: metric, imperial, or british",
    )

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_temperature_unit(cls, data):
        if not isinstance(data, dict):
            return data
        migrated = dict(data)
        if "weather_unit_system" not in migrated or migrated.get("weather_unit_system") is None:
            legacy_unit = str(migrated.get("temperature_unit", "") or "").strip().lower()
            if legacy_unit == "fahrenheit":
                migrated["weather_unit_system"] = "imperial"
            elif legacy_unit == "celsius":
                migrated["weather_unit_system"] = "metric"
        return migrated

    @field_validator("weather_unit_system")
    @classmethod
    def validate_weather_unit_system(cls, v: str) -> str:
        normalized = (v or "metric").strip().lower()
        if normalized not in {"metric", "imperial", "british"}:
            log.warning("Invalid weather_unit_system in config; falling back to metric", value=v)
            return "metric"
        return normalized

    @property
    def temperature_unit(self) -> str:
        return "fahrenheit" if self.weather_unit_system == "imperial" else "celsius"

    @temperature_unit.setter
    def temperature_unit(self, value: str) -> None:
        normalized = (value or "celsius").strip().lower()
        self.weather_unit_system = "imperial" if normalized == "fahrenheit" else "metric"

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


class BlockedSpeciesEntry(BaseModel):
    scientific_name: Optional[str] = Field(default=None, description="Canonical scientific name")
    common_name: Optional[str] = Field(default=None, description="Common name used for display")
    taxa_id: Optional[int] = Field(default=None, description="Canonical taxonomy id")

    @field_validator("scientific_name", "common_name", mode="before")
    @classmethod
    def _normalize_name(cls, value: Any) -> Optional[str]:
        text = str(value or "").strip()
        return text or None

    @field_validator("taxa_id", mode="before")
    @classmethod
    def _normalize_taxa_id(cls, value: Any) -> Optional[int]:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @model_validator(mode="after")
    def _require_identity(self) -> "BlockedSpeciesEntry":
        if self.taxa_id is None and not self.scientific_name and not self.common_name:
            raise ValueError("blocked species entry requires at least one identity field")
        return self


def normalize_blocked_species_entries(raw_value: Any) -> list["BlockedSpeciesEntry"]:
    if not isinstance(raw_value, list):
        return []

    normalized: list[BlockedSpeciesEntry] = []
    for raw_entry in raw_value:
        try:
            entry = (
                raw_entry
                if isinstance(raw_entry, BlockedSpeciesEntry)
                else BlockedSpeciesEntry.model_validate(raw_entry)
            )
        except Exception:
            continue
        normalized.append(entry)
    return normalized


DEFAULT_LLM_MODEL = "gemini-2.5-flash"


class LLMSettings(BaseModel):
    enabled: bool = Field(default=False, description="Enable LLM integration")
    provider: str = Field(default="gemini", description="AI provider (gemini, openai, claude)")
    api_key: Optional[str] = Field(default=None, description="API Key for the provider")
    model: str = Field(default=DEFAULT_LLM_MODEL, description="Model name to use")
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
    device: Optional[str] = Field(default=None, description="Target device name(s), comma-separated. Leave blank to send to all devices.")
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
    color_theme: str = Field(
        default="bluetit",
        description="UI color theme: default, bluetit"
    )

class SystemSettings(BaseModel):
    """System-level performance and resource settings"""
    broadcaster_max_queue_size: int = Field(default=100, ge=10, le=1000, description="Maximum SSE message queue size per subscriber")
    broadcaster_max_consecutive_full: int = Field(default=10, ge=1, le=100, description="Remove subscriber after this many consecutive backpressure failures")
    trusted_proxy_hosts: list[str] = Field(
        default_factory=lambda: DEFAULT_TRUSTED_PROXY_HOSTS.copy(),
        description="Trusted proxy hosts for X-Forwarded-* headers",
    )
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
    oauth_token_secret: Optional[str] = Field(
        default=None,
        description="Secret key for encrypting persisted OAuth tokens; falls back to session_secret if unset"
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
