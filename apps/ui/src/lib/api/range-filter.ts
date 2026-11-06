import { API_BASE, apiFetch, handleResponse } from './core';
import type { components } from './generated/openapi';

export type RangeFilterStatus = components['schemas']['RangeFilterStatus'];
export type RangeFilterPreview = components['schemas']['RangeFilterPreview'];
export type RangePreviewSpecies = components['schemas']['RangePreviewSpecies'];
export type RangeSkip = components['schemas']['RangeSkip'];
export type RangeDecisionDetail = components['schemas']['RangeDecisionDetail'];

/** A status without its reason cannot say what the filter is doing, so it is an error, not a blank panel. */
function checkedStatus(status: RangeFilterStatus): RangeFilterStatus {
    if (typeof status?.reason !== 'string') throw new Error('The server sent an incomplete range filter status.');
    return status;
}

export async function fetchRangeFilterStatus(): Promise<RangeFilterStatus> {
    return checkedStatus(await handleResponse<RangeFilterStatus>(await apiFetch(`${API_BASE}/range-filter/status`)));
}

export async function refreshRangeList(): Promise<RangeFilterStatus> {
    return checkedStatus(
        await handleResponse<RangeFilterStatus>(await apiFetch(`${API_BASE}/range-filter/refresh`, { method: 'POST' }))
    );
}

export async function fetchRangeFilterPreview(): Promise<RangeFilterPreview> {
    const preview = await handleResponse<RangeFilterPreview>(await apiFetch(`${API_BASE}/range-filter/preview`));
    return {
        ...preview,
        available: preview?.available === true,
        recently_seen: Array.isArray(preview?.recently_seen) ? preview.recently_seen : [],
        examples: Array.isArray(preview?.examples) ? preview.examples : []
    };
}

export async function fetchRangeFilterSkips(limit = 10): Promise<RangeSkip[]> {
    const response = await apiFetch(`${API_BASE}/range-filter/skips?limit=${encodeURIComponent(String(limit))}`);
    const items = (await handleResponse<components['schemas']['RangeSkipsResponse']>(response))?.items;
    return Array.isArray(items) ? items : [];
}

export async function fetchRangeDecision(frigateEvent: string): Promise<RangeDecisionDetail | null> {
    const response = await apiFetch(`${API_BASE}/range-filter/decisions/${encodeURIComponent(frigateEvent)}`);
    return (await handleResponse<components['schemas']['RangeDecisionResponse']>(response))?.decision ?? null;
}
