"""Prepare settings privately and publish durable candidates through one writer boundary."""

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, TypeVar

from fastapi import HTTPException
from pydantic import BaseModel

from app.auth import hash_password
from app.config import Settings
from app.config_models import (
    normalize_blocked_species_entries,
    normalize_crop_override_map,
    normalize_crop_model_override,
    normalize_crop_source_override,
)
from app.services.bird_model_region_resolver import normalize_bird_model_region
from app.services.notification_links import public_base

if TYPE_CHECKING:
    from app.routers.settings import SettingsUpdate

AUTH_PASSWORD_REQUIRED_TO_ENABLE_MESSAGE = "Password is required when enabling authentication"
settings_update_lock = asyncio.Lock()
_Result = TypeVar("_Result")


async def run_settings_writer(operation: Callable[[], Awaitable[_Result]]) -> _Result:
    """Serialize the full transaction, including publication and follow-up scheduling.

    A file save runs on a thread which cannot be cancelled. Finish its transaction
    before releasing the lock, even when the requesting client disconnects.
    """
    async with settings_update_lock:
        task = asyncio.create_task(operation())
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise


@dataclass
class PreparedSettings:
    candidate: Settings
    inference_provider_changed: bool
    execution_mode_changed: bool
    ebird_naming_changed: bool
    audit_events: list[tuple[str, dict[str, str | bool]]]


def prepare_update(current: Settings, update: "SettingsUpdate", username: str) -> PreparedSettings:
    candidate = current.model_copy(deep=True)
    audit_events: list[tuple[str, dict[str, str | bool]]] = []
    inference_provider_changed = False

    def should_update_secret(value: Optional[str]) -> bool:
        return value not in (None, "", "***REDACTED***")

    fields_set = update.model_fields_set
    auth_enabled_after_update = (
        update.auth_enabled
        if "auth_enabled" in fields_set and update.auth_enabled is not None
        else candidate.auth.enabled
    )
    auth_password_will_exist = candidate.auth.password_hash is not None or (
        "auth_password" in fields_set and bool(update.auth_password)
    )

    if auth_enabled_after_update and not auth_password_will_exist:
        raise HTTPException(status_code=422, detail=AUTH_PASSWORD_REQUIRED_TO_ENABLE_MESSAGE)

    if (
        "inference_provider" in fields_set
        and update.inference_provider is not None
        and update.inference_provider != "auto"
        and update.inference_provider != str(getattr(candidate.classification, "inference_provider", "auto") or "auto")
    ):
        # The UI filters this list, but the API is the security/correctness
        # boundary. A *new* explicit provider may be saved only when the running
        # image exposes it and the active model's current-image host sweep
        # admitted it. This prevents raw API calls or stale clients from
        # bypassing per-install numerical validation. An unchanged stale choice
        # is allowed through full-form settings saves so an image switch does not
        # make unrelated settings impossible to edit.
        from app.services.classifier_service import get_classifier

        status = get_classifier().get_status()
        selectable = {
            str(provider or "").strip().lower()
            for provider in (status.get("available_providers") or [])
            if str(provider or "").strip()
        }
        if update.inference_provider not in selectable:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{update.inference_provider} is not validated for the active model "
                    "in this image on this host. Run hardware validation before selecting it."
                ),
            )

    finder = (
        update.bird_crop_accurate_detector
        if "bird_crop_accurate_detector" in fields_set and update.bird_crop_accurate_detector is not None
        else candidate.classification.bird_crop_accurate_detector
    )
    finder_provider = update.bird_crop_inference_provider or candidate.classification.bird_crop_inference_provider
    if finder_provider not in {"auto", "cpu"} and (
        finder != candidate.classification.bird_crop_accurate_detector
        or finder_provider != candidate.classification.bird_crop_inference_provider
    ):
        from app.services.model_manager import model_manager
        from app.services.model_validation import host_eligible_providers

        model_id = f"bird_crop_detector_accurate_{finder}"
        metadata = model_manager._get_registry_model_meta(model_id) or {}
        eligible = host_eligible_providers(model_id, artifact_sha256=metadata.get("sha256"))
        if finder_provider not in eligible:
            raise HTTPException(
                status_code=409,
                detail=f"{finder_provider} is not validated for {finder} on this host. Check this finder's devices first.",
            )

    if "notifications_instance_url" in fields_set and update.notifications_instance_url is not None:
        instance_url = update.notifications_instance_url.strip().rstrip("/") or None
        if instance_url and not public_base(instance_url):
            raise HTTPException(
                status_code=400,
                detail="Instance address must start with http:// or https://, for example https://feeder.example.com",
            )

    if "frigate_url" in fields_set and update.frigate_url is not None:
        candidate.frigate.frigate_url = update.frigate_url
    if "frigate_ingest_labels" in fields_set and update.frigate_ingest_labels is not None:
        from app.utils.frigate import normalize_ingest_labels

        candidate.frigate.ingest_labels = normalize_ingest_labels(update.frigate_ingest_labels)
    if "frigate_external_url" in fields_set and update.frigate_external_url is not None:
        candidate.frigate.frigate_external_url = update.frigate_external_url.strip().rstrip("/")
    if "mqtt_server" in fields_set and update.mqtt_server is not None:
        candidate.frigate.mqtt_server = update.mqtt_server
    if "mqtt_port" in fields_set:
        candidate.frigate.mqtt_port = update.mqtt_port
    if "mqtt_auth" in fields_set:
        candidate.frigate.mqtt_auth = update.mqtt_auth
    if "mqtt_username" in fields_set and update.mqtt_username is not None:
        candidate.frigate.mqtt_username = update.mqtt_username
    # Only update password if it's not the redacted placeholder
    if "mqtt_password" in fields_set and should_update_secret(update.mqtt_password):
        candidate.frigate.mqtt_password = update.mqtt_password
    if "birdnet_enabled" in fields_set and update.birdnet_enabled is not None:
        candidate.frigate.birdnet_enabled = update.birdnet_enabled
    if "birdnet_url" in fields_set and update.birdnet_url is not None:
        candidate.frigate.birdnet_url = update.birdnet_url.strip().rstrip("/")
    if "birdnet_external_url" in fields_set and update.birdnet_external_url is not None:
        candidate.frigate.birdnet_external_url = update.birdnet_external_url.strip().rstrip("/")
    if "audio_topic" in fields_set:
        candidate.frigate.audio_topic = update.audio_topic
    if "camera_audio_mapping" in fields_set:
        cleaned_mapping: dict[str, str] = {}
        for camera_name, mapping_value in (update.camera_audio_mapping or {}).items():
            if not isinstance(camera_name, str):
                continue
            normalized_camera = camera_name.strip()
            if not normalized_camera:
                continue
            if not isinstance(mapping_value, str):
                continue
            tokens = [token.strip() for token in re.split(r"[,\n;|]+", mapping_value) if token and token.strip()]
            if not tokens:
                continue
            cleaned_mapping[normalized_camera] = ", ".join(tokens)
        candidate.frigate.camera_audio_mapping = cleaned_mapping
    if "camera_roles" in fields_set:
        cleaned_roles: dict[str, str] = {}
        for camera_name, role in (update.camera_roles or {}).items():
            if not isinstance(camera_name, str) or not isinstance(role, str):
                continue
            normalized_camera = camera_name.strip()
            normalized_role = role.strip().lower()
            if not normalized_camera or normalized_role not in ("feeder", "nest"):
                continue
            # Don't bother persisting the default 'feeder' role; saves config bloat.
            if normalized_role == "feeder":
                continue
            cleaned_roles[normalized_camera] = normalized_role
        candidate.frigate.camera_roles = cleaned_roles
    if "garden_cameras" in fields_set:
        candidate.frigate.garden_cameras = update.garden_cameras
    if "garden_labels" in fields_set:
        candidate.frigate.garden_labels = update.garden_labels
    if "garden_motion_cameras" in fields_set:
        candidate.frigate.garden_motion_cameras = update.garden_motion_cameras
    if fields_set & {"garden_cameras", "garden_motion_cameras"}:
        # Motion collection runs only on Garden cameras, so any other entry is inert; dropping
        # it keeps the saved settings from claiming collection that cannot happen.
        garden_cameras = set(candidate.frigate.garden_cameras)
        candidate.frigate.garden_motion_cameras = [
            camera for camera in candidate.frigate.garden_motion_cameras if camera in garden_cameras
        ]
    if "garden_motion_confidence" in fields_set:
        candidate.frigate.garden_motion_confidence = update.garden_motion_confidence
    if "garden_notifications_enabled" in fields_set:
        candidate.frigate.garden_notifications_enabled = update.garden_notifications_enabled
    if "garden_notification_channels" in fields_set:
        candidate.frigate.garden_notification_channels = list(dict.fromkeys(update.garden_notification_channels))
    if "garden_notifications_use_bird_channels" in fields_set:
        candidate.frigate.garden_notifications_use_bird_channels = update.garden_notifications_use_bird_channels
    if "garden_notifications_include_photo" in fields_set:
        candidate.frigate.garden_notifications_include_photo = update.garden_notifications_include_photo
    if "garden_automatic_naming" in fields_set:
        candidate.frigate.garden_automatic_naming = update.garden_automatic_naming
    if "garden_naming_threshold" in fields_set:
        candidate.frigate.garden_naming_threshold = update.garden_naming_threshold
    if "garden_domestic_birds" in fields_set:
        candidate.frigate.garden_domestic_birds = update.garden_domestic_birds
    if "nest_dedupe_minutes" in fields_set and update.nest_dedupe_minutes is not None:
        candidate.frigate.nest_dedupe_minutes = update.nest_dedupe_minutes
    if "audio_buffer_hours" in fields_set:
        candidate.frigate.audio_buffer_hours = update.audio_buffer_hours
    if "audio_correlation_window_seconds" in fields_set:
        candidate.frigate.audio_correlation_window_seconds = update.audio_correlation_window_seconds
    if "audio_min_confidence" in fields_set:
        candidate.frigate.audio_min_confidence = update.audio_min_confidence

    if "classification_image_source" in fields_set:
        candidate.frigate.classification_image_source = update.classification_image_source
    if "recording_frame_delay_seconds" in fields_set:
        candidate.frigate.recording_frame_delay_seconds = update.recording_frame_delay_seconds
    if "clips_enabled" in fields_set:
        candidate.frigate.clips_enabled = update.clips_enabled
    if "recording_clip_enabled" in fields_set:
        candidate.frigate.recording_clip_enabled = update.recording_clip_enabled
    if "recording_clip_before_seconds" in fields_set:
        candidate.frigate.recording_clip_before_seconds = update.recording_clip_before_seconds
    if "recording_clip_after_seconds" in fields_set:
        candidate.frigate.recording_clip_after_seconds = update.recording_clip_after_seconds
    if "cameras" in fields_set:
        candidate.frigate.camera = update.cameras
    if "classification_threshold" in fields_set and update.classification_threshold is not None:
        candidate.classification.threshold = update.classification_threshold
    if "classification_min_confidence" in fields_set:
        candidate.classification.min_confidence = update.classification_min_confidence
    # None is meaningful here - it returns the count to default resolution - so
    # presence in fields_set alone decides whether the stored value changes.
    if "live_worker_count" in fields_set:
        candidate.classification.live_worker_count = update.live_worker_count
    if "background_worker_count" in fields_set:
        candidate.classification.background_worker_count = update.background_worker_count
    if "retention_days" in fields_set:
        candidate.maintenance.retention_days = update.retention_days
    if "maintenance_max_concurrent" in fields_set and update.maintenance_max_concurrent is not None:
        candidate.maintenance.max_concurrent = update.maintenance_max_concurrent
    if "auto_delete_missing_clips" in fields_set:
        candidate.maintenance.auto_delete_missing_clips = update.auto_delete_missing_clips
    if "frigate_missing_behavior" in fields_set:
        candidate.maintenance.frigate_missing_behavior = update.frigate_missing_behavior
    # An older client still writes only the legacy pair. Mirror it onto the scan
    # so its intent lands, and keep writing the legacy fields so a downgrade
    # reads back what it wrote.
    if "auto_purge_missing_clips" in fields_set:
        candidate.maintenance.auto_purge_missing_clips = update.auto_purge_missing_clips
    if "auto_purge_missing_snapshots" in fields_set:
        candidate.maintenance.auto_purge_missing_snapshots = update.auto_purge_missing_snapshots
    legacy_written = {"auto_purge_missing_clips", "auto_purge_missing_snapshots"} & fields_set
    if legacy_written and "media_integrity_scan_enabled" not in fields_set:
        clips = candidate.maintenance.auto_purge_missing_clips
        snapshots = candidate.maintenance.auto_purge_missing_snapshots
        candidate.maintenance.media_integrity_scan_enabled = bool(clips or snapshots)
        if clips or snapshots:
            candidate.maintenance.media_integrity_scan_media = (
                "any" if clips and snapshots else ("clip" if clips else "snapshot")
            )
    if "media_integrity_scan_enabled" in fields_set:
        candidate.maintenance.media_integrity_scan_enabled = update.media_integrity_scan_enabled
        # Keep the legacy pair truthful for a client that only reads those.
        candidate.maintenance.auto_purge_missing_clips = update.media_integrity_scan_enabled
        candidate.maintenance.auto_purge_missing_snapshots = update.media_integrity_scan_enabled
    if "media_integrity_scan_media" in fields_set:
        candidate.maintenance.media_integrity_scan_media = update.media_integrity_scan_media
    if "media_integrity_scan_interval_hours" in fields_set:
        candidate.maintenance.media_integrity_scan_interval_hours = update.media_integrity_scan_interval_hours
    if "media_integrity_scan_batch_size" in fields_set:
        candidate.maintenance.media_integrity_scan_batch_size = update.media_integrity_scan_batch_size
    if "auto_analyze_unknowns" in fields_set:
        candidate.maintenance.auto_analyze_unknowns = update.auto_analyze_unknowns
    if "blocked_labels" in fields_set:
        candidate.classification.blocked_labels = update.blocked_labels
    if "blocked_species" in fields_set:
        candidate.classification.blocked_species = normalize_blocked_species_entries(update.blocked_species)
    if "trust_frigate_sublabel" in fields_set:
        candidate.classification.trust_frigate_sublabel = update.trust_frigate_sublabel
    if "write_frigate_sublabel" in fields_set:
        candidate.classification.write_frigate_sublabel = update.write_frigate_sublabel
    if "display_common_names" in fields_set:
        candidate.classification.display_common_names = update.display_common_names
    if "scientific_name_primary" in fields_set:
        candidate.classification.scientific_name_primary = update.scientific_name_primary
    if "personalized_rerank_enabled" in fields_set and update.personalized_rerank_enabled is not None:
        candidate.classification.personalized_rerank_enabled = update.personalized_rerank_enabled
    if "range_filter_enabled" in fields_set and update.range_filter_enabled is not None:
        candidate.classification.range_filter_enabled = update.range_filter_enabled
    if "range_filter_region_level" in fields_set and update.range_filter_region_level is not None:
        candidate.classification.range_filter_region_level = update.range_filter_region_level

    if "auto_video_classification" in fields_set and update.auto_video_classification is not None:
        candidate.classification.auto_video_classification = update.auto_video_classification
    if "video_classification_delay" in fields_set and update.video_classification_delay is not None:
        candidate.classification.video_classification_delay = update.video_classification_delay
    if "video_classification_max_retries" in fields_set and update.video_classification_max_retries is not None:
        candidate.classification.video_classification_max_retries = update.video_classification_max_retries
    if "video_classification_frames" in fields_set and update.video_classification_frames is not None:
        candidate.classification.video_classification_frames = update.video_classification_frames

    execution_mode_changed = False
    if "image_execution_mode" in fields_set and update.image_execution_mode is not None:
        previous_mode = candidate.classification.image_execution_mode
        candidate.classification.image_execution_mode = update.image_execution_mode
        execution_mode_changed = previous_mode != update.image_execution_mode

    if "strict_non_finite_output" in fields_set and update.strict_non_finite_output is not None:
        candidate.classification.strict_non_finite_output = update.strict_non_finite_output
    if "inference_provider" in fields_set and update.inference_provider is not None:
        previous_provider = candidate.classification.inference_provider
        candidate.classification.inference_provider = update.inference_provider
        inference_provider_changed = previous_provider != update.inference_provider
    if "bird_crop_detector_tier" in fields_set and update.bird_crop_detector_tier is not None:
        candidate.classification.bird_crop_detector_tier = update.bird_crop_detector_tier
    if "bird_crop_accurate_detector" in fields_set and update.bird_crop_accurate_detector is not None:
        candidate.classification.bird_crop_accurate_detector = update.bird_crop_accurate_detector
    if "bird_crop_inference_provider" in fields_set and update.bird_crop_inference_provider is not None:
        candidate.classification.bird_crop_inference_provider = update.bird_crop_inference_provider
    if "bird_crop_source_priority" in fields_set and update.bird_crop_source_priority is not None:
        candidate.classification.bird_crop_source_priority = update.bird_crop_source_priority
    if "bird_model_region_override" in fields_set and update.bird_model_region_override is not None:
        candidate.classification.bird_model_region_override = normalize_bird_model_region(
            update.bird_model_region_override
        )
    if "crop_model_overrides" in fields_set:
        candidate.classification.crop_model_overrides = normalize_crop_override_map(
            update.crop_model_overrides,
            value_normalizer=normalize_crop_model_override,
        )
    if "crop_source_overrides" in fields_set:
        candidate.classification.crop_source_overrides = normalize_crop_override_map(
            update.crop_source_overrides,
            value_normalizer=normalize_crop_source_override,
        )

    # Media cache settings
    if "media_cache_clips" in fields_set:
        candidate.media_cache.cache_clips = update.media_cache_clips
    if "media_cache_high_quality_event_snapshots" in fields_set:
        candidate.media_cache.high_quality_event_snapshots = update.media_cache_high_quality_event_snapshots
    if "media_cache_high_quality_event_snapshot_bird_crop" in fields_set:
        candidate.media_cache.high_quality_event_snapshot_bird_crop = (
            update.media_cache_high_quality_event_snapshot_bird_crop
        )
    if "media_cache_high_quality_event_snapshot_jpeg_quality" in fields_set:
        candidate.media_cache.high_quality_event_snapshot_jpeg_quality = (
            update.media_cache_high_quality_event_snapshot_jpeg_quality
        )
    if "media_cache_retention_days" in fields_set:
        candidate.media_cache.retention_days = update.media_cache_retention_days
    if "media_cache_per_species_minimum" in fields_set:
        candidate.media_cache.per_species_minimum = update.media_cache_per_species_minimum

    if "media_cache_per_species_maximum" in fields_set:
        candidate.media_cache.per_species_maximum = update.media_cache_per_species_maximum

    if "media_cache_max_size_mb" in fields_set:
        candidate.media_cache.max_size_mb = update.media_cache_max_size_mb

    if "media_cache_automatic_multi_bird_scan" in fields_set:
        candidate.media_cache.automatic_multi_bird_scan = update.media_cache_automatic_multi_bird_scan

    if "media_cache_bird_scan_mode" in fields_set:
        candidate.media_cache.bird_scan_mode = update.media_cache_bird_scan_mode

    # Location settings
    if "location_latitude" in fields_set:
        candidate.location.latitude = update.location_latitude
    if "location_longitude" in fields_set:
        candidate.location.longitude = update.location_longitude
    if "location_state" in fields_set:
        candidate.location.state = update.location_state
    if "location_country" in fields_set:
        candidate.location.country = update.location_country
    if "location_automatic" in fields_set and update.location_automatic is not None:
        candidate.location.automatic = update.location_automatic
    if "location_weather_unit_system" in fields_set and update.location_weather_unit_system is not None:
        candidate.location.weather_unit_system = update.location_weather_unit_system
    if "location_temperature_unit" in fields_set and update.location_temperature_unit is not None:
        candidate.location.temperature_unit = update.location_temperature_unit

    # BirdWeather settings
    if "birdweather_enabled" in fields_set and update.birdweather_enabled is not None:
        candidate.birdweather.enabled = update.birdweather_enabled
    # Only update token if it's not the redacted placeholder
    if "birdweather_station_token" in fields_set and should_update_secret(update.birdweather_station_token):
        candidate.birdweather.station_token = update.birdweather_station_token

    # Home Assistant weather source (#277)
    if "ha_weather_enabled" in fields_set and update.ha_weather_enabled is not None:
        candidate.ha_weather.enabled = update.ha_weather_enabled
    if "ha_weather_access_token" in fields_set and should_update_secret(update.ha_weather_access_token):
        candidate.ha_weather.access_token = update.ha_weather_access_token
    for _ha_field, _ha_target in (
        ("ha_weather_base_url", "base_url"),
        ("ha_weather_entity", "weather_entity"),
        ("ha_weather_temperature_entity", "temperature_entity"),
        ("ha_weather_wind_speed_entity", "wind_speed_entity"),
        ("ha_weather_wind_direction_entity", "wind_direction_entity"),
        ("ha_weather_cloud_cover_entity", "cloud_cover_entity"),
        ("ha_weather_precipitation_entity", "precipitation_entity"),
        ("ha_weather_rain_entity", "rain_entity"),
        ("ha_weather_snowfall_entity", "snowfall_entity"),
    ):
        if _ha_field in fields_set:
            _ha_value = getattr(update, _ha_field)
            setattr(candidate.ha_weather, _ha_target, (_ha_value or "").strip() or None)

    # eBird settings
    if "ebird_enabled" in fields_set and update.ebird_enabled is not None:
        candidate.ebird.enabled = update.ebird_enabled
    if "ebird_api_key" in fields_set and should_update_secret(update.ebird_api_key):
        candidate.ebird.api_key = update.ebird_api_key
    if "ebird_default_radius_km" in fields_set and update.ebird_default_radius_km is not None:
        candidate.ebird.default_radius_km = update.ebird_default_radius_km
    if "ebird_default_days_back" in fields_set and update.ebird_default_days_back is not None:
        candidate.ebird.default_days_back = update.ebird_default_days_back
    if "ebird_max_results" in fields_set and update.ebird_max_results is not None:
        candidate.ebird.max_results = update.ebird_max_results
    if "ebird_locale" in fields_set and update.ebird_locale is not None:
        candidate.ebird.locale = update.ebird_locale
    # A new install has no eBird key at startup, so the localized names fetched
    # then are nothing. Refresh when the key or the language changes rather than
    # leaving the owner on English until the next restart.
    ebird_naming_changed = any(field in fields_set for field in ("ebird_api_key", "ebird_locale", "ebird_enabled"))

    # iNaturalist settings
    if "inaturalist_enabled" in fields_set and update.inaturalist_enabled is not None:
        candidate.inaturalist.enabled = update.inaturalist_enabled
    if "inaturalist_client_id" in fields_set and should_update_secret(update.inaturalist_client_id):
        candidate.inaturalist.client_id = update.inaturalist_client_id
    if "inaturalist_client_secret" in fields_set and should_update_secret(update.inaturalist_client_secret):
        candidate.inaturalist.client_secret = update.inaturalist_client_secret
    if "inaturalist_default_latitude" in fields_set and update.inaturalist_default_latitude is not None:
        candidate.inaturalist.default_latitude = update.inaturalist_default_latitude
    if "inaturalist_default_longitude" in fields_set and update.inaturalist_default_longitude is not None:
        candidate.inaturalist.default_longitude = update.inaturalist_default_longitude
    if "inaturalist_default_place_guess" in fields_set and update.inaturalist_default_place_guess is not None:
        candidate.inaturalist.default_place_guess = update.inaturalist_default_place_guess

    # Enrichment settings
    if "enrichment_mode" in fields_set and update.enrichment_mode is not None:
        candidate.enrichment.mode = update.enrichment_mode
    if "enrichment_single_provider" in fields_set and update.enrichment_single_provider is not None:
        candidate.enrichment.single_provider = update.enrichment_single_provider
    if "enrichment_summary_source" in fields_set and update.enrichment_summary_source is not None:
        candidate.enrichment.summary_source = update.enrichment_summary_source
    if "enrichment_taxonomy_source" in fields_set and update.enrichment_taxonomy_source is not None:
        candidate.enrichment.taxonomy_source = update.enrichment_taxonomy_source
    if "enrichment_sightings_source" in fields_set and update.enrichment_sightings_source is not None:
        candidate.enrichment.sightings_source = update.enrichment_sightings_source
    if "enrichment_seasonality_source" in fields_set and update.enrichment_seasonality_source is not None:
        candidate.enrichment.seasonality_source = update.enrichment_seasonality_source
    if "enrichment_rarity_source" in fields_set and update.enrichment_rarity_source is not None:
        candidate.enrichment.rarity_source = update.enrichment_rarity_source
    if "enrichment_links_sources" in fields_set and update.enrichment_links_sources is not None:
        candidate.enrichment.links_sources = update.enrichment_links_sources

    # LLM settings
    if "llm_enabled" in fields_set and update.llm_enabled is not None:
        candidate.llm.enabled = update.llm_enabled
    if "llm_provider" in fields_set and update.llm_provider:
        candidate.llm.provider = update.llm_provider
    # Only update API key if it's not the redacted placeholder
    if "llm_api_key" in fields_set and should_update_secret(update.llm_api_key):
        candidate.llm.api_key = update.llm_api_key
    if "llm_model" in fields_set and update.llm_model:
        candidate.llm.model = update.llm_model
    if "llm_analysis_prompt_template" in fields_set and update.llm_analysis_prompt_template is not None:
        template = update.llm_analysis_prompt_template.strip()
        if template:
            candidate.llm.analysis_prompt_template = template
    if "llm_conversation_prompt_template" in fields_set and update.llm_conversation_prompt_template is not None:
        template = update.llm_conversation_prompt_template.strip()
        if template:
            candidate.llm.conversation_prompt_template = template
    if "llm_chart_prompt_template" in fields_set and update.llm_chart_prompt_template is not None:
        template = update.llm_chart_prompt_template.strip()
        if template:
            candidate.llm.chart_prompt_template = template
    if "ai_pricing_json" in fields_set and update.ai_pricing_json is not None:
        candidate.classification.ai_pricing_json = update.ai_pricing_json

    # Telemetry
    if "telemetry_enabled" in fields_set and update.telemetry_enabled is not None:
        candidate.telemetry.enabled = update.telemetry_enabled
    if "telemetry_health_enabled" in fields_set and update.telemetry_health_enabled is not None:
        candidate.telemetry.health_enabled = update.telemetry_health_enabled

    # Authentication
    if "auth_enabled" in fields_set and update.auth_enabled is not None:
        if candidate.auth.enabled != update.auth_enabled:
            audit_events.append(
                (
                    "AUTH_AUDIT: Authentication toggled",
                    {"event_type": "auth_toggled", "enabled": update.auth_enabled, "username": username},
                )
            )
        candidate.auth.enabled = update.auth_enabled

    if "auth_username" in fields_set and update.auth_username is not None and update.auth_username.strip():
        if candidate.auth.username != update.auth_username.strip():
            audit_events.append(
                (
                    "AUTH_AUDIT: Username changed",
                    {
                        "event_type": "username_changed",
                        "old_username": candidate.auth.username,
                        "new_username": update.auth_username.strip(),
                        "changed_by": username,
                    },
                )
            )
        candidate.auth.username = update.auth_username.strip()

    if "auth_password" in fields_set and update.auth_password:
        candidate.auth.password_hash = hash_password(update.auth_password)
        audit_events.append(
            (
                "AUTH_AUDIT: Password changed",
                {"event_type": "password_changed", "username": candidate.auth.username, "changed_by": username},
            )
        )

    if "auth_session_expiry_hours" in fields_set and update.auth_session_expiry_hours is not None:
        candidate.auth.session_expiry_hours = update.auth_session_expiry_hours
    if "trusted_proxy_hosts" in fields_set and update.trusted_proxy_hosts is not None:
        candidate.system.trusted_proxy_hosts = update.trusted_proxy_hosts
    if "beta_garden_animals" in fields_set and update.beta_garden_animals is not None:
        candidate.system.beta_garden_animals = update.beta_garden_animals

    # Public access
    if "public_access_enabled" in fields_set and update.public_access_enabled is not None:
        candidate.public_access.enabled = update.public_access_enabled
    if "public_access_show_camera_names" in fields_set and update.public_access_show_camera_names is not None:
        candidate.public_access.show_camera_names = update.public_access_show_camera_names
    if "public_access_show_ai_conversation" in fields_set and update.public_access_show_ai_conversation is not None:
        candidate.public_access.show_ai_conversation = update.public_access_show_ai_conversation
    if "public_access_allow_clip_downloads" in fields_set and update.public_access_allow_clip_downloads is not None:
        candidate.public_access.allow_clip_downloads = update.public_access_allow_clip_downloads
    if "public_access_show_audio" in fields_set and update.public_access_show_audio is not None:
        candidate.public_access.show_audio = update.public_access_show_audio
    if "public_access_show_snapshots" in fields_set and update.public_access_show_snapshots is not None:
        candidate.public_access.show_snapshots = update.public_access_show_snapshots
    if "public_access_show_clips" in fields_set and update.public_access_show_clips is not None:
        candidate.public_access.show_clips = update.public_access_show_clips
    if "public_access_location_precision" in fields_set and update.public_access_location_precision is not None:
        candidate.public_access.location_precision = update.public_access_location_precision
    if "public_access_historical_days_mode" in fields_set and update.public_access_historical_days_mode is not None:
        candidate.public_access.historical_days_mode = update.public_access_historical_days_mode
    if "public_access_historical_days" in fields_set and update.public_access_historical_days is not None:
        candidate.public_access.show_historical_days = update.public_access_historical_days
    if "public_access_media_days_mode" in fields_set and update.public_access_media_days_mode is not None:
        candidate.public_access.media_days_mode = update.public_access_media_days_mode
    if "public_access_media_historical_days" in fields_set and update.public_access_media_historical_days is not None:
        candidate.public_access.media_historical_days = update.public_access_media_historical_days
    if "public_access_rate_limit_per_minute" in fields_set and update.public_access_rate_limit_per_minute is not None:
        candidate.public_access.rate_limit_per_minute = update.public_access_rate_limit_per_minute
    if "public_access_external_base_url" in fields_set:
        raw_url = (update.public_access_external_base_url or "").strip()
        candidate.public_access.external_base_url = raw_url or None

    if "date_format" in fields_set and update.date_format is not None:
        candidate.date_format = update.date_format
    if "time_format" in fields_set and update.time_format is not None:
        candidate.time_format = update.time_format

    # Notifications - Discord
    if "notifications_discord_enabled" in fields_set and update.notifications_discord_enabled is not None:
        candidate.notifications.discord.enabled = update.notifications_discord_enabled
    # Only update webhook URL if it's not the redacted placeholder
    if "notifications_discord_webhook_url" in fields_set and should_update_secret(
        update.notifications_discord_webhook_url
    ):
        candidate.notifications.discord.webhook_url = update.notifications_discord_webhook_url
    if "notifications_discord_username" in fields_set and update.notifications_discord_username:
        candidate.notifications.discord.username = update.notifications_discord_username

    # Notifications - Pushover
    if "notifications_pushover_enabled" in fields_set and update.notifications_pushover_enabled is not None:
        candidate.notifications.pushover.enabled = update.notifications_pushover_enabled
    # Only update keys/tokens if they're not the redacted placeholder
    if "notifications_pushover_user_key" in fields_set and should_update_secret(update.notifications_pushover_user_key):
        candidate.notifications.pushover.user_key = update.notifications_pushover_user_key
    if "notifications_pushover_api_token" in fields_set and should_update_secret(
        update.notifications_pushover_api_token
    ):
        candidate.notifications.pushover.api_token = update.notifications_pushover_api_token
    if "notifications_pushover_priority" in fields_set and update.notifications_pushover_priority is not None:
        candidate.notifications.pushover.priority = update.notifications_pushover_priority
    if "notifications_pushover_device" in fields_set:
        candidate.notifications.pushover.device = update.notifications_pushover_device or None

    # Notifications - Telegram
    if "notifications_telegram_enabled" in fields_set and update.notifications_telegram_enabled is not None:
        candidate.notifications.telegram.enabled = update.notifications_telegram_enabled
    # Only update bot token if it's not the redacted placeholder
    if "notifications_telegram_bot_token" in fields_set and should_update_secret(
        update.notifications_telegram_bot_token
    ):
        candidate.notifications.telegram.bot_token = update.notifications_telegram_bot_token
    # Only update chat ID if it's not the redacted placeholder
    if "notifications_telegram_chat_id" in fields_set and should_update_secret(update.notifications_telegram_chat_id):
        candidate.notifications.telegram.chat_id = update.notifications_telegram_chat_id

    # Notifications - Email
    if "notifications_email_enabled" in fields_set and update.notifications_email_enabled is not None:
        candidate.notifications.email.enabled = update.notifications_email_enabled
    if "notifications_email_only_on_end" in fields_set and update.notifications_email_only_on_end is not None:
        candidate.notifications.email.only_on_end = update.notifications_email_only_on_end
    if "notifications_email_use_oauth" in fields_set and update.notifications_email_use_oauth is not None:
        candidate.notifications.email.use_oauth = update.notifications_email_use_oauth
    if "notifications_email_oauth_provider" in fields_set and update.notifications_email_oauth_provider is not None:
        candidate.notifications.email.oauth_provider = update.notifications_email_oauth_provider
    if "notifications_email_gmail_client_id" in fields_set and update.notifications_email_gmail_client_id is not None:
        candidate.notifications.email.gmail_client_id = update.notifications_email_gmail_client_id
    if "notifications_email_gmail_client_secret" in fields_set and should_update_secret(
        update.notifications_email_gmail_client_secret
    ):
        candidate.notifications.email.gmail_client_secret = update.notifications_email_gmail_client_secret
    if (
        "notifications_email_outlook_client_id" in fields_set
        and update.notifications_email_outlook_client_id is not None
    ):
        candidate.notifications.email.outlook_client_id = update.notifications_email_outlook_client_id
    if "notifications_email_outlook_client_secret" in fields_set and should_update_secret(
        update.notifications_email_outlook_client_secret
    ):
        candidate.notifications.email.outlook_client_secret = update.notifications_email_outlook_client_secret
    if "notifications_email_smtp_host" in fields_set and update.notifications_email_smtp_host is not None:
        candidate.notifications.email.smtp_host = update.notifications_email_smtp_host
    if "notifications_email_smtp_port" in fields_set and update.notifications_email_smtp_port is not None:
        candidate.notifications.email.smtp_port = update.notifications_email_smtp_port
    if "notifications_email_smtp_username" in fields_set and update.notifications_email_smtp_username is not None:
        candidate.notifications.email.smtp_username = update.notifications_email_smtp_username
    if "notifications_email_smtp_password" in fields_set and should_update_secret(
        update.notifications_email_smtp_password
    ):
        candidate.notifications.email.smtp_password = update.notifications_email_smtp_password
    if "notifications_email_smtp_use_tls" in fields_set and update.notifications_email_smtp_use_tls is not None:
        candidate.notifications.email.smtp_use_tls = update.notifications_email_smtp_use_tls
    if "notifications_email_from_email" in fields_set and update.notifications_email_from_email is not None:
        candidate.notifications.email.from_email = update.notifications_email_from_email
    if "notifications_email_to_email" in fields_set and update.notifications_email_to_email is not None:
        candidate.notifications.email.to_email = update.notifications_email_to_email
    if "notifications_email_include_snapshot" in fields_set and update.notifications_email_include_snapshot is not None:
        candidate.notifications.email.include_snapshot = update.notifications_email_include_snapshot
    if "notifications_email_dashboard_url" in fields_set and update.notifications_email_dashboard_url is not None:
        candidate.notifications.email.dashboard_url = update.notifications_email_dashboard_url
    if "notifications_instance_url" in fields_set and update.notifications_instance_url is not None:
        # Keep the legacy email address in sync, including when the address is cleared.
        candidate.notifications.instance_url = instance_url
        candidate.notifications.email.dashboard_url = instance_url
    if "notifications_link_target" in fields_set and update.notifications_link_target is not None:
        candidate.notifications.link_target = update.notifications_link_target

    # Notifications - Filters
    if "notifications_filter_species_mode" in fields_set and update.notifications_filter_species_mode is not None:
        candidate.notifications.filters.species_mode = update.notifications_filter_species_mode
    if (
        "notifications_filter_species_whitelist" in fields_set
        and update.notifications_filter_species_whitelist is not None
    ):
        candidate.notifications.filters.species_whitelist = update.notifications_filter_species_whitelist
    if "notifications_filter_species_whitelist_structured" in fields_set:
        candidate.notifications.filters.species_whitelist_structured = normalize_blocked_species_entries(
            update.notifications_filter_species_whitelist_structured
        )
    if "notifications_filter_species_blacklist_structured" in fields_set:
        candidate.notifications.filters.species_blacklist_structured = normalize_blocked_species_entries(
            update.notifications_filter_species_blacklist_structured
        )
    if "notifications_filter_min_confidence" in fields_set and update.notifications_filter_min_confidence is not None:
        candidate.notifications.filters.min_confidence = update.notifications_filter_min_confidence
    if (
        "notifications_filter_audio_confirmed_only" in fields_set
        and update.notifications_filter_audio_confirmed_only is not None
    ):
        candidate.notifications.filters.audio_confirmed_only = update.notifications_filter_audio_confirmed_only

    if "notification_language" in fields_set and update.notification_language:
        candidate.notifications.notification_language = update.notification_language

    if "notifications_mode" in fields_set and update.notifications_mode is not None:
        candidate.notifications.mode = update.notifications_mode

    if "notifications_notify_on_insert" in fields_set and update.notifications_notify_on_insert is not None:
        candidate.notifications.notify_on_insert = update.notifications_notify_on_insert
    if "notifications_notify_on_update" in fields_set and update.notifications_notify_on_update is not None:
        candidate.notifications.notify_on_update = update.notifications_notify_on_update
    if "notifications_delay_until_video" in fields_set and update.notifications_delay_until_video is not None:
        candidate.notifications.delay_until_video = update.notifications_delay_until_video
    if "notifications_video_fallback_timeout" in fields_set and update.notifications_video_fallback_timeout is not None:
        candidate.notifications.video_fallback_timeout = update.notifications_video_fallback_timeout
    if (
        "notifications_notification_cooldown_minutes" in fields_set
        and update.notifications_notification_cooldown_minutes is not None
    ):
        candidate.notifications.notification_cooldown_minutes = update.notifications_notification_cooldown_minutes

    # Accessibility
    if "accessibility_high_contrast" in fields_set and update.accessibility_high_contrast is not None:
        candidate.accessibility.high_contrast = update.accessibility_high_contrast
    if "accessibility_dyslexia_font" in fields_set and update.accessibility_dyslexia_font is not None:
        candidate.accessibility.dyslexia_font = update.accessibility_dyslexia_font
    if "accessibility_reduced_motion" in fields_set and update.accessibility_reduced_motion is not None:
        candidate.accessibility.reduced_motion = update.accessibility_reduced_motion
    if "accessibility_live_announcements" in fields_set and update.accessibility_live_announcements is not None:
        candidate.accessibility.live_announcements = update.accessibility_live_announcements

    if "appearance_explorer_view" in fields_set and update.appearance_explorer_view is not None:
        candidate.appearance.explorer_view = update.appearance_explorer_view
    if "appearance_font_theme" in fields_set and update.appearance_font_theme is not None:
        candidate.appearance.font_theme = update.appearance_font_theme
    if "appearance_color_theme" in fields_set and update.appearance_color_theme is not None:
        candidate.appearance.color_theme = update.appearance_color_theme

    if update.species_info_source:
        candidate.species_info_source = update.species_info_source

    return PreparedSettings(
        candidate, inference_provider_changed, execution_mode_changed, ebird_naming_changed, audit_events
    )


def publish_settings(current: BaseModel, candidate: BaseModel) -> None:
    """Preserve imported facade and nested section references without yielding."""
    for field in type(current).model_fields:
        old_value = getattr(current, field)
        new_value = getattr(candidate, field)
        if isinstance(old_value, BaseModel) and isinstance(new_value, BaseModel):
            publish_settings(old_value, new_value)
        else:
            setattr(current, field, new_value)


async def apply_update(current: Settings, candidate: Settings) -> None:
    await candidate.save()
    publish_settings(current, candidate)
