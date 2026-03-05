import { API_BASE, apiFetch, handleResponse } from './core';

export type LeaderboardSpan = 'all' | 'day' | 'week' | 'month';

export interface LeaderboardSpeciesItem {
    species: string;
    scientific_name?: string | null;
    common_name?: string | null;
    taxa_id?: number | null;
    window_count: number;
    window_prev_count: number;
    window_delta: number;
    window_percent: number;
    window_first_seen?: string | null;
    window_last_seen?: string | null;
    window_avg_confidence?: number;
    window_camera_count?: number;
}

export interface LeaderboardSpeciesResponse {
    span: LeaderboardSpan;
    window_start: string;
    window_end: string;
    species: LeaderboardSpeciesItem[];
}

export async function fetchLeaderboardSpecies(span: LeaderboardSpan = 'week'): Promise<LeaderboardSpeciesResponse> {
    const response = await apiFetch(`${API_BASE}/leaderboard/species?span=${encodeURIComponent(span)}`);
    return handleResponse<LeaderboardSpeciesResponse>(response);
}

export interface DetectionsTimelinePoint {
    bucket_start: string;
    label: string;
    count: number;
    unique_species?: number;
    avg_confidence?: number | null;
}

export interface DetectionsTimelineComparePoint {
    bucket_start: string;
    count: number;
}

export interface DetectionsTimelineCompareSeries {
    species: string;
    points: DetectionsTimelineComparePoint[];
}

export interface DetectionsTimelineSpanResponse {
    span: LeaderboardSpan;
    bucket: 'hour' | 'halfday' | 'day' | 'month';
    window_start: string;
    window_end: string;
    total_count: number;
    points: DetectionsTimelinePoint[];
    compare_series?: DetectionsTimelineCompareSeries[] | null;
    weather?: {
        bucket_start: string;
        temp_avg?: number | null;
        wind_avg?: number | null;
        precip_total?: number | null;
        rain_total?: number | null;
        snow_total?: number | null;
        condition_text?: string | null;
    }[] | null;
    sunrise_range?: string | null;
    sunset_range?: string | null;
}

export interface DetectionsActivityHeatmapCell {
    day_of_week: number;
    hour: number;
    count: number;
}

export interface DetectionsActivityHeatmapResponse {
    span: LeaderboardSpan;
    window_start: string;
    window_end: string;
    total_count: number;
    max_cell_count: number;
    cells: DetectionsActivityHeatmapCell[];
}

export async function fetchDetectionsTimelineSpan(
    span: LeaderboardSpan = 'week',
    opts: { includeWeather?: boolean; compareSpecies?: string[] } = {}
): Promise<DetectionsTimelineSpanResponse> {
    const params = new URLSearchParams();
    params.set('span', span);
    if (opts.includeWeather) params.set('include_weather', 'true');
    for (const species of opts.compareSpecies ?? []) {
        if (species) params.append('compare_species', species);
    }
    const response = await apiFetch(`${API_BASE}/stats/detections/timeline?${params.toString()}`);
    return handleResponse<DetectionsTimelineSpanResponse>(response);
}

export async function fetchDetectionsActivityHeatmapSpan(
    span: LeaderboardSpan = 'week'
): Promise<DetectionsActivityHeatmapResponse> {
    const params = new URLSearchParams();
    params.set('span', span);
    const response = await apiFetch(`${API_BASE}/stats/detections/activity-heatmap?${params.toString()}`);
    return handleResponse<DetectionsActivityHeatmapResponse>(response);
}

export interface LeaderboardAnalysisResponse {
    analysis: string;
    analysis_timestamp: string;
}

export async function fetchLeaderboardAnalysis(configKey: string): Promise<LeaderboardAnalysisResponse> {
    const response = await apiFetch(`${API_BASE}/leaderboard/analysis?config_key=${encodeURIComponent(configKey)}`);
    if (response.status === 204) {
        return { analysis: '', analysis_timestamp: '' };
    }
    return handleResponse<LeaderboardAnalysisResponse>(response);
}

export async function analyzeLeaderboardGraph(payload: {
    config: Record<string, unknown>;
    image_base64: string;
    force?: boolean;
    config_key?: string;
}): Promise<LeaderboardAnalysisResponse> {
    const response = await apiFetch(`${API_BASE}/leaderboard/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    return handleResponse<LeaderboardAnalysisResponse>(response);
}
