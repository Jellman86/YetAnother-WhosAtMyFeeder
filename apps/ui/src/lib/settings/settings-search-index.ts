import { settingsSectionOfPart, type SettingsPart, type SettingsSection } from './settings-route';
import { settingsMoreId } from './settings-more';

/**
 * Every setting the search can find, and where it is on the page. A section's code loads only when
 * the section opens, so the search cannot read the settings from the page: this list is what it
 * searches, in the reader's language, through the same translation keys the rows show.
 *
 * It is held to the markup by tests:
 * - `settings-search-index.test.ts` reads every component under `components/settings`, subfolders
 *   included, and fails when a row, slider or card has no static id or no entry; when an entry names
 *   a different label or help key than the markup; when an anchor or disclosure is not in the markup;
 *   when a row built in a loop, or a control outside any row, is not declared there with the entries
 *   that find it; or when a key is missing from any language;
 * - `settings-reading-hierarchy.layout.test.ts` holds each card's heading level to where its entry
 *   says it is;
 * - `browser-tests/settings-search.spec.ts` opens every entry in the real page and fails unless
 *   focus lands on that setting's own control.
 * What they cannot see is a setting drawn with none of the kit's rows or controls, nor a plain
 * input, select or textarea: nothing in Settings is built that way today.
 */
export interface SettingsSearchEntry {
    /** The id of the element a result lands on: a row's label, a slider, or a group. */
    anchor: string;
    part: SettingsPart;
    /** A group is a card of settings; a result for one lands on its heading. */
    kind?: 'group';
    labelKey: string;
    helpKey?: string;
    /** Closable sections that must open to show it, outermost first. */
    disclosures?: readonly string[];
    /**
     * The entry whose switch shows this one, for a setting that is only on the page while that
     * switch is on. A result lands there when the setting itself is not shown.
     */
    behind?: string;
    /** English words people look for that the label and help do not say. */
    keywords?: readonly string[];
}

const more = (section: SettingsSection): string => settingsMoreId(section);

export const SETTINGS_SEARCH_INDEX: readonly SettingsSearchEntry[] = [
    { anchor: 'settings-group-ai-connection', part: 'ai', kind: 'group', labelKey: 'settings.ai.connection_title', disclosures: [more('sharing')], behind: 'setting-llm-enabled' },
    { anchor: 'setting-llm-enabled', part: 'ai', labelKey: 'settings.llm.enabled', helpKey: 'settings.llm.enabled_desc', disclosures: [more('sharing')], keywords: ['ai', 'gemini', 'openai', 'llm', 'chatgpt', 'analysis'] },
    { anchor: 'setting-llm-provider', part: 'ai', labelKey: 'settings.llm.provider', disclosures: [more('sharing')], behind: 'setting-llm-enabled' },
    { anchor: 'setting-llm-api-key', part: 'ai', labelKey: 'settings.llm.api_key', disclosures: [more('sharing')], behind: 'setting-llm-enabled', keywords: ['gemini', 'openai', 'token'] },
    { anchor: 'setting-llm-model', part: 'ai', labelKey: 'settings.llm.model', disclosures: [more('sharing')], behind: 'setting-llm-enabled' },
    { anchor: 'setting-ai-pricing', part: 'ai', labelKey: 'settings.ai.pricing_json', helpKey: 'settings.ai.pricing_help', disclosures: [more('sharing'), 'ai-pricing-and-prompts'], behind: 'setting-llm-enabled', keywords: ['cost', 'price', 'tokens'] },
    { anchor: 'setting-llm-prompt-style', part: 'ai', labelKey: 'settings.debug.llm_prompt_style_label', helpKey: 'settings.ai.prompt_style_desc', disclosures: [more('sharing'), 'ai-pricing-and-prompts'], behind: 'setting-llm-enabled' },
    { anchor: 'setting-llm-prompt-analysis', part: 'ai', labelKey: 'settings.debug.llm_prompt_analysis', helpKey: 'settings.debug.llm_prompt_analysis_hint', disclosures: [more('sharing'), 'ai-pricing-and-prompts'], behind: 'setting-llm-enabled' },
    { anchor: 'setting-llm-prompt-conversation', part: 'ai', labelKey: 'settings.debug.llm_prompt_conversation', helpKey: 'settings.debug.llm_prompt_conversation_hint', disclosures: [more('sharing'), 'ai-pricing-and-prompts'], behind: 'setting-llm-enabled' },
    { anchor: 'setting-llm-prompt-chart', part: 'ai', labelKey: 'settings.debug.llm_prompt_chart', helpKey: 'settings.debug.llm_prompt_chart_hint', disclosures: [more('sharing'), 'ai-pricing-and-prompts'], behind: 'setting-llm-enabled' },
    { anchor: 'settings-group-accessibility-device', part: 'accessibility', kind: 'group', labelKey: 'settings.accessibility.device_title' },
    { anchor: 'setting-high-contrast', part: 'accessibility', labelKey: 'settings.accessibility.high_contrast', helpKey: 'settings.accessibility.high_contrast_desc', keywords: ['contrast', 'vision', 'black'] },
    { anchor: 'setting-dyslexia-font', part: 'accessibility', labelKey: 'settings.accessibility.dyslexia_font', keywords: ['dyslexia', 'opendyslexic', 'reading'] },
    { anchor: 'setting-reduced-motion', part: 'accessibility', labelKey: 'settings.accessibility.reduced_motion', helpKey: 'settings.accessibility.reduced_motion_desc', keywords: ['animation', 'motion'] },
    { anchor: 'setting-live-announcements', part: 'accessibility', labelKey: 'settings.accessibility.live_announcements', helpKey: 'settings.accessibility.live_announcements_desc', keywords: ['screen reader', 'announce', 'aria'] },
    { anchor: 'settings-group-accessibility-defaults', part: 'accessibility', kind: 'group', labelKey: 'settings.accessibility.defaults_title', disclosures: [more('display')] },
    { anchor: 'setting-default-high-contrast', part: 'accessibility', labelKey: 'settings.accessibility.high_contrast', helpKey: 'settings.accessibility.high_contrast_desc', disclosures: [more('display')] },
    { anchor: 'setting-default-dyslexia-font', part: 'accessibility', labelKey: 'settings.accessibility.dyslexia_font', disclosures: [more('display')] },
    { anchor: 'setting-default-reduced-motion', part: 'accessibility', labelKey: 'settings.accessibility.reduced_motion', helpKey: 'settings.accessibility.reduced_motion_desc', disclosures: [more('display')] },
    { anchor: 'setting-default-live-announcements', part: 'accessibility', labelKey: 'settings.accessibility.live_announcements', helpKey: 'settings.accessibility.live_announcements_desc', disclosures: [more('display')] },
    { anchor: 'settings-group-tabs-appearance', part: 'appearance', kind: 'group', labelKey: 'settings.tabs.appearance' },
    { anchor: 'setting-theme', part: 'appearance', labelKey: 'theme.title', helpKey: 'settings.theme_scope', keywords: ['dark', 'light', 'mode', 'night'] },
    { anchor: 'setting-text-size', part: 'appearance', labelKey: 'settings.text_size.label', helpKey: 'settings.text_size.desc', keywords: ['font size', 'larger', 'bigger', 'zoom'] },
    { anchor: 'setting-language', part: 'appearance', labelKey: 'settings.language_selector', helpKey: 'settings.language_desc', keywords: ['english', 'german', 'french', 'spanish', 'translate', 'locale'] },
    { anchor: 'settings-group-appearance-more', part: 'appearance', kind: 'group', labelKey: 'settings.appearance.more_title', disclosures: [more('display')] },
    { anchor: 'setting-explorer-view', part: 'appearance', labelKey: 'settings.explorer_view.label', helpKey: 'settings.explorer_view.desc', disclosures: [more('display')], keywords: ['cards', 'list', 'layout'] },
    { anchor: 'setting-date-format', part: 'appearance', labelKey: 'settings.date_format.label', helpKey: 'settings.date_format.desc', disclosures: [more('display')], keywords: ['day', 'month', 'year'] },
    { anchor: 'setting-time-format', part: 'appearance', labelKey: 'settings.time_format.label', helpKey: 'settings.time_format.desc', disclosures: [more('display')], keywords: ['12 hour', '24 hour', 'am', 'pm', 'clock'] },
    { anchor: 'setting-naming', part: 'appearance', labelKey: 'settings.detection.naming_title', disclosures: [more('display')], keywords: ['scientific', 'latin', 'common name'] },
    { anchor: 'setting-font-theme', part: 'appearance', labelKey: 'theme.font_title', helpKey: 'theme.font_desc', disclosures: [more('display'), 'appearance-typography-and-colour'], keywords: ['font', 'typeface', 'serif', 'classic'] },
    { anchor: 'setting-color-theme', part: 'appearance', labelKey: 'theme.color_title', helpKey: 'theme.color_desc', disclosures: [more('display'), 'appearance-typography-and-colour'], keywords: ['colour', 'color', 'accent', 'palette'] },
    { anchor: 'settings-group-auth', part: 'security', kind: 'group', labelKey: 'settings.auth.title', keywords: ['login', 'password', 'sign in', 'account', 'security', 'user'] },
    { anchor: 'setting-auth-avatar', part: 'security', labelKey: 'settings.auth.avatar', helpKey: 'settings.auth.avatar_desc', behind: 'settings-group-auth' },
    { anchor: 'setting-auth-username', part: 'security', labelKey: 'settings.auth.username', behind: 'settings-group-auth' },
    { anchor: 'setting-auth-password', part: 'security', labelKey: 'settings.auth.password', behind: 'settings-group-auth', keywords: ['change password', 'login'] },
    { anchor: 'setting-auth-password-confirm', part: 'security', labelKey: 'settings.auth.password_confirm', behind: 'settings-group-auth' },
    { anchor: 'setting-auth-expiry', part: 'security', labelKey: 'settings.auth.session_expiry', disclosures: ['auth-session-and-proxy'], behind: 'settings-group-auth', keywords: ['session', 'logout', 'timeout'] },
    { anchor: 'setting-trusted-proxies', part: 'security', labelKey: 'settings.auth.trusted_proxies', helpKey: 'settings.auth.trusted_proxies_desc', disclosures: ['auth-session-and-proxy'], behind: 'settings-group-auth', keywords: ['reverse proxy', 'nginx', 'traefik', 'cloudflare'] },
    { anchor: 'settings-group-public-access', part: 'security', kind: 'group', labelKey: 'settings.public_access.title', keywords: ['guest', 'share', 'public', 'anonymous', 'visitors'] },
    { anchor: 'setting-public-show-cameras', part: 'security', labelKey: 'settings.public_access.show_camera_names', helpKey: 'settings.public_access.show_camera_names_desc', behind: 'settings-group-public-access' },
    { anchor: 'setting-public-show-audio', part: 'security', labelKey: 'settings.public_access.show_audio', helpKey: 'settings.public_access.show_audio_desc', behind: 'settings-group-public-access' },
    { anchor: 'setting-public-show-snapshots', part: 'security', labelKey: 'settings.public_access.show_snapshots', helpKey: 'settings.public_access.show_snapshots_desc', behind: 'settings-group-public-access' },
    { anchor: 'setting-public-show-clips', part: 'security', labelKey: 'settings.public_access.show_clips', helpKey: 'settings.public_access.show_clips_desc', behind: 'settings-group-public-access' },
    { anchor: 'setting-public-location-precision', part: 'security', labelKey: 'settings.public_access.location_precision', helpKey: 'settings.public_access.location_precision_desc', behind: 'settings-group-public-access' },
    { anchor: 'setting-public-show-ai', part: 'security', labelKey: 'settings.public_access.show_ai_conversation', helpKey: 'settings.public_access.show_ai_conversation_desc', behind: 'settings-group-public-access' },
    { anchor: 'setting-public-clip-download', part: 'security', labelKey: 'settings.public_access.allow_clip_downloads', helpKey: 'settings.public_access.allow_clip_downloads_desc', behind: 'settings-group-public-access' },
    { anchor: 'setting-public-history-days', part: 'security', labelKey: 'settings.public_access.history_days', helpKey: 'settings.public_access.window_effective', disclosures: ['public-access-windows'], behind: 'settings-group-public-access' },
    { anchor: 'setting-public-media-days', part: 'security', labelKey: 'settings.public_access.media_days', helpKey: 'settings.public_access.window_effective', disclosures: ['public-access-windows'], behind: 'settings-group-public-access' },
    { anchor: 'setting-public-rate-limit', part: 'security', labelKey: 'settings.public_access.rate_limit', disclosures: ['public-access-windows'], behind: 'settings-group-public-access', keywords: ['throttle', 'requests'] },
    { anchor: 'setting-public-share-base-url', part: 'security', labelKey: 'settings.public_access.share_base_url', helpKey: 'settings.public_access.share_base_url_desc', disclosures: ['public-access-windows'], behind: 'settings-group-public-access' },
    { anchor: 'settings-group-integrations-birdnet', part: 'connection', kind: 'group', labelKey: 'settings.integrations.birdnet.title', disclosures: [more('cameras')], keywords: ['audio', 'sound', 'song', 'call', 'microphone', 'birdnet'] },
    { anchor: 'setting-birdnet-url', part: 'connection', labelKey: 'settings.integrations.birdnet.internal_url_label', helpKey: 'settings.integrations.birdnet.internal_url_help', disclosures: [more('cameras')], behind: 'settings-group-integrations-birdnet' },
    { anchor: 'setting-birdnet-external-url', part: 'connection', labelKey: 'settings.integrations.birdnet.external_url_label', helpKey: 'settings.integrations.birdnet.external_url_help', disclosures: [more('cameras')], behind: 'settings-group-integrations-birdnet' },
    { anchor: 'setting-audio-topic', part: 'connection', labelKey: 'settings.integrations.birdnet.mqtt_topic', disclosures: [more('cameras')], behind: 'settings-group-integrations-birdnet', keywords: ['mqtt', 'audio'] },
    { anchor: 'setting-audio-buffer', part: 'connection', labelKey: 'settings.integrations.birdnet.audio_buffer_hours', helpKey: 'settings.integrations.birdnet.audio_buffer_help', disclosures: [more('cameras'), 'integrations-birdnet-advanced'], behind: 'settings-group-integrations-birdnet' },
    { anchor: 'setting-correlation-window', part: 'connection', labelKey: 'settings.integrations.birdnet.match_window_seconds', helpKey: 'settings.integrations.birdnet.match_window_help', disclosures: [more('cameras'), 'integrations-birdnet-advanced'], behind: 'settings-group-integrations-birdnet', keywords: ['audio', 'match', 'seconds'] },
    { anchor: 'setting-sensor-mapping', part: 'connection', labelKey: 'settings.integrations.birdnet.sensor_mapping_title', disclosures: [more('cameras'), 'integrations-birdnet-advanced'], behind: 'settings-group-integrations-birdnet' },
    { anchor: 'setting-classification-image-source', part: 'connection', labelKey: 'settings.frigate.classification_image_source', helpKey: 'settings.frigate.classification_image_source_desc', disclosures: [more('cameras')], keywords: ['snapshot', 'recording', 'frame', 'photo'] },
    { anchor: 'settings-group-frigate', part: 'connection', kind: 'group', labelKey: 'settings.frigate.title' },
    { anchor: 'setting-frigate-url', part: 'connection', labelKey: 'settings.frigate.url', keywords: ['nvr', 'address', 'host', 'connect'] },
    { anchor: 'settings-group-frigate-more', part: 'connection', kind: 'group', labelKey: 'settings.frigate.more_title', disclosures: [more('cameras')] },
    { anchor: 'setting-frigate-ingest-labels', part: 'connection', labelKey: 'settings.frigate.ingest_labels', helpKey: 'settings.frigate.ingest_labels_desc', disclosures: [more('cameras')], keywords: ['bird', 'label', 'object', 'track'] },
    { anchor: 'setting-frigate-external-url', part: 'connection', labelKey: 'settings.frigate.external_url', helpKey: 'settings.frigate.external_url_desc', disclosures: [more('cameras')], keywords: ['public', 'link', 'outside'] },
    { anchor: 'setting-clips-enabled', part: 'connection', labelKey: 'settings.frigate.fetch_clips', helpKey: 'settings.frigate.fetch_clips_desc', disclosures: [more('cameras')], keywords: ['video', 'clip', 'recording'] },
    { anchor: 'setting-recording-clips', part: 'connection', labelKey: 'settings.frigate.full_visit_clips', helpKey: 'settings.frigate.full_visit_clips_desc', disclosures: [more('cameras'), 'connection-full-visit'], behind: 'setting-clips-enabled', keywords: ['video', 'recording', 'longer'] },
    { anchor: 'setting-recording-before', part: 'connection', labelKey: 'settings.frigate.full_visit_before', disclosures: [more('cameras'), 'connection-full-visit'], behind: 'setting-clips-enabled' },
    { anchor: 'setting-recording-after', part: 'connection', labelKey: 'settings.frigate.full_visit_after', disclosures: [more('cameras'), 'connection-full-visit'], behind: 'setting-clips-enabled' },
    { anchor: 'settings-group-connection-mqtt-section', part: 'connection', kind: 'group', labelKey: 'settings.connection.mqtt_section' },
    { anchor: 'setting-mqtt-broker', part: 'connection', labelKey: 'settings.connection.mqtt_where', helpKey: 'settings.connection.mqtt_title', keywords: ['mqtt', 'broker', 'server', 'host', 'mosquitto'] },
    { anchor: 'setting-mqtt-auth', part: 'connection', labelKey: 'settings.frigate.mqtt_auth', keywords: ['mqtt', 'login', 'password', 'username'] },
    { anchor: 'setting-mqtt-username', part: 'connection', labelKey: 'settings.frigate.mqtt_user', behind: 'setting-mqtt-auth' },
    { anchor: 'setting-mqtt-password', part: 'connection', labelKey: 'settings.frigate.mqtt_pass', behind: 'setting-mqtt-auth' },
    { anchor: 'settings-group-cameras', part: 'connection', kind: 'group', labelKey: 'settings.cameras.title', keywords: ['camera', 'feeder', 'garden', 'watch', 'sync'] },
    { anchor: 'data-danger', part: 'maintenance', kind: 'group', labelKey: 'settings.danger.title', keywords: ['delete', 'reset', 'wipe', 'erase', 'clear', 'danger'] },
    { anchor: 'settings-group-data-retention', part: 'data', kind: 'group', labelKey: 'settings.data.retention_title' },
    { anchor: 'setting-retention-days', part: 'data', labelKey: 'settings.data.history_duration', keywords: ['retention', 'delete', 'old', 'keep', 'days', 'purge'] },
    { anchor: 'data-missing-media', part: 'data', kind: 'group', labelKey: 'settings.data.missing_media_title', disclosures: [more('storage')] },
    { anchor: 'setting-frigate-missing-behavior', part: 'data', labelKey: 'settings.data.frigate_missing_behavior', helpKey: 'settings.data.frigate_missing_behavior_note', disclosures: [more('storage')], keywords: ['missing', 'deleted', 'frigate'] },
    { anchor: 'setting-auto-media-integrity', part: 'data', labelKey: 'settings.data.auto_purge_missing_media', helpKey: 'settings.data.media_integrity_note', disclosures: [more('storage')], keywords: ['missing', 'scan', 'clean'] },
    { anchor: 'settings-group-data-cache', part: 'data', kind: 'group', labelKey: 'settings.data.cache_title' },
    { anchor: 'setting-cache-clips', part: 'data', labelKey: 'settings.data.cache_clips', helpKey: 'settings.data.cache_clips_help', keywords: ['video', 'copy', 'disk'] },
    { anchor: 'setting-cache-max_size_mb', part: 'data', labelKey: 'settings.data.storage_limit', keywords: ['disk', 'space', 'gb', 'size', 'quota', 'storage limit'] },
    { anchor: 'setting-cache-species-floor', part: 'data', labelKey: 'settings.data.per_species_minimum', helpKey: 'settings.data.per_species_minimum_help', disclosures: ['data-cache-species'] },
    { anchor: 'setting-cache-per_species_maximum', part: 'data', labelKey: 'settings.data.per_species_maximum', helpKey: 'settings.data.per_species_maximum_help', disclosures: ['data-cache-species'] },
    { anchor: 'setting-cache-hq', part: 'data', labelKey: 'settings.data.cache_high_quality_event_snapshots', disclosures: ['data-cache-advanced'], keywords: ['snapshot', 'quality', 'resolution', 'photo'] },
    { anchor: 'setting-automatic-multi-bird-scan', part: 'data', labelKey: 'settings.data.automatic_multi_bird_scan', helpKey: 'settings.data.automatic_multi_bird_scan_help', disclosures: ['data-cache-advanced'] },
    { anchor: 'setting-bird-scan-mode', part: 'data', labelKey: 'settings.data.bird_scan_mode', helpKey: 'settings.data.bird_scan_mode_help', disclosures: ['data-cache-advanced'] },
    { anchor: 'cache-hq-jpeg-quality', part: 'data', labelKey: 'settings.data.cache_high_quality_event_snapshot_jpeg_quality', helpKey: 'settings.data.cache_high_quality_event_snapshot_jpeg_quality_help', disclosures: ['data-cache-advanced'], behind: 'setting-cache-hq', keywords: ['jpeg', 'compression'] },
    { anchor: 'settings-group-data-config-backup', part: 'data', kind: 'group', labelKey: 'settings.data.config_backup_title', keywords: ['backup', 'export', 'import', 'restore', 'download'] },
    { anchor: 'settings-group-detection-blocked-labels', part: 'detection', kind: 'group', labelKey: 'settings.detection.blocked_labels', disclosures: [more('identification')], keywords: ['block', 'ignore', 'exclude', 'hide', 'species'] },
    { anchor: 'detection-frigate-video', part: 'detection', kind: 'group', labelKey: 'settings.detection.frigate_video_title', disclosures: [more('identification')] },
    { anchor: 'setting-trust-frigate', part: 'detection', labelKey: 'settings.detection.trust_frigate', helpKey: 'settings.detection.trust_frigate_desc', disclosures: [more('identification'), 'detection-frigate-video'], keywords: ['sublabel', 'frigate'] },
    { anchor: 'setting-write-frigate', part: 'detection', labelKey: 'settings.detection.write_frigate_sublabel', helpKey: 'settings.detection.write_frigate_sublabel_desc', disclosures: [more('identification'), 'detection-frigate-video'], keywords: ['sublabel', 'frigate'] },
    { anchor: 'setting-auto-video', part: 'detection', labelKey: 'settings.detection.auto_video', helpKey: 'settings.detection.auto_video_desc', disclosures: [more('identification'), 'detection-frigate-video'], keywords: ['video', 'clip', 'second check'] },
    { anchor: 'setting-video-delay', part: 'detection', labelKey: 'settings.detection.video_delay', disclosures: [more('identification'), 'detection-frigate-video'], behind: 'setting-auto-video' },
    { anchor: 'setting-video-retries', part: 'detection', labelKey: 'settings.detection.video_retries', disclosures: [more('identification'), 'detection-frigate-video'], behind: 'setting-auto-video' },
    { anchor: 'setting-video-frames', part: 'detection', labelKey: 'settings.detection.video_frames', disclosures: [more('identification'), 'detection-frigate-video'], behind: 'setting-auto-video' },
    { anchor: 'settings-group-enrichment', part: 'integrations', kind: 'group', labelKey: 'settings.enrichment.title', disclosures: [more('sharing')], keywords: ['wikipedia', 'species information', 'sources'] },
    { anchor: 'setting-garden-labels', part: 'beta', labelKey: 'garden.labels', helpKey: 'garden.labels_help', disclosures: [more('identification'), 'garden-section-cameras'], behind: 'beta-garden-animals-name' },
    { anchor: 'garden-motion-confidence', part: 'beta', labelKey: 'garden.confidence', helpKey: 'garden.confidence_help', disclosures: [more('identification'), 'garden-section-cameras'], behind: 'beta-garden-animals-name' },
    { anchor: 'garden-notifications', part: 'notifications', labelKey: 'settings.notifications.garden.enabled', helpKey: 'settings.notifications.garden.enabled_help', disclosures: [more('alerts')], behind: 'beta-garden-animals-name', keywords: ['garden', 'animal', 'alert'] },
    { anchor: 'garden-notification-photo', part: 'notifications', labelKey: 'settings.notifications.garden.include_photo', helpKey: 'settings.notifications.garden.include_photo_help', disclosures: [more('alerts')], behind: 'garden-notifications' },
    { anchor: 'settings-group-integrations-ha-weather', part: 'integrations', kind: 'group', labelKey: 'settings.integrations.ha_weather.title', disclosures: [more('sharing')], keywords: ['home assistant', 'weather', 'temperature', 'sensor', 'hass'] },
    { anchor: 'setting-ha-weather-url', part: 'integrations', labelKey: 'settings.integrations.ha_weather.base_url', helpKey: 'settings.integrations.ha_weather.base_url_desc', disclosures: [more('sharing')], behind: 'settings-group-integrations-ha-weather' },
    { anchor: 'setting-ha-weather-token', part: 'integrations', labelKey: 'settings.integrations.ha_weather.token', helpKey: 'settings.integrations.ha_weather.token_desc', disclosures: [more('sharing')], behind: 'settings-group-integrations-ha-weather' },
    { anchor: 'setting-ha-weather-entity', part: 'integrations', labelKey: 'settings.integrations.ha_weather.entity', helpKey: 'settings.integrations.ha_weather.entity_desc', disclosures: [more('sharing')], behind: 'settings-group-integrations-ha-weather' },
    { anchor: 'setting-ha-weather-illuminance', part: 'integrations', labelKey: 'settings.integrations.ha_weather.illuminance', helpKey: 'settings.integrations.ha_weather.illuminance_desc', disclosures: [more('sharing')], behind: 'settings-group-integrations-ha-weather' },
    { anchor: 'setting-ha-weather-temperature', part: 'integrations', labelKey: 'settings.integrations.ha_weather.override_temperature', disclosures: [more('sharing'), 'integrations-ha-weather-overrides'], behind: 'settings-group-integrations-ha-weather' },
    { anchor: 'setting-ha-weather-wind-speed', part: 'integrations', labelKey: 'settings.integrations.ha_weather.override_wind_speed', disclosures: [more('sharing'), 'integrations-ha-weather-overrides'], behind: 'settings-group-integrations-ha-weather' },
    { anchor: 'setting-ha-weather-wind-direction', part: 'integrations', labelKey: 'settings.integrations.ha_weather.override_wind_direction', disclosures: [more('sharing'), 'integrations-ha-weather-overrides'], behind: 'settings-group-integrations-ha-weather' },
    { anchor: 'setting-ha-weather-cloud-cover', part: 'integrations', labelKey: 'settings.integrations.ha_weather.override_cloud_cover', disclosures: [more('sharing'), 'integrations-ha-weather-overrides'], behind: 'settings-group-integrations-ha-weather' },
    { anchor: 'setting-ha-weather-precipitation', part: 'integrations', labelKey: 'settings.integrations.ha_weather.override_precipitation', disclosures: [more('sharing'), 'integrations-ha-weather-overrides'], behind: 'settings-group-integrations-ha-weather' },
    { anchor: 'setting-ha-weather-rain', part: 'integrations', labelKey: 'settings.integrations.ha_weather.override_rain', disclosures: [more('sharing'), 'integrations-ha-weather-overrides'], behind: 'settings-group-integrations-ha-weather' },
    { anchor: 'setting-ha-weather-snowfall', part: 'integrations', labelKey: 'settings.integrations.ha_weather.override_snowfall', disclosures: [more('sharing'), 'integrations-ha-weather-overrides'], behind: 'settings-group-integrations-ha-weather' },
    { anchor: 'models-hardware', part: 'models', kind: 'group', labelKey: 'settings.detection.hardware_title', disclosures: [more('identification')], keywords: ['gpu', 'cpu', 'npu', 'openvino', 'cuda', 'intel', 'nvidia', 'device', 'acceleration'] },
    { anchor: 'setting-inference-provider', part: 'models', labelKey: 'settings.detection.inference_provider', helpKey: 'settings.detection.inference_provider_desc', disclosures: [more('identification')], keywords: ['gpu', 'cpu', 'npu', 'openvino', 'cuda', 'device'] },
    { anchor: 'setting-execution-mode', part: 'models', labelKey: 'settings.detection.execution_mode', helpKey: 'settings.detection.execution_mode_desc', disclosures: [more('identification'), 'detection-memory-advanced'], keywords: ['subprocess', 'worker', 'memory', 'crash'] },
    { anchor: 'setting-worker-counts', part: 'models', labelKey: 'settings.detection.worker_counts', helpKey: 'settings.detection.worker_counts_desc', disclosures: [more('identification'), 'detection-memory-advanced'], keywords: ['workers', 'parallel', 'memory'] },
    { anchor: 'setting-strict-non-finite-output', part: 'models', labelKey: 'settings.debug.strict_non_finite_output', helpKey: 'settings.debug.strict_non_finite_output_desc', disclosures: [more('identification'), 'detection-memory-advanced'], behind: 'setting-execution-mode' },
    { anchor: 'beta-garden-animals-name', part: 'beta', kind: 'group', labelKey: 'settings.beta.garden_animals', helpKey: 'settings.beta.garden_animals_desc', disclosures: [more('identification')], keywords: ['garden', 'animal', 'cat', 'fox', 'squirrel', 'hedgehog', 'mammal', 'beta'] },
    { anchor: 'settings-group-integrations-inaturalist', part: 'integrations', kind: 'group', labelKey: 'settings.integrations.inaturalist.title', disclosures: [more('sharing')], keywords: ['inat', 'submit', 'observation'] },
    { anchor: 'setting-inat-client-id', part: 'integrations', labelKey: 'settings.integrations.inaturalist.client_id', disclosures: [more('sharing')], behind: 'settings-group-integrations-inaturalist' },
    { anchor: 'setting-inat-client-secret', part: 'integrations', labelKey: 'settings.integrations.inaturalist.client_secret', disclosures: [more('sharing')], behind: 'settings-group-integrations-inaturalist' },
    { anchor: 'setting-inat-lat', part: 'integrations', labelKey: 'settings.integrations.inaturalist.default_latitude', disclosures: [more('sharing'), 'integrations-inat-advanced'], behind: 'settings-group-integrations-inaturalist' },
    { anchor: 'setting-inat-lon', part: 'integrations', labelKey: 'settings.integrations.inaturalist.default_longitude', disclosures: [more('sharing'), 'integrations-inat-advanced'], behind: 'settings-group-integrations-inaturalist' },
    { anchor: 'setting-inat-place', part: 'integrations', labelKey: 'settings.integrations.inaturalist.default_place_guess', disclosures: [more('sharing'), 'integrations-inat-advanced'], behind: 'settings-group-integrations-inaturalist' },
    { anchor: 'settings-group-integrations-ebird', part: 'integrations', kind: 'group', labelKey: 'settings.integrations.ebird.title', disclosures: [more('sharing')], keywords: ['ebird', 'cornell', 'api key', 'export', 'checklist'] },
    { anchor: 'setting-ebird-api-key', part: 'integrations', labelKey: 'settings.integrations.ebird.api_key', helpKey: 'settings.integrations.ebird.api_key_desc', disclosures: [more('sharing')], behind: 'settings-group-integrations-ebird' },
    { anchor: 'setting-ebird-export-mode', part: 'integrations', labelKey: 'settings.integrations.ebird.export_everything', helpKey: 'settings.integrations.ebird.export_everything_help', disclosures: [more('sharing')], behind: 'settings-group-integrations-ebird' },
    { anchor: 'setting-ebird-export-from', part: 'integrations', labelKey: 'settings.integrations.ebird.export_from', disclosures: [more('sharing')], behind: 'settings-group-integrations-ebird' },
    { anchor: 'setting-ebird-export-to', part: 'integrations', labelKey: 'settings.integrations.ebird.export_to', disclosures: [more('sharing')], behind: 'settings-group-integrations-ebird' },
    { anchor: 'setting-ebird-days', part: 'integrations', labelKey: 'settings.integrations.ebird.days_back', disclosures: [more('sharing'), 'integrations-ebird-advanced'], behind: 'settings-group-integrations-ebird' },
    { anchor: 'setting-ebird-max-results', part: 'integrations', labelKey: 'settings.integrations.ebird.max_results', disclosures: [more('sharing'), 'integrations-ebird-advanced'], behind: 'settings-group-integrations-ebird' },
    { anchor: 'setting-ebird-locale', part: 'integrations', labelKey: 'settings.integrations.ebird.locale', disclosures: [more('sharing'), 'integrations-ebird-advanced'], behind: 'settings-group-integrations-ebird' },
    { anchor: 'settings-group-integrations-birdweather', part: 'integrations', kind: 'group', labelKey: 'settings.integrations.birdweather.title', disclosures: [more('sharing')], keywords: ['birdweather', 'station'] },
    { anchor: 'setting-birdweather-token', part: 'integrations', labelKey: 'settings.integrations.birdweather.token', helpKey: 'settings.integrations.birdweather.token_desc', disclosures: [more('sharing')], behind: 'settings-group-integrations-birdweather' },
    { anchor: 'settings-group-location-card', part: 'security', kind: 'group', labelKey: 'settings.location.card_title' },
    { anchor: 'setting-location-mode', part: 'security', labelKey: 'settings.location.mode_title', helpKey: 'settings.location.mode_help', keywords: ['latitude', 'longitude', 'coordinates', 'gps', 'where'] },
    { anchor: 'setting-location-lat', part: 'security', labelKey: 'settings.location.latitude', behind: 'setting-location-mode' },
    { anchor: 'setting-location-lon', part: 'security', labelKey: 'settings.location.longitude', behind: 'setting-location-mode' },
    { anchor: 'setting-location-map', part: 'security', labelKey: 'settings.location.map_title' },
    { anchor: 'settings-group-data-taxonomy', part: 'maintenance', kind: 'group', labelKey: 'settings.data.taxonomy_title', disclosures: [more('storage')] },
    { anchor: 'setting-maintenance-taxonomy', part: 'maintenance', labelKey: 'settings.maintenance.taxonomy_row', disclosures: [more('storage')], keywords: ['taxonomy', 'names', 'sync', 'inaturalist'] },
    { anchor: 'settings-group-data-timezone-repair', part: 'maintenance', kind: 'group', labelKey: 'settings.data.timezone_repair_title', disclosures: [more('storage')], keywords: ['timezone', 'time', 'clock', 'utc'] },
    { anchor: 'settings-group-data-backfill', part: 'maintenance', kind: 'group', labelKey: 'settings.data.backfill_title', disclosures: [more('storage')], keywords: ['backfill', 'import', 'history', 'frigate', 'past'] },
    { anchor: 'setting-backfill-window', part: 'maintenance', labelKey: 'settings.data.backfill_window', disclosures: [more('storage')] },
    { anchor: 'settings-group-data-batch-analysis', part: 'maintenance', kind: 'group', labelKey: 'settings.data.batch_analysis_title', disclosures: [more('storage')] },
    { anchor: 'setting-maintenance-analyse', part: 'maintenance', labelKey: 'settings.maintenance.analyse_row', disclosures: [more('storage')], keywords: ['unknown', 'reanalyse', 'batch', 'reclassify'] },
    { anchor: 'setting-auto-analyze', part: 'maintenance', labelKey: 'settings.data.auto_analyze_unknowns', disclosures: [more('storage')] },
    { anchor: 'maintenance-concurrency', part: 'maintenance', kind: 'group', labelKey: 'settings.data.maintenance_jobs_title', disclosures: [more('storage')] },
    { anchor: 'setting-maint-concurrency', part: 'maintenance', labelKey: 'settings.data.maintenance_max_concurrent', helpKey: 'settings.data.maintenance_max_concurrent_help', disclosures: [more('storage')], keywords: ['parallel', 'jobs', 'speed'] },
    { anchor: 'settings-group-detection-models-card', part: 'models', kind: 'group', labelKey: 'settings.detection.models_card_title', keywords: ['model', 'classifier', 'detector', 'download'] },
    { anchor: 'setting-region-override', part: 'models', labelKey: 'settings.detection.region_override_title', helpKey: 'settings.detection.region_override_desc', keywords: ['europe', 'north america', 'country', 'regional'] },
    { anchor: 'setting-model-evaluation', part: 'models', labelKey: 'settings.models.evaluation_row', helpKey: 'settings.models.evaluation_row_desc' },
    { anchor: 'settings-group-naming', part: 'detection', kind: 'group', labelKey: 'settings.naming.title' },
    { anchor: 'confidence-threshold-slider', part: 'detection', labelKey: 'settings.detection.confidence_threshold', helpKey: 'settings.detection.threshold_help', keywords: ['confidence', 'score', 'sure', 'accuracy', 'sensitivity'] },
    { anchor: 'min-confidence-slider', part: 'detection', labelKey: 'settings.detection.min_confidence_floor', helpKey: 'settings.detection.floor_help', keywords: ['unknown', 'minimum', 'floor', 'reject'] },
    { anchor: 'setting-personalized-rerank', part: 'detection', labelKey: 'settings.detection.personalized_rerank', helpKey: 'settings.detection.personalized_rerank_desc', keywords: ['corrections', 'learning', 'personal', 'rerank'] },
    { anchor: 'setting-garden-naming', part: 'detection', labelKey: 'settings.beta.garden_naming', helpKey: 'settings.beta.garden_naming_help', behind: 'beta-garden-animals-name' },
    { anchor: 'garden-naming-threshold', part: 'detection', labelKey: 'settings.beta.garden_naming_threshold', helpKey: 'settings.beta.garden_naming_threshold_help', behind: 'beta-garden-animals-name' },
    { anchor: 'notification-channels', part: 'notifications', kind: 'group', labelKey: 'settings.notifications.channels_title', keywords: ['discord', 'telegram', 'pushover', 'email', 'where'] },
    { anchor: 'discord-channel-label', part: 'notifications', labelKey: 'settings.discord.title', helpKey: 'settings.discord.desc', keywords: ['webhook', 'bot'] },
    { anchor: 'pushover-channel-label', part: 'notifications', labelKey: 'settings.pushover.title', helpKey: 'settings.pushover.desc', keywords: ['phone', 'push', 'user key', 'api token', 'priority'] },
    { anchor: 'telegram-channel-label', part: 'notifications', labelKey: 'settings.telegram.title', helpKey: 'settings.telegram.desc', keywords: ['bot', 'chat'] },
    { anchor: 'email-channel-label', part: 'notifications', labelKey: 'settings.email.title', helpKey: 'settings.email.desc', keywords: ['smtp', 'gmail', 'outlook', 'mail'] },
    { anchor: 'email-auth-mode-label', part: 'notifications', labelKey: 'settings.email.auth_mode', behind: 'email-channel-label' },
    { anchor: 'settings-group-notifications-global-filters', part: 'notifications', kind: 'group', labelKey: 'settings.notifications.global_filters', keywords: ['alert', 'notify', 'when', 'confidence', 'new visits', 'audio'] },
    { anchor: 'settings-group-notifications-details', part: 'notifications', kind: 'group', labelKey: 'settings.notifications.details_title', disclosures: [more('alerts')] },
    { anchor: 'notification-cooldown-label', part: 'notifications', labelKey: 'settings.notifications.cooldown', helpKey: 'settings.notifications.cooldown_desc', disclosures: [more('alerts')], keywords: ['quiet', 'throttle', 'rate', 'spam', 'too many', 'minutes', 'pause'] },
    { anchor: 'notification-language', part: 'notifications', labelKey: 'settings.notifications.notification_language', helpKey: 'settings.notifications.notification_language_desc', disclosures: [more('alerts')], keywords: ['translate', 'locale'] },
    { anchor: 'notification-instance-url', part: 'notifications', labelKey: 'settings.notifications.instance_url', helpKey: 'settings.notifications.instance_url_desc', disclosures: [more('alerts')], keywords: ['link', 'url', 'public address'] },
    { anchor: 'notification-link-opens', part: 'notifications', labelKey: 'settings.notifications.link_opens', disclosures: [more('alerts')], keywords: ['link', 'frigate', 'url'] },
    { anchor: 'notification-species-filter-section', part: 'notifications', labelKey: 'settings.notifications.species_filter', disclosures: [more('alerts')], keywords: ['only', 'except', 'allow', 'block', 'whitelist', 'blacklist'] },
    { anchor: 'settings-group-range-filter', part: 'detection', kind: 'group', labelKey: 'settings.range_filter.title', disclosures: [more('identification')], keywords: ['ebird', 'region', 'out of range', 'rare', 'location'] },
    { anchor: 'setting-range-filter', part: 'detection', labelKey: 'settings.range_filter.toggle', disclosures: [more('identification')] },
    { anchor: 'setting-range-filter-level', part: 'detection', labelKey: 'settings.range_filter.level_label', helpKey: 'settings.range_filter.level_desc', disclosures: [more('identification')], behind: 'setting-range-filter' },
    { anchor: 'settings-group-telemetry', part: 'ai', kind: 'group', labelKey: 'settings.telemetry.title', disclosures: [more('sharing')] },
    { anchor: 'setting-telemetry', part: 'ai', labelKey: 'settings.telemetry.usage_title', helpKey: 'settings.telemetry.appreciation_tooltip', disclosures: [more('sharing')], keywords: ['analytics', 'tracking', 'anonymous', 'privacy', 'usage'] },
    { anchor: 'setting-telemetry-health', part: 'ai', labelKey: 'settings.telemetry.health_title', helpKey: 'settings.telemetry.health_desc', disclosures: [more('sharing')] },
    { anchor: 'settings-group-units', part: 'appearance', kind: 'group', labelKey: 'settings.units.title', disclosures: [more('display')] },
    { anchor: 'setting-weather-units', part: 'appearance', labelKey: 'settings.location.weather_unit_system', helpKey: 'settings.location.weather_unit_system_desc', disclosures: [more('display')], keywords: ['metric', 'imperial', 'celsius', 'fahrenheit', 'mph', 'km'] },
    { anchor: 'settings-group-visit-gap', part: 'detection', kind: 'group', labelKey: 'settings.visit_gap.title' },
    { anchor: 'setting-visit-gap', part: 'detection', labelKey: 'settings.visit_gap.label', helpKey: 'settings.visit_gap.range', keywords: ['gap', 'dedupe', 'duplicate', 'grouping', 'count', 'seconds'] },
    { anchor: 'setting-ebird-radius', part: 'integrations', labelKey: 'settings.integrations.ebird.radius', disclosures: [more('sharing'), 'integrations-ebird-advanced'], behind: 'settings-group-integrations-ebird' }
];

const ENTRY_BY_ANCHOR: ReadonlyMap<string, SettingsSearchEntry> = new Map(SETTINGS_SEARCH_INDEX.map((entry) => [entry.anchor, entry]));

/** The entry an anchor names, or null. */
export function settingsSearchEntry(anchor: string): SettingsSearchEntry | null {
    return ENTRY_BY_ANCHOR.get(anchor) ?? null;
}

/** The section that shows an entry. */
export function settingsSearchSection(entry: SettingsSearchEntry): SettingsSection {
    return settingsSectionOfPart(entry.part);
}

/** Whether an entry sits under its section's More options. */
export function settingsSearchInMore(entry: SettingsSearchEntry): boolean {
    return entry.disclosures?.[0] === settingsMoreId(settingsSearchSection(entry));
}

/** Whether an entry sits behind a further "advanced" disclosure, beyond More options. */
export function settingsSearchIsAdvanced(entry: SettingsSearchEntry): boolean {
    return (entry.disclosures?.length ?? 0) > (settingsSearchInMore(entry) ? 1 : 0);
}
