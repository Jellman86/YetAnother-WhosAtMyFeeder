import { API_BASE, apiFetch, handleResponse } from './core';

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

export interface PurgeMissingMediaResult {
    status: string;
    deleted_count: number;
    checked: number;
    missing: number;
    message?: string;
}

export interface AnalyzeUnknownsResult {
    status: string;
    count: number;
    message: string;
    accepted?: number;
    skipped_duplicate?: number;
    dropped_full?: number;
    skipped_no_clip?: number;
    skipped_missing_event?: number;
    skipped_outside_retention?: number;
    precheck_errors?: number;
    total_candidates?: number;
}

export interface AnalysisStatus {
    pending: number;
    active: number;
    circuit_open: boolean;
    open_until?: string | null;
    failure_count?: number;
    pending_capacity?: number;
    pending_available?: number;
    max_concurrent_configured?: number;
    max_concurrent_effective?: number;
    mqtt_pressure_level?: string;
    throttled_for_mqtt_pressure?: boolean;
    throttled_for_live_pressure?: boolean;
    maintenance_starvation_relief_active?: boolean;
    live_pressure_active?: boolean;
    live_in_flight?: number;
    live_queued?: number;
    mqtt_in_flight?: number;
    mqtt_in_flight_capacity?: number;
    oldest_maintenance_pending_age_seconds?: number;
}

export interface ResetDatabaseResult {
    status: string;
    message: string;
    deleted_count: number;
    cache_stats: any;
}

export interface ClearFeedbackResult {
    status: string;
    message: string;
    deleted_count: number;
}

export interface TaxonomySyncStatus {
    is_running: boolean;
    total: number;
    processed: number;
    current_item: string | null;
    error: string | null;
}

export interface TimezoneRepairCandidate {
    detection_id: number;
    frigate_event: string;
    camera_name: string;
    display_name: string;
    status: 'ok' | 'repair_candidate' | 'missing_frigate_event' | 'unsupported_delta' | string;
    stored_detection_time: string;
    frigate_start_time: string | null;
    repaired_detection_time: string | null;
    delta_hours: number | null;
    error?: string | null;
}

export interface TimezoneRepairPreview {
    summary: {
        scanned_count: number;
        repair_candidate_count: number;
        ok_count: number;
        missing_frigate_event_count: number;
        lookup_error_count: number;
        unsupported_delta_count: number;
    };
    candidates: TimezoneRepairCandidate[];
}

export interface TimezoneRepairApplyResult {
    status: string;
    repaired_count: number;
    skipped_count: number;
    preview: TimezoneRepairPreview;
}

export async function fetchMaintenanceStats(): Promise<MaintenanceStats> {
    const response = await apiFetch(`${API_BASE}/maintenance/stats`);
    return handleResponse<MaintenanceStats>(response);
}

export async function runCleanup(): Promise<CleanupResult> {
    const response = await apiFetch(`${API_BASE}/maintenance/cleanup`, { method: 'POST' });
    return handleResponse<CleanupResult>(response);
}

export async function clearAllFavorites(): Promise<CleanupResult> {
    const response = await apiFetch(`${API_BASE}/maintenance/favorites/clear`, { method: 'POST' });
    return handleResponse<CleanupResult>(response);
}

export async function purgeMissingClips(): Promise<PurgeMissingMediaResult> {
    const response = await apiFetch(`${API_BASE}/maintenance/purge-missing-clips`, { method: 'POST' });
    return handleResponse<PurgeMissingMediaResult>(response);
}

export async function purgeMissingSnapshots(): Promise<PurgeMissingMediaResult> {
    const response = await apiFetch(`${API_BASE}/maintenance/purge-missing-snapshots`, { method: 'POST' });
    return handleResponse<PurgeMissingMediaResult>(response);
}

export async function analyzeUnknowns(): Promise<AnalyzeUnknownsResult> {
    const response = await apiFetch(`${API_BASE}/maintenance/analyze-unknowns`, { method: 'POST' });
    return handleResponse<AnalyzeUnknownsResult>(response);
}

export async function fetchAnalysisStatus(): Promise<AnalysisStatus> {
    const response = await apiFetch(`${API_BASE}/maintenance/analysis/status`, { cache: 'no-store' });
    return handleResponse<AnalysisStatus>(response);
}

export async function resetVideoCircuit(): Promise<{ status: string; message: string }> {
    const response = await apiFetch(`${API_BASE}/maintenance/video-classification/reset-circuit`, { method: 'POST' });
    return handleResponse<{ status: string; message: string }>(response);
}

export async function resetDatabase(): Promise<ResetDatabaseResult> {
    const response = await apiFetch(`${API_BASE}/backfill/reset`, { method: 'DELETE' });
    return handleResponse<ResetDatabaseResult>(response);
}

export async function clearClassificationFeedback(): Promise<ClearFeedbackResult> {
    const response = await apiFetch(`${API_BASE}/maintenance/feedback/clear`, { method: 'DELETE' });
    return handleResponse<ClearFeedbackResult>(response);
}

export async function fetchCacheStats(): Promise<CacheStats> {
    const response = await apiFetch(`${API_BASE}/cache/stats`);
    return handleResponse<CacheStats>(response);
}

export async function runCacheCleanup(): Promise<CacheCleanupResult> {
    const response = await apiFetch(`${API_BASE}/cache/cleanup`, { method: 'POST' });
    return handleResponse<CacheCleanupResult>(response);
}

export async function fetchTaxonomyStatus(): Promise<TaxonomySyncStatus> {
    const response = await apiFetch(`${API_BASE}/maintenance/taxonomy/status`);
    return handleResponse<TaxonomySyncStatus>(response);
}

export async function startTaxonomySync(): Promise<{ status: string }> {
    const response = await apiFetch(`${API_BASE}/maintenance/taxonomy/sync`, { method: 'POST' });
    return handleResponse<{ status: string }>(response);
}

export async function fetchTimezoneRepairPreview(): Promise<TimezoneRepairPreview> {
    const response = await apiFetch(`${API_BASE}/maintenance/timezone-repair/preview`, { cache: 'no-store' });
    return handleResponse<TimezoneRepairPreview>(response);
}

export async function applyTimezoneRepair(): Promise<TimezoneRepairApplyResult> {
    const response = await apiFetch(`${API_BASE}/maintenance/timezone-repair/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirm: true })
    });
    return handleResponse<TimezoneRepairApplyResult>(response);
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

export async function testLlm(config: {
    llm_enabled?: boolean;
    llm_provider?: string;
    llm_model?: string;
    llm_api_key?: string;
}): Promise<{ status: string; message: string }> {
    const response = await apiFetch(`${API_BASE}/settings/llm/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
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
