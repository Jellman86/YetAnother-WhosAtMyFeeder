import { API_BASE, apiFetch, handleResponse } from './core';
import type { components } from './generated/openapi';

export type Taxon = components['schemas']['TaxonResponse'];
type TaxonLineage = components['schemas']['TaxonLineageResponse'];
type TaxonChildren = components['schemas']['TaxonChildrenResponse'];
export type TaxonFacts = components['schemas']['TaxonFactsItem'];
export type TaxonFactsPage = components['schemas']['TaxonFactsResponse'];
export type TaxonPhoto = components['schemas']['TaxonPhotoResponse'];
export type TaxonOtherName = components['schemas']['TaxonOtherNameResponse'];
export type TaxonNames = components['schemas']['TaxonNamesResponse'];

/** Where a species sits, by scientific name, root first, with what was seen here beneath each rank. */
export async function fetchSpeciesLineage(scientificName: string, signal?: AbortSignal): Promise<TaxonLineage> {
    const params = new URLSearchParams({ scientific_name: scientificName });
    const response = await apiFetch(`${API_BASE}/taxonomy/lineage?${params.toString()}`, { signal, timeoutMs: 15_000 });
    return handleResponse<TaxonLineage>(response);
}

/** Where a taxon sits, root first; the last entry is the taxon itself. */
export async function fetchTaxonLineage(taxonId: number, signal?: AbortSignal): Promise<TaxonLineage> {
    const response = await apiFetch(`${API_BASE}/taxonomy/${encodeURIComponent(String(taxonId))}/lineage`, {
        signal,
        timeoutMs: 15_000
    });
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

/** What this install recorded of each taxon, one open level of the tree in one request. */
export async function fetchTaxonFacts(taxonIds: readonly number[], signal?: AbortSignal): Promise<TaxonFactsPage> {
    const params = new URLSearchParams(taxonIds.map((id) => ['ids', String(id)]));
    const response = await apiFetch(`${API_BASE}/taxonomy/facts?${params.toString()}`, { signal, timeoutMs: 15_000 });
    return handleResponse<TaxonFactsPage>(response);
}

/** A taxon's common names in the catalogue's other languages. */
export async function fetchTaxonNames(taxonId: number, signal?: AbortSignal): Promise<TaxonNames> {
    const response = await apiFetch(`${API_BASE}/taxonomy/${encodeURIComponent(String(taxonId))}/names`, {
        signal,
        timeoutMs: 15_000
    });
    return handleResponse<TaxonNames>(response);
}
