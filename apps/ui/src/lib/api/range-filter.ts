import { API_BASE, apiFetch, handleResponse } from './core';
import type { components } from './generated/openapi';

export type RangeFilterStatus = components['schemas']['RangeFilterStatus'];
export type RangeFilterPreview = components['schemas']['RangeFilterPreview'];
export type RangePreviewSpecies = components['schemas']['RangePreviewSpecies'];
export type RangeSkip = components['schemas']['RangeSkip'];
export type RangeDecisionDetail = components['schemas']['RangeDecisionDetail'];

export async function fetchRangeFilterStatus(): Promise<RangeFilterStatus> {
    return handleResponse<RangeFilterStatus>(await apiFetch(`${API_BASE}/range-filter/status`));
}

export async function refreshRangeList(): Promise<RangeFilterStatus> {
    return handleResponse<RangeFilterStatus>(await apiFetch(`${API_BASE}/range-filter/refresh`, { method: 'POST' }));
}

export async function fetchRangeFilterPreview(): Promise<RangeFilterPreview> {
    return handleResponse<RangeFilterPreview>(await apiFetch(`${API_BASE}/range-filter/preview`));
}

export async function fetchRangeFilterSkips(limit = 10): Promise<RangeSkip[]> {
    const response = await apiFetch(`${API_BASE}/range-filter/skips?limit=${encodeURIComponent(String(limit))}`);
    return (await handleResponse<components['schemas']['RangeSkipsResponse']>(response)).items;
}

export async function fetchRangeDecision(frigateEvent: string): Promise<RangeDecisionDetail | null> {
    const response = await apiFetch(`${API_BASE}/range-filter/decisions/${encodeURIComponent(frigateEvent)}`);
    return (await handleResponse<components['schemas']['RangeDecisionResponse']>(response)).decision ?? null;
}
