import { API_BASE, apiFetch, handleResponse } from './core';
import type { paths } from './generated/openapi';

export type LeaderboardSpan = 'all' | paths['/api/leaderboard/species']['get']['query']['span'];

export type LeaderboardSpeciesItem = paths['/api/leaderboard/species']['get']['response']['species'][number];

export type LeaderboardSpeciesResponse = paths['/api/leaderboard/species']['get']['response'];

export async function fetchLeaderboardSpecies(
    span: LeaderboardSpan = 'week',
    signal?: AbortSignal
): Promise<LeaderboardSpeciesResponse> {
    const response = await apiFetch(`${API_BASE}/leaderboard/species?span=${encodeURIComponent(span)}`, {
        signal,
        timeoutMs: 15_000
    });
    return handleResponse<LeaderboardSpeciesResponse>(response);
}

export type DetectionsTimelinePoint =
    paths['/api/stats/detections/timeline']['get']['response']['points'][number];

export type DetectionsTimelineComparePoint = NonNullable<
    paths['/api/stats/detections/timeline']['get']['response']['compare_series']
>[number]['points'][number];

export type DetectionsTimelineCompareSeries = NonNullable<
    paths['/api/stats/detections/timeline']['get']['response']['compare_series']
>[number];

export type DetectionsTimelineSpanResponse = paths['/api/stats/detections/timeline']['get']['response'];

export type DetectionsActivityHeatmapCell =
    paths['/api/stats/detections/activity-heatmap']['get']['response']['cells'][number];

export type DetectionsActivityHeatmapResponse = paths['/api/stats/detections/activity-heatmap']['get']['response'];

export async function fetchDetectionsTimelineSpan(
    span: LeaderboardSpan = 'week',
    opts: { includeWeather?: boolean; compareSpecies?: string[]; signal?: AbortSignal } = {}
): Promise<DetectionsTimelineSpanResponse> {
    const params = new URLSearchParams();
    params.set('span', span);
    if (opts.includeWeather) params.set('include_weather', 'true');
    for (const species of opts.compareSpecies ?? []) {
        if (species) params.append('compare_species', species);
    }
    const response = await apiFetch(`${API_BASE}/stats/detections/timeline?${params.toString()}`, {
        signal: opts.signal,
        timeoutMs: 15_000
    });
    return handleResponse<DetectionsTimelineSpanResponse>(response);
}

export async function fetchDetectionsActivityHeatmapSpan(
    span: LeaderboardSpan = 'week',
    signal?: AbortSignal
): Promise<DetectionsActivityHeatmapResponse> {
    const params = new URLSearchParams();
    params.set('span', span);
    const response = await apiFetch(`${API_BASE}/stats/detections/activity-heatmap?${params.toString()}`, {
        signal,
        timeoutMs: 15_000
    });
    return handleResponse<DetectionsActivityHeatmapResponse>(response);
}

export type LeaderboardAnalysisResponse = paths['/api/leaderboard/analysis']['get']['response'];

export async function fetchLeaderboardAnalysis(configKey: string): Promise<LeaderboardAnalysisResponse> {
    const response = await apiFetch(`${API_BASE}/leaderboard/analysis?config_key=${encodeURIComponent(configKey)}`);
    if (response.status === 204) {
        return { analysis: '', analysis_timestamp: '' };
    }
    return handleResponse<LeaderboardAnalysisResponse>(response);
}

export async function analyzeLeaderboardGraph(
    payload: paths['/api/leaderboard/analyze']['post']['requestBody']
): Promise<LeaderboardAnalysisResponse> {
    const response = await apiFetch(`${API_BASE}/leaderboard/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    return handleResponse<LeaderboardAnalysisResponse>(response);
}

export type UptimeWindowResponse = paths['/api/stats/uptime']['get']['response'];

export async function fetchUptimeWindow(
    hours: number = 24,
    signal?: AbortSignal
): Promise<UptimeWindowResponse> {
    const params = new URLSearchParams({ hours: String(hours) });
    const response = await apiFetch(`${API_BASE}/stats/uptime?${params.toString()}`, { signal });
    return handleResponse<UptimeWindowResponse>(response);
}
