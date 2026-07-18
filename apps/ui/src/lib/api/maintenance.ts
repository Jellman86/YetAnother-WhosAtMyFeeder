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
    const response = await apiFetch(`${API_BASE}/maintenance/analysis/status`, {
        cache: 'no-store',
        timeoutMs: 10_000
    });
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
    const response = await apiFetch(`${API_BASE}/cache/stats`, { timeoutMs: 10_000 });
    return handleResponse<CacheStats>(response);
}

export async function runCacheCleanup(): Promise<CacheCleanupResult> {
    const response = await apiFetch(`${API_BASE}/cache/cleanup`, { method: 'POST' });
    return handleResponse<CacheCleanupResult>(response);
}

export async function fetchTaxonomyStatus(): Promise<TaxonomySyncStatus> {
    const response = await apiFetch(`${API_BASE}/maintenance/taxonomy/status`, { timeoutMs: 10_000 });
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

type LlmTestApiResponse = paths['/api/settings/llm/test']['post']['response'];
export type LlmTestFailureStage = NonNullable<LlmTestApiResponse['failure_stage']>;
export type LlmTestResult = LlmTestApiResponse & {
    failure_stage: LlmTestFailureStage | null;
    retryable: boolean;
    retry_after_seconds: number | null;
    http_status: number;
};

function readLlmTestResult(raw: unknown, httpStatus: number): LlmTestResult {
    const data = raw && typeof raw === 'object' ? raw as Record<string, unknown> : {};
    const failureStage = data.failure_stage;
    const validFailureStages: LlmTestFailureStage[] = [
        'configuration',
        'provider',
        'vision',
        'multi_frame',
        'response'
    ];
    return {
        status: data.status === 'ok' ? 'ok' : 'error',
        message: typeof data.message === 'string' ? data.message : `AI test failed (HTTP ${httpStatus}).`,
        provider: typeof data.provider === 'string' ? data.provider : '',
        model: typeof data.model === 'string' ? data.model : '',
        frame_count: typeof data.frame_count === 'number' ? data.frame_count : 5,
        failure_stage: typeof failureStage === 'string' && validFailureStages.includes(failureStage as LlmTestFailureStage)
            ? failureStage as LlmTestFailureStage
            : null,
        retryable: data.retryable === true,
        retry_after_seconds: typeof data.retry_after_seconds === 'number' ? data.retry_after_seconds : null,
        http_status: httpStatus
    };
}

export async function testLlm(
    config: paths['/api/settings/llm/test']['post']['requestBody']
): Promise<LlmTestResult> {
    const response = await apiFetch(`${API_BASE}/settings/llm/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
    });
    const payload: unknown = await response.json();
    return readLlmTestResult(payload, response.status);
}

export async function testBirdNET(): Promise<{ status: string; message: string }> {
    const response = await apiFetch(`${API_BASE}/settings/birdnet/test`, { method: 'POST' });
    return handleResponse<{ status: string; message: string }>(response);
}

export async function checkBirdNetReachability(): Promise<{ status: string; message: string }> {
    const response = await apiFetch(`${API_BASE}/settings/birdnet/reachability`);
    return handleResponse<{ status: string; message: string }>(response);
}

export async function testMQTTPublish(): Promise<{ status: string; message: string }> {
    const response = await apiFetch(`${API_BASE}/settings/mqtt/test-publish`, { method: 'POST' });
    return handleResponse<{ status: string; message: string }>(response);
}
