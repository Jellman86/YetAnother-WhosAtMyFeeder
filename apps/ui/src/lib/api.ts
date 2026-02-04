export interface Detection {
    id?: number;
    frigate_event: string;
    display_name: string;
    score: number;
    detection_time: string;
    camera_name: string;
    detection_index?: number;
    category_name?: string;
    has_clip?: boolean;  // Clip availability from backend
    is_hidden?: boolean; // Hidden/ignored status
    frigate_score?: number; // Frigate detection confidence
    sub_label?: string;     // Frigate sub-label
    manual_tagged?: boolean;
    // Audio fields
    audio_confirmed?: boolean;
    audio_species?: string;
    audio_score?: number;
    // Weather fields
    temperature?: number;
    weather_condition?: string;
    weather_cloud_cover?: number;
    weather_wind_speed?: number;
    weather_wind_direction?: number;
    weather_precipitation?: number;
    weather_rain?: number;
    weather_snowfall?: number;
    // Taxonomy fields
    scientific_name?: string;
    common_name?: string;
    taxa_id?: number;
    // Video classification fields
    video_classification_score?: number;
    video_classification_label?: string;
    video_classification_timestamp?: string;
    video_classification_status?: 'pending' | 'processing' | 'completed' | 'failed' | null;
    video_classification_error?: string | null;
    // AI analysis fields
    ai_analysis?: string | null;
    ai_analysis_timestamp?: string | null;
}

export interface VersionInfo {
    version: string;
    base_version: string;
    git_hash: string;
    branch: string;
}

export interface AuthStatusResponse {
    auth_required: boolean;
    public_access_enabled: boolean;
    is_authenticated: boolean;
    birdnet_enabled: boolean;
    llm_enabled: boolean;
    ebird_enabled: boolean;
    inaturalist_enabled: boolean;
    enrichment_mode: string;
    enrichment_single_provider: string;
    enrichment_summary_source: string;
    enrichment_sightings_source: string;
    enrichment_seasonality_source: string;
    enrichment_rarity_source: string;
    enrichment_links_sources: string[];
    display_common_names: boolean;
    scientific_name_primary: boolean;
    accessibility_live_announcements: boolean;
    location_temperature_unit: string;
    username: string | null;
    needs_initial_setup: boolean;
    https_warning: boolean;
}

export interface LoginResponse {
    access_token: string;
    token_type: string;
    username: string;
    expires_in_hours: number;
}

export interface SpeciesCount {
    species: string;
    count: number;
    scientific_name?: string | null;
    common_name?: string | null;
    first_seen?: string | null;
    last_seen?: string | null;
    avg_confidence?: number;
    max_confidence?: number;
    min_confidence?: number;
    camera_count?: number;
    count_1d?: number;
    count_7d?: number;
    count_30d?: number;
    days_seen_14d?: number;
    days_seen_30d?: number;
    trend_delta?: number;
    trend_percent?: number;
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
    classification_threshold: number;
    classification_min_confidence: number;
    cameras: string[];
    retention_days: number;
    blocked_labels: string[];
    trust_frigate_sublabel: boolean;
    display_common_names: boolean;
    scientific_name_primary: boolean;
    auto_video_classification: boolean;
    video_classification_delay: number;
    video_classification_max_retries: number;
    video_classification_circuit_open?: boolean;
    video_classification_circuit_until?: string | null;
    video_classification_circuit_failures?: number;
    audio_buffer_hours?: number;
    audio_correlation_window_seconds?: number;
    // Media cache settings
    media_cache_enabled: boolean;
    media_cache_snapshots: boolean;
    media_cache_clips: boolean;
    media_cache_retention_days: number;
    // Location settings
    location_latitude?: number | null;
    location_longitude?: number | null;
    location_automatic?: boolean;
    location_temperature_unit?: 'celsius' | 'fahrenheit' | string;
    // BirdWeather settings
    birdweather_enabled: boolean;
    birdweather_station_token?: string | null;
    // eBird settings
    ebird_enabled?: boolean;
    ebird_api_key?: string | null;
    ebird_default_radius_km?: number;
    ebird_default_days_back?: number;
    ebird_max_results?: number;
    ebird_locale?: string;
    // iNaturalist settings
    inaturalist_enabled?: boolean;
    inaturalist_client_id?: string | null;
    inaturalist_client_secret?: string | null;
    inaturalist_default_latitude?: number | null;
    inaturalist_default_longitude?: number | null;
    inaturalist_default_place_guess?: string | null;
    inaturalist_connected_user?: string | null;
    // Enrichment settings
    enrichment_mode?: string;
    enrichment_single_provider?: string;
    enrichment_summary_source?: string;
    enrichment_taxonomy_source?: string;
    enrichment_sightings_source?: string;
    enrichment_seasonality_source?: string;
    enrichment_rarity_source?: string;
    enrichment_links_sources?: string[];
    // LLM settings
    llm_enabled: boolean;
    llm_provider?: string;
    llm_api_key?: string;
    llm_model?: string;
    telemetry_enabled: boolean;
    telemetry_installation_id?: string;
    telemetry_platform?: string;

    // Notification settings
    notifications_discord_enabled: boolean;
    notifications_discord_webhook_url?: string | null;
    notifications_discord_username: string;
    
    notifications_pushover_enabled: boolean;
    notifications_pushover_user_key?: string | null;
    notifications_pushover_api_token?: string | null;
    notifications_pushover_priority: number;
    
    notifications_telegram_enabled: boolean;
    notifications_telegram_bot_token?: string | null;
    notifications_telegram_chat_id?: string | null;

    // Email notification settings
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

    // Optional nested notifications object for backward compatibility/UI grouping
    notifications?: {
        discord?: { enabled: boolean };
        pushover?: { enabled: boolean };
        telegram?: { enabled: boolean };
        email?: { enabled: boolean };
    };

    // Accessibility settings
    accessibility_high_contrast: boolean;
    accessibility_dyslexia_font: boolean;
    accessibility_reduced_motion: boolean;
    accessibility_zen_mode: boolean;
    accessibility_live_announcements: boolean;

    // Authentication
    auth_enabled: boolean;
    auth_username: string;
    auth_has_password: boolean;
    auth_session_expiry_hours: number;
    auth_password?: string;
    trusted_proxy_hosts?: string[];
    debug_ui_enabled?: boolean;

    // Public access
    public_access_enabled: boolean;
    public_access_show_camera_names: boolean;
    public_access_historical_days: number;
    public_access_rate_limit_per_minute: number;

    species_info_source?: string;
}

export type UpdateSettings = Partial<Settings>;

export interface SettingsUpdate extends Partial<Settings> {}

export interface CacheStats {
    snapshot_count: number;
    snapshot_size_bytes: number;
    snapshot_size_mb: number;
    clip_count: number;
    clip_size_bytes: number;
    clip_size_mb: number;
    total_size_bytes: number;
    total_size_mb: number;
    oldest_file: string | null;
    newest_file: string | null;
    cache_enabled: boolean;
    cache_snapshots: boolean;
    cache_clips: boolean;
    retention_days: number;
    retention_source: string;
}

export interface CacheCleanupResult {
    status: string;
    snapshots_deleted: number;
    clips_deleted: number;
    bytes_freed: number;
    retention_days?: number;
    message?: string;
}

export interface MaintenanceStats {
    total_detections: number;
    oldest_detection: string | null;
    retention_days: number;
    detections_to_cleanup: number;
}

export interface CleanupResult {
    status: string;
    deleted_count: number;
    message?: string;
    cutoff_date?: string;
}

const API_BASE = '/api';

// API Key Management
let apiKey: string | null = typeof localStorage !== 'undefined' ? localStorage.getItem('api_key') : null;

// Auth Token Management (JWT)
let authToken: string | null = typeof localStorage !== 'undefined' ? localStorage.getItem('auth_token') : null;
let authTokenExpiresAt: number = typeof localStorage !== 'undefined'
    ? Number(localStorage.getItem('auth_token_expires_at') || 0)
    : 0;

export function setApiKey(key: string | null) {
    apiKey = key;
    if (typeof localStorage !== 'undefined') {
        if (key) localStorage.setItem('api_key', key);
        else localStorage.removeItem('api_key');
    }
}

export function getApiKey(): string | null {
    return apiKey;
}

function isAuthTokenExpired(): boolean {
    if (!authToken || !authTokenExpiresAt) {
        return false;
    }
    return Date.now() >= authTokenExpiresAt;
}

export function setAuthToken(token: string | null, expiresInHours?: number) {
    authToken = token;
    if (typeof localStorage !== 'undefined') {
        if (token) {
            localStorage.setItem('auth_token', token);
            if (expiresInHours) {
                authTokenExpiresAt = Date.now() + expiresInHours * 60 * 60 * 1000;
                localStorage.setItem('auth_token_expires_at', String(authTokenExpiresAt));
            } else {
                authTokenExpiresAt = 0;
                localStorage.removeItem('auth_token_expires_at');
            }
        } else {
            localStorage.removeItem('auth_token');
            localStorage.removeItem('auth_token_expires_at');
            authTokenExpiresAt = 0;
        }
    }
}

export function getAuthToken(): string | null {
    if (isAuthTokenExpired()) {
        setAuthToken(null);
        return null;
    }
    return authToken;
}

function getHeaders(customHeaders: HeadersInit = {}): HeadersInit {
    const headers: Record<string, string> = { ...customHeaders as Record<string, string> };
    const token = getAuthToken();
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    if (apiKey) {
        headers['X-API-Key'] = apiKey;
    }

    // Add Accept-Language header if available
    if (typeof localStorage !== 'undefined') {
        const preferredLang = localStorage.getItem('preferred-language');
        if (preferredLang) {
            headers['Accept-Language'] = preferredLang;
        }
    }

    return headers;
}

// Auth error handling
let authErrorCallback: (() => void) | null = null;

export function setAuthErrorCallback(callback: () => void) {
    authErrorCallback = callback;
}

async function apiFetch(url: string, options: RequestInit = {}): Promise<Response> {
    const response = await fetch(url, {
        ...options,
        headers: getHeaders(options.headers)
    });
    
    if (response.status === 401 && authErrorCallback) {
        authErrorCallback();
    }
    
    return response;
}

export async function fetchAuthStatus(): Promise<AuthStatusResponse> {
    const response = await fetch(`${API_BASE}/auth/status`, {
        headers: getHeaders()
    });

    if (!response.ok) {
        throw new Error('Failed to fetch auth status');
    }

    return response.json();
}

export async function login(username: string, password: string): Promise<LoginResponse> {
    const response = await apiFetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ username, password })
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || 'Login failed');
    }

    const data: LoginResponse = await response.json();
    setAuthToken(data.access_token, data.expires_in_hours);
    return data;
}

export async function logout(): Promise<void> {
    await apiFetch(`${API_BASE}/auth/logout`, { method: 'POST' });
    setAuthToken(null);
}

export async function setInitialPassword(options: {
    username: string;
    password: string | null;
    enableAuth: boolean;
}): Promise<void> {
    const response = await apiFetch(`${API_BASE}/auth/initial-setup`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            username: options.username,
            password: options.password,
            enable_auth: options.enableAuth
        })
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || 'Initial setup failed');
    }
}

// Global abort controller map for cancellable requests
const abortControllers = new Map<string, AbortController>();

/**
 * Create a fetch request with optional abort signal support
 * @param key - Unique key for this request (for cancellation)
 * @param url - URL to fetch
 * @param options - Fetch options
 * @returns Promise with response
 */
async function fetchWithAbort<T>(
    key: string | null,
    url: string,
    options: RequestInit = {}
): Promise<T> {
    // Cancel any existing request with the same key
    if (key && abortControllers.has(key)) {
        abortControllers.get(key)!.abort();
        abortControllers.delete(key);
    }

    // Create new abort controller if key provided
    let controller: AbortController | undefined;
    if (key) {
        controller = new AbortController();
        abortControllers.set(key, controller);
    }

    try {
        const fetchOptions: RequestInit = {
            ...options,
            headers: getHeaders(options.headers),
            signal: controller?.signal
        };
        
        const response = await fetch(url, fetchOptions);

        // Clean up controller on success
        if (key) {
            abortControllers.delete(key);
        }

        return await handleResponse<T>(response);
    } catch (error) {
        // Clean up controller on error
        if (key) {
            abortControllers.delete(key);
        }

        // Re-throw non-abort errors
        if (error instanceof Error && error.name === 'AbortError') {
            console.log(`Request cancelled: ${key || url}`);
        }
        throw error;
    }
}

/**
 * Cancel a pending request by key
 */
export function cancelRequest(key: string) {
    if (abortControllers.has(key)) {
        abortControllers.get(key)!.abort();
        abortControllers.delete(key);
    }
}

async function handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
        const error = await response.text();
        throw new Error(error || `HTTP ${response.status}`);
    }
    return response.json();
}

export async function fetchVersion(): Promise<VersionInfo> {
    try {
        const response = await apiFetch(`${API_BASE}/version`);
        if (response.ok) {
            return await response.json();
        }
    } catch {
        // Ignore errors - return fallback
    }
    const appVersion = typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : 'unknown';
    const appVersionBase = appVersion.includes('+') ? appVersion.split('+')[0] : appVersion;
    const appBranch = typeof __APP_BRANCH__ === 'string' ? __APP_BRANCH__ : 'unknown';
    return { 
        version: appVersion, 
        base_version: appVersionBase, 
        git_hash: typeof __GIT_HASH__ === 'string' ? __GIT_HASH__ : 'unknown',
        branch: appBranch
    };
}

export interface FetchEventsOptions {
    limit?: number;
    offset?: number;
    startDate?: string;  // YYYY-MM-DD format
    endDate?: string;    // YYYY-MM-DD format
    species?: string;
    camera?: string;
    sort?: 'newest' | 'oldest' | 'confidence';
    includeHidden?: boolean;  // Include hidden/ignored detections
}

export async function fetchEvents(options: FetchEventsOptions = {}): Promise<Detection[]> {
    const { limit = 50, offset = 0, startDate, endDate, species, camera, sort, includeHidden } = options;
    const params = new URLSearchParams();
    params.set('limit', limit.toString());
    params.set('offset', offset.toString());
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    if (species) params.set('species', species);
    if (camera) params.set('camera', camera);
    if (sort) params.set('sort', sort);
    if (includeHidden) params.set('include_hidden', 'true');

    // Use abort key based on filters to cancel outdated requests
    const filterKey = `events-${species || 'all'}-${camera || 'all'}-${sort || 'newest'}`;
    return fetchWithAbort<Detection[]>(filterKey, `${API_BASE}/events?${params.toString()}`);
}

export interface EventFilters {
    species: string[];
    cameras: string[];
}

export async function fetchEventFilters(): Promise<EventFilters> {
    const response = await apiFetch(`${API_BASE}/events/filters`);
    return handleResponse<EventFilters>(response);
}

export interface EventsCountOptions {
    startDate?: string;
    endDate?: string;
    species?: string;
    camera?: string;
    includeHidden?: boolean;
}

export interface EventsCountResponse {
    count: number;
    filtered: boolean;
}

export async function fetchEventsCount(options: EventsCountOptions = {}): Promise<EventsCountResponse> {
    const { startDate, endDate, species, camera, includeHidden } = options;
    const params = new URLSearchParams();
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    if (species) params.set('species', species);
    if (camera) params.set('camera', camera);
    if (includeHidden) params.set('include_hidden', 'true');

    const response = await apiFetch(`${API_BASE}/events/count?${params.toString()}`);
    return handleResponse<EventsCountResponse>(response);
}

export async function fetchMaintenanceStats(): Promise<MaintenanceStats> {
    const response = await apiFetch(`${API_BASE}/maintenance/stats`);
    return handleResponse<MaintenanceStats>(response);
}

export async function runCleanup(): Promise<CleanupResult> {
    const response = await apiFetch(`${API_BASE}/maintenance/cleanup`, { method: 'POST' });
    return handleResponse<CleanupResult>(response);
}

export async function analyzeUnknowns(): Promise<{ status: string; count: number; message: string }> {
    const response = await apiFetch(`${API_BASE}/maintenance/analyze-unknowns`, { method: 'POST' });
    return handleResponse<{ status: string; count: number; message: string }>(response);
}

export async function fetchAnalysisStatus(): Promise<{ pending: number; active: number; circuit_open: boolean }> {
    const response = await apiFetch(`${API_BASE}/maintenance/analysis/status`);
    return handleResponse<{ pending: number; active: number; circuit_open: boolean }>(response);
}

export async function deleteDetection(frigateEventId: string): Promise<{ status: string }> {
    const response = await apiFetch(`${API_BASE}/events/${encodeURIComponent(frigateEventId)}`, {
        method: 'DELETE'
    });
    return handleResponse<{ status: string }>(response);
}

export interface HideDetectionResult {
    status: string;
    event_id: string;
    is_hidden: boolean;
}

export async function hideDetection(frigateEventId: string): Promise<HideDetectionResult> {
    const response = await apiFetch(`${API_BASE}/events/${encodeURIComponent(frigateEventId)}/hide`, {
        method: 'POST'
    });
    return handleResponse<HideDetectionResult>(response);
}

export async function fetchHiddenCount(): Promise<{ hidden_count: number }> {
    const response = await apiFetch(`${API_BASE}/events/hidden-count`);
    return handleResponse<{ hidden_count: number }>(response);
}

export async function fetchSpecies(): Promise<SpeciesCount[]> {
    const response = await apiFetch(`${API_BASE}/species`);
    return handleResponse<SpeciesCount[]>(response);
}

export async function fetchSettings(): Promise<Settings> {
    // Don't use abort mechanism to avoid race conditions between
    // loadSettings() and settingsStore.load() that cancel each other
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

export async function checkHealth(): Promise<{ status: string; service: string }> {
    const response = await apiFetch('/health');
    return handleResponse<{ status: string; service: string }>(response);
}

export interface FrigateTestResult {
    status: string;
    frigate_url: string;
    version: string;
}

export async function testFrigateConnection(): Promise<FrigateTestResult> {
    const response = await apiFetch(`${API_BASE}/frigate/test`);
    return handleResponse<FrigateTestResult>(response);
}

export async function fetchFrigateConfig(): Promise<any> {
    const response = await apiFetch(`${API_BASE}/frigate/config`);
    return handleResponse<any>(response);
}

export interface ClassifierStatus {
    loaded: boolean;
    error: string | null;
    labels_count: number;
    enabled: boolean;
}

export async function fetchClassifierStatus(): Promise<ClassifierStatus> {
    const response = await apiFetch(`${API_BASE}/classifier/status`);
    return handleResponse<ClassifierStatus>(response);
}

export interface DownloadModelResult {
    status: 'ok' | 'error';
    message: string;
    labels_count?: number;
}

export async function downloadDefaultModel(): Promise<DownloadModelResult> {
    const response = await apiFetch(`${API_BASE}/classifier/download`, {
        method: 'POST',
    });
    return handleResponse<DownloadModelResult>(response);
}

export function getSnapshotUrl(frigateEvent: string): string {
    return `${API_BASE}/frigate/${frigateEvent}/snapshot.jpg`;
}

export function getThumbnailUrl(frigateEvent: string): string {
    return `${API_BASE}/frigate/${frigateEvent}/thumbnail.jpg`;
}

export function getClipUrl(frigateEvent: string): string {
    return `${API_BASE}/frigate/${frigateEvent}/clip.mp4`;
}

export async function checkClipAvailable(frigateEvent: string): Promise<boolean> {
    try {
        const response = await apiFetch(`${API_BASE}/frigate/${frigateEvent}/clip.mp4`, {
            method: 'HEAD'
        });
        return response.ok;
    } catch {
        return false;
    }
}

// Species detail types
export interface CameraStats {
    camera_name: string;
    count: number;
    percentage: number;
}

export interface SpeciesStats {
    species_name: string;
    scientific_name?: string | null;
    common_name?: string | null;
    total_sightings: number;
    first_seen: string | null;
    last_seen: string | null;
    cameras: CameraStats[];
    hourly_distribution: number[];
    daily_distribution: number[];
    monthly_distribution: number[];
    avg_confidence: number;
    max_confidence: number;
    min_confidence: number;
    recent_sightings: Detection[];
}

export interface SpeciesInfo {
    title: string;
    description: string | null;
    extract: string | null;
    thumbnail_url: string | null;
    wikipedia_url: string | null;
    source: string | null;
    source_url: string | null;
    summary_source: string | null;
    summary_source_url: string | null;
    scientific_name: string | null;
    conservation_status: string | null;
    taxa_id?: number | null;
    cached_at: string | null;
}

export interface DailyDetectionCount {
    date: string;
    count: number;
}

export interface DailyWeatherSummary {
    date: string;
    condition?: string | null;
    precip_total?: number | null;
    rain_total?: number | null;
    snow_total?: number | null;
    wind_max?: number | null;
    wind_avg?: number | null;
    cloud_avg?: number | null;
    temp_avg?: number | null;
    sunrise?: string | null;
    sunset?: string | null;
    am_condition?: string | null;
    am_rain?: number | null;
    am_snow?: number | null;
    am_wind?: number | null;
    am_cloud?: number | null;
    am_temp?: number | null;
    pm_condition?: string | null;
    pm_rain?: number | null;
    pm_snow?: number | null;
    pm_wind?: number | null;
    pm_cloud?: number | null;
    pm_temp?: number | null;
}

export interface DetectionsTimeline {
    days: number;
    total_count: number;
    daily: DailyDetectionCount[];
    weather?: DailyWeatherSummary[] | null;
}

export async function fetchSpeciesStats(speciesName: string): Promise<SpeciesStats> {
    const response = await apiFetch(`${API_BASE}/species/${encodeURIComponent(speciesName)}/stats`);
    return handleResponse<SpeciesStats>(response);
}

export async function fetchSpeciesInfo(speciesName: string): Promise<SpeciesInfo> {
    const response = await apiFetch(`${API_BASE}/species/${encodeURIComponent(speciesName)}/info`);
    return handleResponse<SpeciesInfo>(response);
}

export interface EbirdObservation {
    species_code?: string | null;
    common_name?: string | null;
    scientific_name?: string | null;
    observed_at?: string | null;
    location_name?: string | null;
    how_many?: number | null;
    lat?: number | null;
    lng?: number | null;
    obs_valid?: boolean | null;
    obs_reviewed?: boolean | null;
    thumbnail_url?: string | null;
}

export interface EbirdNearbyResult {
    status: string;
    species_name?: string | null;
    species_code?: string | null;
    warning?: string | null;
    results: EbirdObservation[];
}

export interface EbirdNotableResult {
    status: string;
    results: EbirdObservation[];
}

export async function fetchEbirdNearby(speciesName?: string, scientificName?: string): Promise<EbirdNearbyResult> {
    const params = new URLSearchParams();
    if (speciesName) params.append('species_name', speciesName);
    if (scientificName) params.append('scientific_name', scientificName);
    const response = await apiFetch(`${API_BASE}/ebird/nearby?${params.toString()}`);
    return handleResponse<EbirdNearbyResult>(response);
}

export async function fetchEbirdNotable(): Promise<EbirdNotableResult> {
    const response = await apiFetch(`${API_BASE}/ebird/notable`);
    return handleResponse<EbirdNotableResult>(response);
}

export async function exportEbirdCsv(): Promise<void> {
    const response = await apiFetch(`${API_BASE}/ebird/export`);
    if (!response.ok) {
        throw new Error('Failed to export eBird CSV');
    }
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ebird_export_${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

export async function fetchDetectionsTimeline(days = 30): Promise<DetectionsTimeline> {
    const response = await apiFetch(`${API_BASE}/stats/detections/daily?days=${days}`);
    return handleResponse<DetectionsTimeline>(response);
}

// Reclassify and manual tagging types and functions
export interface ReclassifyResult {
    status: string;
    event_id: string;
    old_species: string;
    new_species: string;
    new_score: number;
    updated: boolean;
    actual_strategy?: "snapshot" | "video";
}

export interface UpdateDetectionResult {
    status: string;
    event_id: string;
    old_species?: string;
    new_species?: string;
    species?: string;
}

export async function fetchClassifierLabels(): Promise<{ labels: string[] }> {
    const response = await apiFetch(`${API_BASE}/classifier/labels`);
    return handleResponse<{ labels: string[] }>(response);
}

export async function reclassifyDetection(eventId: string, strategy: 'snapshot' | 'video' = 'snapshot'): Promise<ReclassifyResult> {
    const params = new URLSearchParams({ strategy });
    const response = await apiFetch(`${API_BASE}/events/${encodeURIComponent(eventId)}/reclassify?${params.toString()}`, {
        method: 'POST',
    });
    return handleResponse<ReclassifyResult>(response);
}

export async function updateDetectionSpecies(eventId: string, displayName: string): Promise<UpdateDetectionResult> {
    const response = await apiFetch(`${API_BASE}/events/${encodeURIComponent(eventId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: displayName }),
    });
    return handleResponse<UpdateDetectionResult>(response);
}

// Backfill types and functions
export interface BackfillRequest {
    date_range: 'day' | 'week' | 'month' | 'custom';
    start_date?: string;  // YYYY-MM-DD format
    end_date?: string;    // YYYY-MM-DD format
    cameras?: string[];
}

export interface BackfillResult {
    status: string;
    processed: number;
    new_detections: number;
    skipped: number;
    errors: number;
    skipped_reasons?: Record<string, number>;
    message: string;
}

export async function runBackfill(request: BackfillRequest): Promise<BackfillResult> {
    const response = await apiFetch(`${API_BASE}/backfill`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
    });
    return handleResponse<BackfillResult>(response);
}

export interface WeatherBackfillRequest {
    date_range: 'day' | 'week' | 'month' | 'custom';
    start_date?: string;
    end_date?: string;
    only_missing?: boolean;
}

export interface WeatherBackfillResult {
    status: string;
    processed: number;
    updated: number;
    skipped: number;
    errors: number;
    message: string;
}

export async function runWeatherBackfill(request: WeatherBackfillRequest): Promise<WeatherBackfillResult> {
    const response = await apiFetch(`${API_BASE}/backfill/weather`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
    });
    return handleResponse<WeatherBackfillResult>(response);
}

export interface BackfillJobStatus {
    id: string;
    kind: string;
    status: string;
    processed: number;
    total: number;
    new_detections?: number;
    updated?: number;
    skipped: number;
    errors: number;
    message?: string;
    started_at?: string | null;
    finished_at?: string | null;
}

export async function startBackfillJob(request: BackfillRequest): Promise<BackfillJobStatus> {
    const response = await apiFetch(`${API_BASE}/backfill/async`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
    });
    return handleResponse<BackfillJobStatus>(response);
}

export async function startWeatherBackfillJob(request: WeatherBackfillRequest): Promise<BackfillJobStatus> {
    const response = await apiFetch(`${API_BASE}/backfill/weather/async`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
    });
    return handleResponse<BackfillJobStatus>(response);
}

export async function getBackfillStatus(kind?: 'detections' | 'weather'): Promise<BackfillJobStatus | null> {
    const params = kind ? `?kind=${kind}` : '';
    const response = await apiFetch(`${API_BASE}/backfill/status${params}`);
    return handleResponse<BackfillJobStatus | null>(response);
}

export interface ResetDatabaseResult {
    status: string;
    message: string;
    deleted_count: number;
    cache_stats: any; // Using any for brevity or match backend dict
}

export async function resetDatabase(): Promise<ResetDatabaseResult> {
    const response = await apiFetch(`${API_BASE}/backfill/reset`, { method: 'DELETE' });
    return handleResponse<ResetDatabaseResult>(response);
}

// Wildlife classification types and functions
export interface WildlifeClassification {
    label: string;
    score: number;
    index: number;
}

export interface WildlifeClassifyResult {
    status: string;
    event_id: string;
    classifications: WildlifeClassification[];
}

export interface WildlifeModelStatus {
    loaded: boolean;
    error: string | null;
    labels_count: number;
    enabled: boolean;
    model_path?: string;
}

export async function classifyWildlife(eventId: string): Promise<WildlifeClassifyResult> {
    const response = await apiFetch(`${API_BASE}/events/${encodeURIComponent(eventId)}/classify-wildlife`, {
        method: 'POST',
    });
    return handleResponse<WildlifeClassifyResult>(response);
}

export async function fetchWildlifeModelStatus(): Promise<WildlifeModelStatus> {
    const response = await apiFetch(`${API_BASE}/classifier/wildlife/status`);
    return handleResponse<WildlifeModelStatus>(response);
}

export async function fetchWildlifeLabels(): Promise<{ labels: string[] }> {
    const response = await apiFetch(`${API_BASE}/classifier/wildlife/labels`);
    return handleResponse<{ labels: string[] }>(response);
}

export async function downloadWildlifeModel(): Promise<{ status: string; message: string; labels_count?: number }> {
    const response = await apiFetch(`${API_BASE}/classifier/wildlife/download`, {
        method: 'POST',
    });
    return handleResponse<{ status: string; message: string; labels_count?: number }>(response);
}

// Media cache functions
export async function fetchCacheStats(): Promise<CacheStats> {
    const response = await apiFetch(`${API_BASE}/cache/stats`);
    return handleResponse<CacheStats>(response);
}

export async function runCacheCleanup(): Promise<CacheCleanupResult> {
    const response = await apiFetch(`${API_BASE}/cache/cleanup`, { method: 'POST' });
    return handleResponse<CacheCleanupResult>(response);
}

export interface TaxonomySyncStatus {
    is_running: boolean;
    total: number;
    processed: number;
    current_item: string | null;
    error: string | null;
}

export async function fetchTaxonomyStatus(): Promise<TaxonomySyncStatus> {
    const response = await apiFetch(`${API_BASE}/maintenance/taxonomy/status`);
    return handleResponse<TaxonomySyncStatus>(response);
}

export async function startTaxonomySync(): Promise<{ status: string }> {
    const response = await apiFetch(`${API_BASE}/maintenance/taxonomy/sync`, { method: 'POST' });
    return handleResponse<{ status: string }>(response);
}

export async function testNotification(platform: string, credentials: Record<string, unknown> = {}): Promise<{ status: string; message: string }> {
    const response = await apiFetch(`${API_BASE}/settings/notifications/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ platform, ...credentials })
    });
    return handleResponse<{ status: string; message: string }>(response);
}

export async function testBirdWeather(token?: string): Promise<{ status: string; message: string }> {
    const response = await apiFetch(`${API_BASE}/settings/birdweather/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token })
    });
    return handleResponse<{ status: string; message: string }>(response);
}

export async function testBirdNET(): Promise<{ status: string; message: string }> {
    const response = await apiFetch(`${API_BASE}/settings/birdnet/test`, { method: 'POST' });
    return handleResponse<{ status: string; message: string }>(response);
}

export async function testMQTTPublish(): Promise<{ status: string; message: string }> {
    const response = await apiFetch(`${API_BASE}/settings/mqtt/test-publish`, { method: 'POST' });
    return handleResponse<{ status: string; message: string }>(response);
}

// Model Manager types and functions
export interface ModelMetadata {
    id: string;
    name: string;
    description: string;
    architecture: string;
    file_size_mb: number;
    accuracy_tier: string;
    inference_speed: string;
    download_url: string;
    weights_url?: string;
    labels_url: string;
    input_size: number;
}

export interface InstalledModel {
    id: string;
    path: string;
    labels_path: string;
    is_active: boolean;
    metadata?: ModelMetadata;
}

export interface DownloadProgress {
    model_id: string;
    status: 'pending' | 'downloading' | 'completed' | 'error';
    progress: number;
    message?: string;
    error?: string;
}

export async function fetchAvailableModels(): Promise<ModelMetadata[]> {
    const response = await apiFetch(`${API_BASE}/models/available`);
    return handleResponse<ModelMetadata[]>(response);
}

export async function fetchInstalledModels(): Promise<InstalledModel[]> {
    const response = await apiFetch(`${API_BASE}/models/installed`);
    return handleResponse<InstalledModel[]>(response);
}

export async function downloadModel(modelId: string): Promise<{ status: string; message: string }> {
    const response = await apiFetch(`${API_BASE}/models/${modelId}/download`, {
        method: 'POST',
    });
    return handleResponse<{ status: string; message: string }>(response);
}

export async function fetchDownloadStatus(modelId: string): Promise<DownloadProgress | null> {
    const response = await apiFetch(`${API_BASE}/models/download-status/${encodeURIComponent(modelId)}`);
    return handleResponse<DownloadProgress | null>(response);
}

export async function activateModel(modelId: string): Promise<{ status: string; message: string }> {
    const response = await apiFetch(`${API_BASE}/models/${modelId}/activate`, {
        method: 'POST',
    });
    return handleResponse<{ status: string; message: string }>(response);
}

export async function analyzeDetection(eventId: string, force: boolean = false): Promise<{ analysis: string }> {
    // Use event-specific key to allow multiple analyses, but cancel if same event analyzed again
    const url = force
        ? `${API_BASE}/events/${encodeURIComponent(eventId)}/analyze?force=true`
        : `${API_BASE}/events/${encodeURIComponent(eventId)}/analyze`;
    return fetchWithAbort<{ analysis: string }>(
        `analyze-${eventId}`,
        url,
        { method: 'POST' }
    );
}

export interface LeaderboardAnalysisResponse {
    analysis: string;
    analysis_timestamp: string;
}

export async function fetchLeaderboardAnalysis(configKey: string): Promise<LeaderboardAnalysisResponse> {
    const response = await apiFetch(`${API_BASE}/leaderboard/analysis?config_key=${encodeURIComponent(configKey)}`);
    return handleResponse<LeaderboardAnalysisResponse>(response);
}

export async function analyzeLeaderboardGraph(payload: {
    config: Record<string, unknown>;
    image_base64: string;
    force?: boolean;
    config_key?: string;
}): Promise<LeaderboardAnalysisResponse> {
    const response = await apiFetch(`${API_BASE}/leaderboard/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    return handleResponse<LeaderboardAnalysisResponse>(response);
}

export interface AudioDetection {
    timestamp: string;
    species: string;
    confidence: number;
    sensor_id: string | null;
}

export async function fetchRecentAudio(limit: number = 10): Promise<AudioDetection[]> {
    const response = await apiFetch(`${API_BASE}/audio/recent?limit=${limit}`);
    return handleResponse<AudioDetection[]>(response);
}

export interface AudioContextDetection extends AudioDetection {
    offset_seconds: number;
}

export async function fetchAudioContext(
    timestamp: string,
    camera?: string,
    windowSeconds: number = 300,
    limit: number = 5
): Promise<AudioContextDetection[]> {
    const params = new URLSearchParams();
    params.set('timestamp', timestamp);
    params.set('window_seconds', String(windowSeconds));
    params.set('limit', String(limit));
    if (camera) {
        params.set('camera', camera);
    }
    const response = await apiFetch(`${API_BASE}/audio/context?${params.toString()}`);
    return handleResponse<AudioContextDetection[]>(response);
}

export interface SearchResult {
    id: string;
    display_name: string;
    scientific_name?: string | null;
    common_name?: string | null;
}

export async function searchSpecies(query: string, limit?: number): Promise<SearchResult[]> {
    const params = new URLSearchParams();
    params.set('q', query);
    if (limit !== undefined) {
        params.set('limit', String(limit));
    }
    const response = await apiFetch(`${API_BASE}/species/search?${params.toString()}`);
    return handleResponse<SearchResult[]>(response);
}

// Stats types and functions
export interface DailySpeciesSummary {
    species: string;
    count: number;
    latest_event: string;
    scientific_name?: string | null;
    common_name?: string | null;
}

export interface DailySummary {
    hourly_distribution: number[];
    top_species: DailySpeciesSummary[];
    latest_detection: Detection | null;
    total_count: number;
    audio_confirmations: number;
}

export async function fetchDailySummary(): Promise<DailySummary> {
    const response = await apiFetch(`${API_BASE}/stats/daily-summary`);
    return handleResponse<DailySummary>(response);
}

// ============================================================================
// Email / SMTP Notifications API
// ============================================================================

export interface OAuthAuthorizeResponse {
    authorization_url: string;
    state?: string;
}

export interface TestEmailRequest {
    test_subject?: string;
    test_message?: string;
}

export interface TestEmailResponse {
    message: string;
    to: string;
}

/**
 * Initiate Gmail OAuth authorization flow
 * Returns authorization URL to open in popup
 */
export async function initiateGmailOAuth(): Promise<OAuthAuthorizeResponse> {
    const response = await apiFetch(`${API_BASE}/email/oauth/gmail/authorize`);
    return handleResponse<OAuthAuthorizeResponse>(response);
}

/**
 * Initiate Outlook OAuth authorization flow
 * Returns authorization URL to open in popup
 */
export async function initiateOutlookOAuth(): Promise<OAuthAuthorizeResponse> {
    const response = await apiFetch(`${API_BASE}/email/oauth/outlook/authorize`);
    return handleResponse<OAuthAuthorizeResponse>(response);
}

/**
 * Disconnect OAuth provider and delete stored tokens
 */
export async function disconnectEmailOAuth(provider: 'gmail' | 'outlook'): Promise<{ message: string }> {
    const response = await apiFetch(`${API_BASE}/email/oauth/${provider}/disconnect`, {
        method: 'DELETE'
    });
    return handleResponse<{ message: string }>(response);
}

/**
 * Send a test email to verify configuration
 */
export async function sendTestEmail(request: TestEmailRequest = {}): Promise<TestEmailResponse> {
    const response = await apiFetch(`${API_BASE}/email/test`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
            test_subject: request.test_subject || 'YA-WAMF Test Email',
            test_message: request.test_message || 'This is a test email from YA-WAMF to verify your email configuration.'
        })
    });
    return handleResponse<TestEmailResponse>(response);
}

// ============================================================================
// iNaturalist API
// ============================================================================

export interface InaturalistDraft {
    event_id: string;
    species_guess: string;
    taxon_id?: number | null;
    observed_on_string: string;
    time_zone: string;
    latitude?: number | null;
    longitude?: number | null;
    place_guess?: string | null;
    notes?: string | null;
    snapshot_url?: string | null;
}

export interface InaturalistSubmitResult {
    status: string;
    observation_id?: number;
}

export async function initiateInaturalistOAuth(): Promise<OAuthAuthorizeResponse> {
    const response = await apiFetch(`${API_BASE}/inaturalist/oauth/authorize`);
    return handleResponse<OAuthAuthorizeResponse>(response);
}

export async function disconnectInaturalistOAuth(): Promise<{ status: string }> {
    const response = await apiFetch(`${API_BASE}/inaturalist/oauth/disconnect`, {
        method: 'DELETE'
    });
    return handleResponse<{ status: string }>(response);
}

export async function createInaturalistDraft(eventId: string): Promise<InaturalistDraft> {
    const response = await apiFetch(`${API_BASE}/inaturalist/draft`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ event_id: eventId })
    });
    return handleResponse<InaturalistDraft>(response);
}

export async function submitInaturalistObservation(payload: {
    event_id: string;
    notes?: string;
    latitude?: number | null;
    longitude?: number | null;
    place_guess?: string | null;
}): Promise<InaturalistSubmitResult> {
    const response = await apiFetch(`${API_BASE}/inaturalist/submit`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(payload)
    });
    return handleResponse<InaturalistSubmitResult>(response);
}

export interface SeasonalityResult {
    status: string;
    taxon_id: number;
    local: boolean;
    month_counts: number[];
    total_observations: number;
}

export interface SpeciesRangeMap {
    status: string;
    taxon_key?: number | null;
    map_tile_url?: string | null;
    source?: string | null;
    source_url?: string | null;
    message?: string | null;
}

export async function fetchSeasonality(taxonId: number, lat?: number, lng?: number): Promise<SeasonalityResult> {
    const params = new URLSearchParams({ taxon_id: String(taxonId) });
    if (lat !== undefined && lng !== undefined) {
        params.set('lat', String(lat));
        params.set('lng', String(lng));
    }
    const response = await apiFetch(`${API_BASE}/inaturalist/seasonality?${params.toString()}`);
    return handleResponse<SeasonalityResult>(response);
}

export async function fetchSpeciesRange(speciesName: string, scientificName?: string): Promise<SpeciesRangeMap> {
    const params = new URLSearchParams();
    if (scientificName) params.set('scientific_name', scientificName);
    const suffix = params.toString() ? `?${params.toString()}` : '';
    const response = await apiFetch(`${API_BASE}/species/${encodeURIComponent(speciesName)}/range${suffix}`);
    return handleResponse<SpeciesRangeMap>(response);
}
