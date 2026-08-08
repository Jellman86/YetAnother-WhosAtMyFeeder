import { toLocalYMD } from '../utils/date-only';
import { API_BASE, apiFetch, handleResponse } from './core';
import type { Detection, SpeciesCount } from './types';
import type { paths } from './generated/openapi';

export async function fetchSpecies(signal?: AbortSignal): Promise<SpeciesCount[]> {
    const response = await apiFetch(`${API_BASE}/species`, { signal, timeoutMs: 15_000 });
    return handleResponse<SpeciesCount[]>(response);
}

export interface CameraStats {
    camera_name: string;
    count: number;
    percentage: number;
}

export interface SpeciesStats {
    species_name: string;
    scientific_name?: string | null;
    common_name?: string | null;
    total_sightings: number;
    first_seen: string | null;
    last_seen: string | null;
    cameras: CameraStats[];
    hourly_distribution: number[];
    daily_distribution: number[];
    monthly_distribution: number[];
    avg_confidence: number;
    max_confidence: number;
    min_confidence: number;
    recent_sightings: Detection[];
}

export interface SpeciesInfo {
    title: string;
    description: string | null;
    extract: string | null;
    thumbnail_url: string | null;
    wikipedia_url: string | null;
    source: string | null;
    source_url: string | null;
    summary_source: string | null;
    summary_source_url: string | null;
    scientific_name: string | null;
    conservation_status: string | null;
    taxa_id?: number | null;
    cached_at: string | null;
}

export type DetectionsTimeline = paths['/api/stats/detections/daily']['get']['response'];
export type DailyDetectionCount = DetectionsTimeline['daily'][number];
export type DailyWeatherSummary = NonNullable<DetectionsTimeline['weather']>[number];

export async function fetchSpeciesStats(speciesName: string): Promise<SpeciesStats> {
    const response = await apiFetch(`${API_BASE}/species/${encodeURIComponent(speciesName)}/stats`);
    return handleResponse<SpeciesStats>(response);
}

export async function fetchSpeciesInfo(speciesName: string, signal?: AbortSignal): Promise<SpeciesInfo> {
    const response = await apiFetch(`${API_BASE}/species/${encodeURIComponent(speciesName)}/info`, {
        signal,
        timeoutMs: 15_000
    });
    return handleResponse<SpeciesInfo>(response);
}

export interface CommonNameOverride {
    scientific_name: string;
    provider_common_name: string | null;
    manual_common_name: string | null;
    effective_common_name: string | null;
}

export async function fetchCommonNameOverride(scientificName: string): Promise<CommonNameOverride> {
    const params = new URLSearchParams({ scientific_name: scientificName });
    const response = await apiFetch(`${API_BASE}/species/common-name-override?${params.toString()}`);
    return handleResponse<CommonNameOverride>(response);
}

export async function setCommonNameOverride(
    scientificName: string,
    commonName: string
): Promise<CommonNameOverride> {
    const response = await apiFetch(`${API_BASE}/species/common-name-override`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scientific_name: scientificName, common_name: commonName })
    });
    return handleResponse<CommonNameOverride>(response);
}

export async function clearCommonNameOverride(scientificName: string): Promise<CommonNameOverride> {
    const params = new URLSearchParams({ scientific_name: scientificName });
    const response = await apiFetch(`${API_BASE}/species/common-name-override?${params.toString()}`, {
        method: 'DELETE'
    });
    return handleResponse<CommonNameOverride>(response);
}

export type EbirdNearbyResult = paths['/api/ebird/nearby']['get']['response'];
export type EbirdNotableResult = paths['/api/ebird/notable']['get']['response'];
export type EbirdObservation = EbirdNearbyResult['results'][number];

export async function fetchEbirdNearby(speciesName?: string, scientificName?: string): Promise<EbirdNearbyResult> {
    const params = new URLSearchParams();
    if (speciesName) params.append('species_name', speciesName);
    if (scientificName) params.append('scientific_name', scientificName);
    const response = await apiFetch(`${API_BASE}/ebird/nearby?${params.toString()}`);
    return handleResponse<EbirdNearbyResult>(response);
}

export async function fetchEbirdNotable(): Promise<EbirdNotableResult> {
    const response = await apiFetch(`${API_BASE}/ebird/notable`);
    return handleResponse<EbirdNotableResult>(response);
}

export interface EbirdExportRange {
    from?: string;
    to?: string;
}

export async function exportEbirdCsv(range?: EbirdExportRange): Promise<void> {
    const params = new URLSearchParams();
    if (range?.from) {
        params.set('from', range.from);
    }
    if (range?.to) {
        params.set('to', range.to);
    }
    const suffix = params.toString() ? `?${params.toString()}` : '';
    const response = await apiFetch(`${API_BASE}/ebird/export${suffix}`);
    if (!response.ok) {
        throw new Error('Failed to export eBird CSV');
    }
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ebird_export_${toLocalYMD()}.csv`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

export async function fetchDetectionsTimeline(days = 30): Promise<DetectionsTimeline> {
    const response = await apiFetch(`${API_BASE}/stats/detections/daily?days=${days}`);
    return handleResponse<DetectionsTimeline>(response);
}

export type SearchResult = paths['/api/species/search']['get']['response'][number];

export async function searchSpecies(query: string, limit?: number, hydrateMissing: boolean = false): Promise<SearchResult[]> {
    const params = new URLSearchParams();
    params.set('q', query);
    if (limit !== undefined) {
        params.set('limit', String(limit));
    }
    if (hydrateMissing) {
        params.set('hydrate_missing', 'true');
    }
    const response = await apiFetch(`${API_BASE}/species/search?${params.toString()}`);
    return handleResponse<SearchResult[]>(response);
}

export type SeasonalityResult = paths['/api/inaturalist/seasonality']['get']['response'];

export interface SpeciesRangeMap {
    status: string;
    taxon_key?: number | null;
    map_tile_url?: string | null;
    source?: string | null;
    source_url?: string | null;
    message?: string | null;
}

export async function fetchSeasonality(taxonId: number, lat?: number, lng?: number): Promise<SeasonalityResult> {
    const params = new URLSearchParams({ taxon_id: String(taxonId) });
    if (lat !== undefined && lng !== undefined) {
        params.set('lat', String(lat));
        params.set('lng', String(lng));
    }
    const response = await apiFetch(`${API_BASE}/inaturalist/seasonality?${params.toString()}`);
    return handleResponse<SeasonalityResult>(response);
}

export async function fetchSpeciesRange(speciesName: string, scientificName?: string): Promise<SpeciesRangeMap> {
    const params = new URLSearchParams();
    if (scientificName) params.set('scientific_name', scientificName);
    const suffix = params.toString() ? `?${params.toString()}` : '';
    const response = await apiFetch(`${API_BASE}/species/${encodeURIComponent(speciesName)}/range${suffix}`);
    return handleResponse<SpeciesRangeMap>(response);
}
