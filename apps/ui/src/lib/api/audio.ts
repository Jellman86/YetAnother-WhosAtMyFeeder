import { API_BASE, apiFetch, handleResponse } from './core';
import type { LeaderboardSpan } from './leaderboard';

export interface AudioDetection {
    timestamp: string;
    species: string;
    confidence: number;
    sensor_id: string | null;
    source_name?: string | null;
    birdnet_id?: number | null;
}

export interface AudioHistoryDetection extends AudioDetection {
    id: number;
}

export interface AudioHistoryParams {
    days?: number;
    start_date?: string;
    end_date?: string;
    species?: string;
    source?: string;
    min_confidence?: number;
    limit?: number;
    offset?: number;
}

export interface AudioHistoryResponse {
    items: AudioHistoryDetection[];
    total: number;
    limit: number;
    offset: number;
}

export interface AudioSpeciesSummary {
    species: string;
    count: number;
    avg_confidence: number;
    max_confidence: number;
    first_heard?: string | null;
    last_heard?: string | null;
}

export interface AudioDailyCount {
    date: string;
    count: number;
}

export interface AudioHourlyCount {
    hour: number;
    count: number;
}

export interface AudioSourceSummary {
    source_name: string;
    count: number;
    last_heard: string;
}

export interface AudioSummaryResponse {
    total: number;
    species_count: number;
    source_count: number;
    top_species: AudioSpeciesSummary[];
    daily_counts: AudioDailyCount[];
    hourly_counts: AudioHourlyCount[];
    sources: AudioSourceSummary[];
}

export async function fetchRecentAudio(limit: number = 10): Promise<AudioDetection[]> {
    const response = await apiFetch(`${API_BASE}/audio/recent?limit=${limit}`);
    return handleResponse<AudioDetection[]>(response);
}

function buildAudioHistoryParams(params: AudioHistoryParams = {}): URLSearchParams {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
        if (value === undefined || value === null || value === '') continue;
        query.set(key, String(value));
    }
    return query;
}

export async function fetchAudioHistory(params: AudioHistoryParams = {}): Promise<AudioHistoryResponse> {
    const query = buildAudioHistoryParams(params);
    const response = await apiFetch(`${API_BASE}/audio/history?${query.toString()}`);
    return handleResponse<AudioHistoryResponse>(response);
}

export async function fetchAudioSummary(params: Omit<AudioHistoryParams, 'limit' | 'offset'> = {}): Promise<AudioSummaryResponse> {
    const query = buildAudioHistoryParams(params);
    const response = await apiFetch(`${API_BASE}/audio/summary?${query.toString()}`);
    return handleResponse<AudioSummaryResponse>(response);
}

export interface AudioSpeciesLeaderboardItem {
    species: string;
    scientific_name?: string | null;
    heard_count: number;
    heard_prev_count: number;
    heard_delta: number;
    heard_percent: number;
    avg_confidence: number;
    last_heard?: string | null;
}

export interface AudioSpeciesLeaderboardResponse {
    span: LeaderboardSpan;
    window_start: string;
    window_end: string;
    species: AudioSpeciesLeaderboardItem[];
}

export async function fetchAudioSpeciesLeaderboard(
    span: LeaderboardSpan = 'week'
): Promise<AudioSpeciesLeaderboardResponse> {
    const response = await apiFetch(`${API_BASE}/audio/species?span=${encodeURIComponent(span)}`);
    return handleResponse<AudioSpeciesLeaderboardResponse>(response);
}

export interface AudioContextDetection extends AudioDetection {
    offset_seconds: number;
}

export interface AudioSourceOption {
    source_name: string;
    mapping_value: string;
    last_seen: string;
    sample_source_id?: string | null;
    seen_count?: number;
}

export async function fetchAudioContext(
    timestamp: string,
    camera?: string,
    windowSeconds: number = 300,
    limit: number = 5
): Promise<AudioContextDetection[]> {
    const params = new URLSearchParams();
    params.set('timestamp', timestamp);
    params.set('window_seconds', String(windowSeconds));
    params.set('limit', String(limit));
    if (camera) {
        params.set('camera', camera);
    }
    const response = await apiFetch(`${API_BASE}/audio/context?${params.toString()}`);
    return handleResponse<AudioContextDetection[]>(response);
}

export async function fetchAudioSources(limit: number = 20): Promise<AudioSourceOption[]> {
    const response = await apiFetch(`${API_BASE}/audio/sources?limit=${limit}`);
    return handleResponse<AudioSourceOption[]>(response);
}
