import { toLocalYMD } from '../utils/date-only';
import { API_BASE, apiFetch, handleResponse } from './core';
import type { Detection, SpeciesCount } from './types';

export async function fetchSpecies(): Promise<SpeciesCount[]> {
    const response = await apiFetch(`${API_BASE}/species`);
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

export interface DailyDetectionCount {
    date: string;
    count: number;
}

export interface DailyWeatherSummary {
    date: string;
    condition?: string | null;
    precip_total?: number | null;
    rain_total?: number | null;
    snow_total?: number | null;
    wind_max?: number | null;
    wind_avg?: number | null;
    cloud_avg?: number | null;
    temp_avg?: number | null;
    sunrise?: string | null;
    sunset?: string | null;
    am_condition?: string | null;
    am_rain?: number | null;
    am_snow?: number | null;
    am_wind?: number | null;
    am_cloud?: number | null;
    am_temp?: number | null;
    pm_condition?: string | null;
    pm_rain?: number | null;
    pm_snow?: number | null;
    pm_wind?: number | null;
    pm_cloud?: number | null;
    pm_temp?: number | null;
}

export interface DetectionsTimeline {
    days: number;
    total_count: number;
    daily: DailyDetectionCount[];
    weather?: DailyWeatherSummary[] | null;
}

export async function fetchSpeciesStats(speciesName: string): Promise<SpeciesStats> {
    const response = await apiFetch(`${API_BASE}/species/${encodeURIComponent(speciesName)}/stats`);
    return handleResponse<SpeciesStats>(response);
}

export async function fetchSpeciesInfo(speciesName: string): Promise<SpeciesInfo> {
    const response = await apiFetch(`${API_BASE}/species/${encodeURIComponent(speciesName)}/info`);
    return handleResponse<SpeciesInfo>(response);
}

export interface EbirdObservation {
    species_code?: string | null;
    common_name?: string | null;
    scientific_name?: string | null;
    observed_at?: string | null;
    location_name?: string | null;
    how_many?: number | null;
    lat?: number | null;
    lng?: number | null;
    obs_valid?: boolean | null;
    obs_reviewed?: boolean | null;
    thumbnail_url?: string | null;
}

export interface EbirdNearbyResult {
    status: string;
    species_name?: string | null;
    species_code?: string | null;
    warning?: string | null;
    results: EbirdObservation[];
}

export interface EbirdNotableResult {
    status: string;
    results: EbirdObservation[];
}

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

export async function exportEbirdCsv(date?: string): Promise<void> {
    const params = new URLSearchParams();
    if (date) {
        params.set('date', date);
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

export interface SearchResult {
    id: string;
    display_name: string;
    scientific_name?: string | null;
    common_name?: string | null;
}

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

export interface SeasonalityResult {
    status: string;
    taxon_id: number;
    local: boolean;
    month_counts: number[];
    total_observations: number;
}

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
