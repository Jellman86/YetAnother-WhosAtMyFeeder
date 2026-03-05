import { API_BASE, apiFetch, handleResponse } from './core';
import type { Detection } from './types';

export interface DailySpeciesSummary {
    species: string;
    count: number;
    latest_event: string;
    scientific_name?: string | null;
    common_name?: string | null;
    taxa_id?: number | null;
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

export interface AIUsageBreakdown {
    provider: string;
    model: string;
    feature: string;
    calls: number;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    estimated_cost_usd: number;
}

export interface AIUsageDaily {
    day: string;
    calls: number;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
}

export interface AIUsageResponse {
    span: string;
    from_date: string;
    to_date: string;
    calls: number;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    estimated_cost_usd: number;
    pricing_configured: boolean;
    breakdown: AIUsageBreakdown[];
    daily: AIUsageDaily[];
}

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
