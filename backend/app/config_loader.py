import json
import os
import secrets as secrets_lib
from pathlib import Path
from typing import Any

import structlog

from .config_models import (
    AuthSettings,
    AccessibilitySettings,
    AppearanceSettings,
    BirdWeatherSettings,
    ClassificationSettings,
    DEFAULT_AI_ANALYSIS_PROMPT,
    DEFAULT_AI_CONVERSATION_PROMPT,
    DEFAULT_AI_CHART_PROMPT,
    DEFAULT_TRUSTED_PROXY_HOSTS,
    EbirdSettings,
    EnrichmentSettings,
    FrigateSettings,
    InaturalistSettings,
    LEGACY_DEFAULT_AI_ANALYSIS_PROMPT,
    LEGACY_DEFAULT_AI_CONVERSATION_PROMPT,
    LLMSettings,
    LocationSettings,
    MaintenanceSettings,
    MediaCacheSettings,
    NotificationSettings,
    PublicAccessSettings,
    SystemSettings,
    TelemetrySettings,
    _expand_trusted_hosts,
)

log = structlog.get_logger()


CLASSIFICATION_ENV_OVERRIDES: dict[str, tuple[str, ...]] = {
    "write_frigate_sublabel": ("CLASSIFICATION__WRITE_FRIGATE_SUBLABEL",),
    "personalized_rerank_enabled": ("CLASSIFICATION__PERSONALIZED_RERANK_ENABLED",),
    "auto_video_classification": ("CLASSIFICATION__AUTO_VIDEO_CLASSIFICATION",),
    "video_classification_delay": ("CLASSIFICATION__VIDEO_CLASSIFICATION_DELAY",),
    "video_classification_max_retries": ("CLASSIFICATION__VIDEO_CLASSIFICATION_MAX_RETRIES",),
    "video_classification_retry_interval": ("CLASSIFICATION__VIDEO_CLASSIFICATION_RETRY_INTERVAL",),
    "video_classification_max_concurrent": ("CLASSIFICATION__VIDEO_CLASSIFICATION_MAX_CONCURRENT",),
    "video_classification_failure_threshold": ("CLASSIFICATION__VIDEO_FAILURE_THRESHOLD",),
    "video_classification_failure_window_minutes": ("CLASSIFICATION__VIDEO_FAILURE_WINDOW_MINUTES",),
    "video_classification_failure_cooldown_minutes": ("CLASSIFICATION__VIDEO_FAILURE_COOLDOWN_MINUTES",),
    "video_classification_timeout_seconds": ("CLASSIFICATION__VIDEO_CLASSIFICATION_TIMEOUT_SECONDS",),
    "video_classification_stale_minutes": ("CLASSIFICATION__VIDEO_CLASSIFICATION_STALE_MINUTES",),
    "video_classification_frames": ("CLASSIFICATION__VIDEO_CLASSIFICATION_FRAMES",),
    "strict_non_finite_output": ("CLASSIFICATION__STRICT_NON_FINITE_OUTPUT", "CLASSIFIER_STRICT_NON_FINITE_OUTPUT"),
    "inference_provider": ("CLASSIFICATION__INFERENCE_PROVIDER", "CLASSIFICATION__USE_CUDA"),
    "image_execution_mode": ("CLASSIFICATION__IMAGE_EXECUTION_MODE",),
    "live_worker_count": ("CLASSIFICATION__LIVE_WORKER_COUNT",),
    "background_worker_count": ("CLASSIFICATION__BACKGROUND_WORKER_COUNT",),
    "worker_heartbeat_timeout_seconds": ("CLASSIFICATION__WORKER_HEARTBEAT_TIMEOUT_SECONDS",),
    "worker_hard_deadline_seconds": ("CLASSIFICATION__WORKER_HARD_DEADLINE_SECONDS",),
    "background_worker_hard_deadline_seconds": ("CLASSIFICATION__BACKGROUND_WORKER_HARD_DEADLINE_SECONDS",),
    "worker_ready_timeout_seconds": ("CLASSIFICATION__WORKER_READY_TIMEOUT_SECONDS",),
    "worker_restart_window_seconds": ("CLASSIFICATION__WORKER_RESTART_WINDOW_SECONDS",),
    "worker_restart_threshold": ("CLASSIFICATION__WORKER_RESTART_THRESHOLD",),
    "worker_breaker_cooldown_seconds": ("CLASSIFICATION__WORKER_BREAKER_COOLDOWN_SECONDS",),
    "live_event_stale_drop_seconds": ("CLASSIFICATION__LIVE_EVENT_STALE_DROP_SECONDS",),
    "live_event_coalescing_enabled": ("CLASSIFICATION__LIVE_EVENT_COALESCING_ENABLED",),
    "ai_pricing_json": ("CLASSIFICATION__AI_PRICING_JSON",),
    "max_classification_results": ("CLASSIFICATION__MAX_CLASSIFICATION_RESULTS",),
}


def _classification_overridden_by_env(key: str) -> bool:
    env_keys = CLASSIFICATION_ENV_OVERRIDES.get(key, ())
    return any(env_key in os.environ for env_key in env_keys)


def load_settings_instance(settings_cls: type[Any], config_path: Path) -> Any:
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
    legacy_use_cuda_env = os.environ.get('CLASSIFICATION__USE_CUDA')
    env_inference_provider = os.environ.get('CLASSIFICATION__INFERENCE_PROVIDER')
    if env_inference_provider:
        default_inference_provider = env_inference_provider
    elif legacy_use_cuda_env is not None:
        default_inference_provider = 'cuda' if legacy_use_cuda_env.lower() == 'true' else 'cpu'
    else:
        default_inference_provider = 'auto'
    
    classification_data = {
        'model': 'model.tflite',
        'threshold': 0.7,
        'min_confidence': 0.4,
        'blocked_labels': [],
        'unknown_bird_labels': ["background", "Background"],
        'trust_frigate_sublabel': True,
        'write_frigate_sublabel': os.environ.get('CLASSIFICATION__WRITE_FRIGATE_SUBLABEL', 'true').lower() == 'true',
        'display_common_names': True,
        'scientific_name_primary': False,
        'personalized_rerank_enabled': os.environ.get('CLASSIFICATION__PERSONALIZED_RERANK_ENABLED', 'false').lower() == 'true',
        'auto_video_classification': os.environ.get('CLASSIFICATION__AUTO_VIDEO_CLASSIFICATION', 'false').lower() == 'true',
        'video_classification_delay': int(os.environ.get('CLASSIFICATION__VIDEO_CLASSIFICATION_DELAY', '30')),
        'video_classification_max_retries': int(os.environ.get('CLASSIFICATION__VIDEO_CLASSIFICATION_MAX_RETRIES', '3')),
        'video_classification_retry_interval': int(os.environ.get('CLASSIFICATION__VIDEO_CLASSIFICATION_RETRY_INTERVAL', '15')),
        'video_classification_max_concurrent': int(os.environ.get('CLASSIFICATION__VIDEO_CLASSIFICATION_MAX_CONCURRENT', '5')),
        'video_classification_failure_threshold': int(os.environ.get('CLASSIFICATION__VIDEO_FAILURE_THRESHOLD', '5')),
        'video_classification_failure_window_minutes': int(os.environ.get('CLASSIFICATION__VIDEO_FAILURE_WINDOW_MINUTES', '10')),
        'video_classification_failure_cooldown_minutes': int(os.environ.get('CLASSIFICATION__VIDEO_FAILURE_COOLDOWN_MINUTES', '15')),
        'video_classification_timeout_seconds': int(os.environ.get('CLASSIFICATION__VIDEO_CLASSIFICATION_TIMEOUT_SECONDS', '180')),
        'video_classification_stale_minutes': int(os.environ.get('CLASSIFICATION__VIDEO_CLASSIFICATION_STALE_MINUTES', '15')),
        'video_classification_frames': int(os.environ.get('CLASSIFICATION__VIDEO_CLASSIFICATION_FRAMES', '15')),
        'strict_non_finite_output': (
            os.environ.get(
                'CLASSIFICATION__STRICT_NON_FINITE_OUTPUT',
                os.environ.get('CLASSIFIER_STRICT_NON_FINITE_OUTPUT', 'true'),
            ).lower() == 'true'
        ),
        'inference_provider': default_inference_provider,
        'image_execution_mode': os.environ.get('CLASSIFICATION__IMAGE_EXECUTION_MODE', 'in_process'),
        'live_worker_count': int(os.environ.get('CLASSIFICATION__LIVE_WORKER_COUNT', '2')),
        'background_worker_count': int(os.environ.get('CLASSIFICATION__BACKGROUND_WORKER_COUNT', '1')),
        'worker_heartbeat_timeout_seconds': float(os.environ.get('CLASSIFICATION__WORKER_HEARTBEAT_TIMEOUT_SECONDS', '5.0')),
        'worker_hard_deadline_seconds': float(os.environ.get('CLASSIFICATION__WORKER_HARD_DEADLINE_SECONDS', '35.0')),
        'background_worker_hard_deadline_seconds': float(os.environ.get('CLASSIFICATION__BACKGROUND_WORKER_HARD_DEADLINE_SECONDS', '120.0')),
        'worker_ready_timeout_seconds': float(os.environ.get('CLASSIFICATION__WORKER_READY_TIMEOUT_SECONDS', '20.0')),
        'worker_restart_window_seconds': float(os.environ.get('CLASSIFICATION__WORKER_RESTART_WINDOW_SECONDS', '60.0')),
        'worker_restart_threshold': int(os.environ.get('CLASSIFICATION__WORKER_RESTART_THRESHOLD', '3')),
        'worker_breaker_cooldown_seconds': float(os.environ.get('CLASSIFICATION__WORKER_BREAKER_COOLDOWN_SECONDS', '60.0')),
        'live_event_stale_drop_seconds': float(os.environ.get('CLASSIFICATION__LIVE_EVENT_STALE_DROP_SECONDS', '30.0')),
        'live_event_coalescing_enabled': os.environ.get('CLASSIFICATION__LIVE_EVENT_COALESCING_ENABLED', 'true').lower() == 'true',
        'ai_pricing_json': os.environ.get('CLASSIFICATION__AI_PRICING_JSON', '[]'),
        'max_classification_results': int(os.environ.get('CLASSIFICATION__MAX_CLASSIFICATION_RESULTS', '5')),
    }
    
    # Media cache settings
    media_cache_data = {
        'enabled': os.environ.get('MEDIA_CACHE__ENABLED', 'true').lower() == 'true',
        'cache_snapshots': os.environ.get('MEDIA_CACHE__CACHE_SNAPSHOTS', 'true').lower() == 'true',
        'cache_clips': os.environ.get('MEDIA_CACHE__CACHE_CLIPS', 'false').lower() == 'true',  # Disabled by default to avoid blocking
        'high_quality_event_snapshots': os.environ.get('MEDIA_CACHE__HIGH_QUALITY_EVENT_SNAPSHOTS', 'false').lower() == 'true',
        'high_quality_event_snapshot_jpeg_quality': int(os.environ.get('MEDIA_CACHE__HIGH_QUALITY_EVENT_SNAPSHOT_JPEG_QUALITY', '95')),
        'retention_days': int(os.environ.get('MEDIA_CACHE__RETENTION_DAYS', '0')),
    }
    
    # Location settings
    location_data = {
        'latitude': None,
        'longitude': None,
        'automatic': True,
        'weather_unit_system': 'metric'
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
            'video_fallback_timeout': int(os.environ.get('NOTIFICATIONS__VIDEO_FALLBACK_TIMEOUT', '45')),
            'notification_cooldown_minutes': int(os.environ.get('NOTIFICATIONS__NOTIFICATION_COOLDOWN_MINUTES', '0'))
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
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
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
                cls_file = file_data['classification']
                if (
                    'inference_provider' not in cls_file
                    and 'use_cuda' in cls_file
                ):
                    # Back-compat mapping for older configs (pre-provider selector).
                    cls_file = dict(cls_file)
                    cls_file['inference_provider'] = 'cuda' if bool(cls_file.get('use_cuda')) else 'cpu'
                for key, value in cls_file.items():
                    if value is None:  # Guard against null values in config
                        continue
                    # Keep env vars authoritative for explicitly supported classification overrides.
                    if _classification_overridden_by_env(key):
                        continue
                    classification_data[key] = value
    
            if 'media_cache' in file_data:
                for key, value in file_data['media_cache'].items():
                    env_key = f'MEDIA_CACHE__{key.upper()}'
                    if env_key not in os.environ:
                        media_cache_data[key] = value
                        
            if 'location' in file_data:
                location_file = file_data['location']
                if (
                    isinstance(location_file, dict)
                    and 'weather_unit_system' not in location_file
                    and location_file.get('temperature_unit') is not None
                ):
                    legacy_temperature_unit = str(location_file.get('temperature_unit')).strip().lower()
                    location_data['weather_unit_system'] = (
                        'imperial' if legacy_temperature_unit == 'fahrenheit' else 'metric'
                    )
                for key, value in location_file.items():
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
    
            log.info("Loaded config from file", path=str(config_path))
        except Exception as e:
            log.warning("Failed to load config from file", path=str(config_path), error=str(e))
    
    log.info("MQTT config", server=frigate_data['mqtt_server'], port=frigate_data['mqtt_port'], auth=frigate_data['mqtt_auth'])
    log.info("Maintenance config", retention_days=maintenance_data['retention_days'])
    log.info("Classification config",
             threshold=classification_data['threshold'],
             min_confidence=classification_data['min_confidence'],
             blocked_labels=classification_data['blocked_labels'],
             unknown_bird_labels=classification_data['unknown_bird_labels'],
             trust_frigate_sublabel=classification_data['trust_frigate_sublabel'],
             write_frigate_sublabel=classification_data['write_frigate_sublabel'],
             display_common_names=classification_data['display_common_names'],
             scientific_name_primary=classification_data['scientific_name_primary'],
             personalized_rerank_enabled=classification_data.get('personalized_rerank_enabled', False),
             inference_provider=classification_data.get('inference_provider', 'auto'))
    log.info("Media cache config",
             enabled=media_cache_data['enabled'],
             cache_snapshots=media_cache_data['cache_snapshots'],
             cache_clips=media_cache_data['cache_clips'],
             high_quality_event_snapshots=media_cache_data['high_quality_event_snapshots'],
             high_quality_event_snapshot_jpeg_quality=media_cache_data['high_quality_event_snapshot_jpeg_quality'],
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
    
    return settings_cls(
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
