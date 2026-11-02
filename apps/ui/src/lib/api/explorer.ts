import { API_BASE, apiFetch, handleResponse } from './core';
import type { components } from './generated/openapi';

export type ExplorerSearchResponse = components['schemas']['ExplorerSearchResponse'];
export type ExplorerSearchTaxon = components['schemas']['ExplorerSearchTaxon'];
export type ExplorerSearchRecord = components['schemas']['ExplorerSearchRecord'];

/** Species and groups seen here, and the record an id names, as this reader may see them. */
export async function searchExplorer(query: string, signal: AbortSignal): Promise<ExplorerSearchResponse> {
    const params = new URLSearchParams({ q: query, limit: '8' });
    const response = await apiFetch(`${API_BASE}/explorer/search?${params.toString()}`, { signal, timeoutMs: 15_000 });
    return handleResponse<ExplorerSearchResponse>(response);
}
