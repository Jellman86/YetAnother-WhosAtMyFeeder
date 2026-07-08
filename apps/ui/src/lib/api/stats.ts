import { API_BASE, apiFetch, handleResponse } from './core';
import type { paths } from './generated/openapi';

export type DailySpeciesSummary = paths['/api/stats/daily-summary']['get']['response']['top_species'][number];
export type DailySummary = paths['/api/stats/daily-summary']['get']['response'];

export async function fetchDailySummary(): Promise<DailySummary> {
    const response = await apiFetch(`${API_BASE}/stats/daily-summary`);
    return handleResponse<DailySummary>(response);
}

export type AIUsageBreakdown = paths['/api/stats/ai/usage']['get']['response']['breakdown'][number];
export type AIUsageDaily = paths['/api/stats/ai/usage']['get']['response']['daily'][number];
export type AIUsageResponse = paths['/api/stats/ai/usage']['get']['response'];

export async function fetchAiUsage(span: string = '30d'): Promise<AIUsageResponse> {
    const response = await apiFetch(`${API_BASE}/stats/ai/usage?span=${span}`);
    return handleResponse<AIUsageResponse>(response);
}

export async function clearAiUsage(): Promise<{ status: string; deleted_count: number }> {
    const response = await apiFetch(`${API_BASE}/stats/ai/usage`, {
        method: 'DELETE'
    });
    return handleResponse<{ status: string; deleted_count: number }>(response);
}
