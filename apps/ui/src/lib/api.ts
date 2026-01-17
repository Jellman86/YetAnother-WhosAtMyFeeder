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
    // Audio fields
    audio_confirmed?: boolean;
    audio_species?: string;
    audio_score?: number;
    // Weather fields
    temperature?: number;
    weather_condition?: string;
    // Taxonomy fields
    scientific_name?: string;
    common_name?: string;
    taxa_id?: number;
    // Video classification fields
    video_classification_score?: number;
    video_classification_label?: string;
    video_classification_timestamp?: string;
    video_classification_status?: 'pending' | 'processing' | 'completed' | 'failed' | null;
}

export interface VersionInfo {
    version: string;
    base_version: string;
    git_hash: string;
}

export interface SpeciesCount {
    species: string;
    count: number;
    scientific_name?: string | null;
    common_name?: string | null;
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
    // BirdWeather settings
    birdweather_enabled: boolean;
    birdweather_station_token?: string | null;
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

    // Accessibility settings
    accessibility_high_contrast: boolean;
    accessibility_dyslexia_font: boolean;
    accessibility_reduced_motion: boolean;
    accessibility_zen_mode: boolean;
    accessibility_live_announcements: boolean;
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

function getHeaders(customHeaders: HeadersInit = {}): HeadersInit {
    const headers: any = { ...customHeaders };
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
    return { 
        version: appVersion, 
        base_version: appVersionBase, 
        git_hash: __GIT_HASH__ 
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
    cached_at: string | null;
}

export async function fetchSpeciesStats(speciesName: string): Promise<SpeciesStats> {
    const response = await apiFetch(`${API_BASE}/species/${encodeURIComponent(speciesName)}/stats`);
    return handleResponse<SpeciesStats>(response);
}

export async function fetchSpeciesInfo(speciesName: string): Promise<SpeciesInfo> {
    const response = await apiFetch(`${API_BASE}/species/${encodeURIComponent(speciesName)}/info`);
    return handleResponse<SpeciesInfo>(response);
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

export async function testNotification(platform: string, credentials: any = {}): Promise<{ status: string; message: string }> {
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

export interface SearchResult {
    id: string;
    display_name: string;
    scientific_name?: string | null;
    common_name?: string | null;
}

export async function searchSpecies(query: string): Promise<SearchResult[]> {
    const response = await apiFetch(`${API_BASE}/species/search?q=${encodeURIComponent(query)}`);
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
        headers: getHeaders(),
        body: JSON.stringify({
            test_subject: request.test_subject || 'YA-WAMF Test Email',
            test_message: request.test_message || 'This is a test email from YA-WAMF to verify your email configuration.'
        })
    });
    return handleResponse<TestEmailResponse>(response);
}
