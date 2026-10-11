import { API_BASE, apiFetch, handleResponse } from './core';
import type { components } from './generated/openapi';

export type Taxon = components['schemas']['TaxonResponse'];
type TaxonLineage = components['schemas']['TaxonLineageResponse'];
type TaxonChildren = components['schemas']['TaxonChildrenResponse'];

/** Where a species sits, by scientific name, root first, with what was seen here beneath each rank. */
export async function fetchSpeciesLineage(scientificName: string, signal?: AbortSignal): Promise<TaxonLineage> {
    const params = new URLSearchParams({ scientific_name: scientificName });
    const response = await apiFetch(`${API_BASE}/taxonomy/lineage?${params.toString()}`, { signal, timeoutMs: 15_000 });
    return handleResponse<TaxonLineage>(response);
}

/** The taxa directly beneath one, in the source's order. */
export async function fetchTaxonChildren(taxonId: number, signal?: AbortSignal): Promise<TaxonChildren> {
    const response = await apiFetch(`${API_BASE}/taxonomy/${encodeURIComponent(String(taxonId))}/children`, {
        signal,
        timeoutMs: 15_000
    });
    return handleResponse<TaxonChildren>(response);
}
