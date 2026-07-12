import { API_BASE, apiFetch, handleResponse } from './core';
import type { paths } from './generated/openapi';

export type CacheStats = paths['/api/cache/stats']['get']['response'];

export type CacheCleanupResult = paths['/api/cache/cleanup']['post']['response'];

export type MaintenanceStats = paths['/api/maintenance/stats']['get']['response'];

export type CleanupResult = paths['/api/maintenance/cleanup']['post']['response'];

export type PurgeMissingMediaResult = paths['/api/maintenance/purge-missing-media']['post']['response'];

export type AnalyzeUnknownsResult = paths['/api/maintenance/analyze-unknowns']['post']['response'];

export type AnalysisStatus = paths['/api/maintenance/analysis/status']['get']['response'];

export interface ResetDatabaseResult {
    status: string;
    message: string;
    deleted_count: number;
    cache_stats: CacheStats;
}

export type ClearFeedbackResult = paths['/api/maintenance/feedback/clear']['delete']['response'];

export type TaxonomySyncStatus = paths['/api/maintenance/taxonomy/status']['get']['response'];

export type TimezoneRepairCandidate =
    paths['/api/maintenance/timezone-repair/preview']['get']['response']['candidates'][number];

export type TimezoneRepairPreview = paths['/api/maintenance/timezone-repair/preview']['get']['response'];

export type TimezoneRepairApplyResult = paths['/api/maintenance/timezone-repair/apply']['post']['response'];

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

export async function purgeMissingMedia(): Promise<PurgeMissingMediaResult> {
    const response = await apiFetch(`${API_BASE}/maintenance/purge-missing-media`, { method: 'POST' });
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

export async function startTaxonomySync(): Promise<paths['/api/maintenance/taxonomy/sync']['post']['response']> {
    const response = await apiFetch(`${API_BASE}/maintenance/taxonomy/sync`, { method: 'POST' });
    return handleResponse<paths['/api/maintenance/taxonomy/sync']['post']['response']>(response);
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
