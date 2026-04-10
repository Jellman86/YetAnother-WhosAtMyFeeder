import { API_BASE, apiFetch, handleResponse } from './core';
import type { BirdModelRegionOverride } from '../settings/bird-model-region-override';
import type { CropModelOverride, CropSourceOverride } from '../settings/crop-overrides';

export interface BlockedSpeciesEntry {
    scientific_name?: string | null;
    common_name?: string | null;
    taxa_id?: number | null;
}

export interface Settings {
    frigate_url: string;
    mqtt_server: string;
    mqtt_port: number;
    mqtt_auth: boolean;
    mqtt_username?: string;
    mqtt_password?: string;
    birdnet_enabled: boolean;
    audio_topic: string;
    camera_audio_mapping: Record<string, string>;
    clips_enabled: boolean;
    recording_clip_enabled: boolean;
    recording_clip_before_seconds: number;
    recording_clip_after_seconds: number;
    classification_threshold: number;
    classification_min_confidence: number;
    cameras: string[];
    retention_days: number;
    auto_purge_missing_clips: boolean;
    auto_purge_missing_snapshots: boolean;
    auto_analyze_unknowns: boolean;
    blocked_labels: string[];
    blocked_species: BlockedSpeciesEntry[];
    trust_frigate_sublabel: boolean;
    write_frigate_sublabel: boolean;
    display_common_names: boolean;
    scientific_name_primary: boolean;
    personalized_rerank_enabled: boolean;
    auto_video_classification: boolean;
    video_classification_delay: number;
    video_classification_max_retries: number;
    video_classification_max_concurrent: number;
    video_classification_frames: number;
    bird_model_region_override?: BirdModelRegionOverride;
    crop_model_overrides?: Record<string, CropModelOverride>;
    crop_source_overrides?: Record<string, CropSourceOverride>;
    image_execution_mode?: 'in_process' | 'subprocess' | string;
    strict_non_finite_output?: boolean;
    inference_provider: 'auto' | 'cpu' | 'cuda' | 'intel_gpu' | 'intel_cpu' | string;
    ai_pricing_json: string;
    video_classification_circuit_open?: boolean;
    video_classification_circuit_until?: string | null;
    video_classification_circuit_failures?: number;
    audio_buffer_hours?: number;
    audio_correlation_window_seconds?: number;
    media_cache_enabled: boolean;
    media_cache_snapshots: boolean;
    media_cache_clips: boolean;
    media_cache_high_quality_event_snapshots: boolean;
    media_cache_high_quality_event_snapshot_bird_crop: boolean;
    media_cache_high_quality_event_snapshot_jpeg_quality: number;
    media_cache_retention_days: number;
    location_latitude?: number | null;
    location_longitude?: number | null;
    location_state?: string | null;
    location_country?: string | null;
    location_automatic?: boolean;
    location_weather_unit_system?: 'metric' | 'imperial' | 'british' | string;
    location_temperature_unit?: 'celsius' | 'fahrenheit' | string;
    birdweather_enabled: boolean;
    birdweather_station_token?: string | null;
    ebird_enabled?: boolean;
    ebird_api_key?: string | null;
    ebird_default_radius_km?: number;
    ebird_default_days_back?: number;
    ebird_max_results?: number;
    ebird_locale?: string;
    inaturalist_enabled?: boolean;
    inaturalist_client_id?: string | null;
    inaturalist_client_secret?: string | null;
    inaturalist_default_latitude?: number | null;
    inaturalist_default_longitude?: number | null;
    inaturalist_default_place_guess?: string | null;
    inaturalist_connected_user?: string | null;
    enrichment_mode?: string;
    enrichment_single_provider?: string;
    enrichment_summary_source?: string;
    enrichment_taxonomy_source?: string;
    enrichment_sightings_source?: string;
    enrichment_seasonality_source?: string;
    enrichment_rarity_source?: string;
    enrichment_links_sources?: string[];
    llm_enabled: boolean;
    llm_ready?: boolean;
    llm_provider?: string;
    llm_api_key?: string;
    llm_model?: string;
    llm_analysis_prompt_template?: string;
    llm_conversation_prompt_template?: string;
    llm_chart_prompt_template?: string;
    telemetry_enabled: boolean;
    telemetry_installation_id?: string;
    telemetry_platform?: string;
    notifications_discord_enabled: boolean;
    notifications_discord_webhook_url?: string | null;
    notifications_discord_username: string;
    notifications_pushover_enabled: boolean;
    notifications_pushover_user_key?: string | null;
    notifications_pushover_api_token?: string | null;
    notifications_pushover_priority: number;
    notifications_pushover_device?: string | null;
    notifications_telegram_enabled: boolean;
    notifications_telegram_bot_token?: string | null;
    notifications_telegram_chat_id?: string | null;
    notifications_email_enabled: boolean;
    notifications_email_only_on_end: boolean;
    notifications_email_use_oauth: boolean;
    notifications_email_oauth_provider?: string | null;
    notifications_email_connected_email?: string | null;
    notifications_email_gmail_client_id?: string | null;
    notifications_email_gmail_client_secret?: string | null;
    notifications_email_outlook_client_id?: string | null;
    notifications_email_outlook_client_secret?: string | null;
    notifications_email_smtp_host?: string | null;
    notifications_email_smtp_port: number;
    notifications_email_smtp_username?: string | null;
    notifications_email_smtp_password?: string | null;
    notifications_email_smtp_use_tls: boolean;
    notifications_email_from_email?: string | null;
    notifications_email_to_email?: string | null;
    notifications_email_include_snapshot: boolean;
    notifications_email_dashboard_url?: string | null;
    notifications_filter_species_whitelist: string[];
    notifications_filter_min_confidence: number;
    notifications_filter_audio_confirmed_only: boolean;
    notification_language: string;
    notifications_mode: string;
    notifications_notify_on_insert: boolean;
    notifications_notify_on_update: boolean;
    notifications_delay_until_video: boolean;
    notifications_video_fallback_timeout: number;
    notifications_notification_cooldown_minutes: number;
    notifications?: {
        discord?: { enabled: boolean };
        pushover?: { enabled: boolean };
        telegram?: { enabled: boolean };
        email?: { enabled: boolean };
    };
    accessibility_high_contrast: boolean;
    accessibility_dyslexia_font: boolean;
    accessibility_reduced_motion: boolean;
    accessibility_zen_mode: boolean;
    accessibility_live_announcements: boolean;
    appearance_font_theme?: string;
    appearance_color_theme?: string;
    auth_enabled: boolean;
    auth_username: string;
    auth_has_password: boolean;
    auth_session_expiry_hours: number;
    auth_password?: string;
    trusted_proxy_hosts?: string[];
    debug_ui_enabled?: boolean;
    public_access_enabled: boolean;
    public_access_show_camera_names: boolean;
    public_access_show_ai_conversation?: boolean;
    public_access_allow_clip_downloads?: boolean;
    public_access_historical_days_mode?: string;
    public_access_historical_days: number;
    public_access_media_days_mode?: string;
    public_access_media_historical_days: number;
    public_access_rate_limit_per_minute: number;
    public_access_external_base_url?: string | null;
    species_info_source?: string;
    date_format?: string;
}

export type UpdateSettings = Partial<Settings>;

export interface SettingsUpdate extends Partial<Settings> {}

export async function fetchSettings(): Promise<Settings> {
    const response = await apiFetch(`${API_BASE}/settings`);
    return handleResponse<Settings>(response);
}

export async function updateSettings(settings: SettingsUpdate): Promise<{ status: string }> {
    const response = await apiFetch(`${API_BASE}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
    });
    return handleResponse<{ status: string }>(response);
}
