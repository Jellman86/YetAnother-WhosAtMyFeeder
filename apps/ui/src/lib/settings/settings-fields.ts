import { SETTINGS_TAB_ORDER, type SettingsTab } from './settings-route';

/**
 * Where each saved setting lives in Settings. The save model uses it to name the tabs that hold
 * unsaved changes, and to send a rejected value back to the field that shows it.
 *
 * A field is matched exactly first, then by its longest matching prefix, so a whole family such as
 * `notifications_` has one home and an exception (`garden_notifications_`) can still be named.
 */
const EXACT_FIELD_TABS: Readonly<Record<string, SettingsTab>> = {
    frigate_url: 'connection',
    frigate_ingest_labels: 'connection',
    frigate_external_url: 'connection',
    cameras: 'connection',
    camera_roles: 'connection',
    garden_cameras: 'connection',
    garden_motion_cameras: 'connection',
    nest_dedupe_minutes: 'connection',
    classification_image_source: 'connection',
    recording_frame_delay_seconds: 'connection',
    clips_enabled: 'connection',
    frigate_missing_behavior: 'data',
    retention_days: 'data',
    auto_analyze_unknowns: 'data',
    classification_threshold: 'detection',
    classification_min_confidence: 'detection',
    live_worker_count: 'detection',
    background_worker_count: 'detection',
    trust_frigate_sublabel: 'detection',
    write_frigate_sublabel: 'detection',
    personalized_rerank_enabled: 'detection',
    auto_video_classification: 'detection',
    image_execution_mode: 'detection',
    inference_provider: 'detection',
    blocked_labels: 'detection',
    blocked_species: 'detection',
    camera_audio_mapping: 'integrations',
    trusted_proxy_hosts: 'security',
    notification_language: 'notifications',
    strict_non_finite_output: 'debug',
    beta_garden_animals: 'beta',
    display_common_names: 'appearance',
    scientific_name_primary: 'appearance',
    explorer_view: 'appearance',
    date_format: 'appearance',
    time_format: 'appearance',
    font_theme: 'appearance',
    color_theme: 'appearance'
};

const PREFIX_FIELD_TABS: ReadonlyArray<readonly [string, SettingsTab]> = [
    ['mqtt_', 'connection'],
    ['recording_clip_', 'connection'],
    ['telemetry_', 'connection'],
    ['video_classification_', 'detection'],
    ['range_filter_', 'detection'],
    ['bird_model_region_', 'detection'],
    ['bird_crop_', 'detection'],
    ['garden_notification', 'notifications'],
    ['notifications_', 'notifications'],
    ['garden_', 'beta'],
    ['birdnet_', 'integrations'],
    ['audio_', 'integrations'],
    ['birdweather_', 'integrations'],
    ['ha_weather_', 'integrations'],
    ['ebird_', 'integrations'],
    ['inaturalist_', 'integrations'],
    ['location_', 'integrations'],
    ['enrichment_', 'enrichment'],
    ['llm_', 'ai'],
    ['ai_', 'ai'],
    ['auth_', 'security'],
    ['public_access_', 'security'],
    ['media_cache_', 'data'],
    ['maintenance_', 'data'],
    ['auto_purge_', 'data'],
    ['accessibility_', 'accessibility']
];

/** The tab that owns a saved setting, or null for a field Settings does not show. */
export function settingsFieldTab(field: string): SettingsTab | null {
    const exact = EXACT_FIELD_TABS[field];
    if (exact) return exact;
    let best: readonly [string, SettingsTab] | null = null;
    for (const entry of PREFIX_FIELD_TABS) {
        if (field.startsWith(entry[0]) && (!best || entry[0].length > best[0].length)) best = entry;
    }
    return best ? best[1] : null;
}

export interface UnsavedSummary {
    /** How many saved settings the draft would change. */
    count: number;
    /** The tabs holding those changes, in navigation order. */
    tabs: SettingsTab[];
}

/** Summarises changed settings, given by field name, as a count and the tabs that hold them. */
export function summarizeUnsaved(changedFields: readonly string[]): UnsavedSummary {
    const fields = [...new Set(changedFields)];
    const owners = new Set(fields.map(settingsFieldTab).filter((tab): tab is SettingsTab => tab !== null));
    return {
        count: fields.length,
        tabs: SETTINGS_TAB_ORDER.filter((tab) => owners.has(tab))
    };
}

/** A draft value beside the value saved for the same field. */
export interface FieldComparison {
    field: string;
    draft: unknown;
    saved: unknown;
}

/** The fields whose draft differs from what is saved. Lists and objects compare by content. */
export function changedFields(comparisons: readonly FieldComparison[]): string[] {
    return comparisons
        .filter(({ draft, saved }) => (typeof draft === 'object' || typeof saved === 'object'
            ? JSON.stringify(draft) !== JSON.stringify(saved)
            : draft !== saved))
        .map(({ field }) => field);
}

/** The label a field shows under, and the input that holds it, for pointing at a refused value. */
export interface SettingsFieldPlace {
    labelKey: string;
    inputId: string;
}

const FIELD_PLACES: Readonly<Record<string, SettingsFieldPlace>> = {
    frigate_url: { labelKey: 'settings.frigate.url', inputId: 'frigate-url' },
    frigate_ingest_labels: { labelKey: 'settings.frigate.ingest_labels', inputId: 'frigate-ingest-labels' },
    frigate_external_url: { labelKey: 'settings.frigate.external_url', inputId: 'frigate-external-url' },
    mqtt_server: { labelKey: 'settings.frigate.mqtt_broker', inputId: 'mqtt-server' },
    mqtt_port: { labelKey: 'settings.frigate.mqtt_port', inputId: 'mqtt-port' },
    mqtt_username: { labelKey: 'settings.frigate.mqtt_user', inputId: 'mqtt-username' },
    recording_frame_delay_seconds: { labelKey: 'settings.frigate.recording_frame_delay', inputId: 'recording-frame-delay' },
    recording_clip_before_seconds: { labelKey: 'settings.frigate.full_visit_before', inputId: 'recording-clip-before' },
    recording_clip_after_seconds: { labelKey: 'settings.frigate.full_visit_after', inputId: 'recording-clip-after' },
    video_classification_delay: { labelKey: 'settings.detection.video_delay', inputId: 'video-delay' },
    video_classification_max_retries: { labelKey: 'settings.detection.video_retries', inputId: 'video-retries' },
    video_classification_frames: { labelKey: 'settings.detection.video_frames', inputId: 'video-frames' },
    maintenance_max_concurrent: { labelKey: 'settings.data.maintenance_max_concurrent', inputId: 'maintenance-max-concurrent' },
    garden_labels: { labelKey: 'garden.labels', inputId: 'garden-labels' },
    garden_motion_confidence: { labelKey: 'garden.confidence', inputId: 'garden-motion-confidence' },
    garden_naming_threshold: { labelKey: 'settings.beta.garden_naming_threshold', inputId: 'garden-naming-threshold' },
    birdnet_url: { labelKey: 'settings.integrations.birdnet.internal_url_label', inputId: 'birdnet-url' },
    birdnet_external_url: { labelKey: 'settings.integrations.birdnet.external_url_label', inputId: 'birdnet-external-url' },
    audio_topic: { labelKey: 'settings.integrations.birdnet.mqtt_topic', inputId: 'audio-topic' },
    audio_buffer_hours: { labelKey: 'settings.integrations.birdnet.audio_buffer_hours', inputId: 'audio-buffer' },
    audio_correlation_window_seconds: { labelKey: 'settings.integrations.birdnet.match_window_seconds', inputId: 'correlation-window' },
    inaturalist_default_latitude: { labelKey: 'settings.integrations.inaturalist.default_latitude', inputId: 'inat-lat' },
    inaturalist_default_longitude: { labelKey: 'settings.integrations.inaturalist.default_longitude', inputId: 'inat-lon' },
    inaturalist_default_place_guess: { labelKey: 'settings.integrations.inaturalist.default_place_guess', inputId: 'inat-place' },
    ebird_default_radius_km: { labelKey: 'settings.integrations.ebird.radius', inputId: 'ebird-radius' },
    ebird_default_days_back: { labelKey: 'settings.integrations.ebird.days_back', inputId: 'ebird-days' },
    ebird_max_results: { labelKey: 'settings.integrations.ebird.max_results', inputId: 'ebird-max-results' },
    ebird_locale: { labelKey: 'settings.integrations.ebird.locale', inputId: 'ebird-locale' },
    ha_weather_base_url: { labelKey: 'settings.integrations.ha_weather.base_url', inputId: 'ha-weather-url' },
    ha_weather_entity: { labelKey: 'settings.integrations.ha_weather.entity', inputId: 'ha-weather-entity' },
    ha_weather_illuminance_entity: { labelKey: 'settings.integrations.ha_weather.illuminance', inputId: 'ha-weather-illuminance' },
    location_latitude: { labelKey: 'settings.location.latitude', inputId: 'location-lat' },
    location_longitude: { labelKey: 'settings.location.longitude', inputId: 'location-lon' },
    auth_username: { labelKey: 'settings.auth.username', inputId: 'auth-username' },
    auth_password: { labelKey: 'settings.auth.password', inputId: 'auth-password' },
    auth_session_expiry_hours: { labelKey: 'settings.auth.session_expiry', inputId: 'auth-expiry' },
    public_access_rate_limit_per_minute: { labelKey: 'settings.public_access.rate_limit', inputId: 'public-rate' },
    public_access_external_base_url: { labelKey: 'settings.public_access.share_base_url', inputId: 'public-share-base-url' },
    notifications_instance_url: { labelKey: 'settings.notifications.instance_url', inputId: 'notification-instance-url' }
};

/** Where a field is shown, or null for one without its own input (the tab is then the pointer). */
export function settingsFieldPlace(field: string): SettingsFieldPlace | null {
    return FIELD_PLACES[field] ?? null;
}
