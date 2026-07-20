import { API_BASE, apiFetch, handleResponse } from './core';
import type { paths } from './generated/openapi';
import type { LeaderboardSpan } from './leaderboard';

export type AudioDetection = paths['/api/audio/recent']['get']['response'][number];

export type AudioHistoryDetection = paths['/api/audio/history']['get']['response']['items'][number];

export type AudioHistoryParams = paths['/api/audio/history']['get']['query'];

export type AudioHistoryResponse = paths['/api/audio/history']['get']['response'];

export type AudioSpeciesSummary = paths['/api/audio/summary']['get']['response']['top_species'][number];

export type AudioDailyCount = paths['/api/audio/summary']['get']['response']['daily_counts'][number];

export type AudioHourlyCount = paths['/api/audio/summary']['get']['response']['hourly_counts'][number];

export type AudioSourceSummary = paths['/api/audio/summary']['get']['response']['sources'][number];

export type AudioSummaryResponse = paths['/api/audio/summary']['get']['response'];

export async function fetchRecentAudio(limit: number = 10, signal?: AbortSignal): Promise<AudioDetection[]> {
    const response = await apiFetch(`${API_BASE}/audio/recent?limit=${limit}`, {
        signal,
        timeoutMs: 10_000
    });
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

export async function fetchAudioSummary(
    params: Omit<AudioHistoryParams, 'limit' | 'offset'> = {},
    signal?: AbortSignal
): Promise<AudioSummaryResponse> {
    const query = buildAudioHistoryParams(params);
    const response = await apiFetch(`${API_BASE}/audio/summary?${query.toString()}`, {
        signal,
        timeoutMs: 15_000
    });
    return handleResponse<AudioSummaryResponse>(response);
}

export type AudioSpeciesLeaderboardItem = paths['/api/audio/species']['get']['response']['species'][number];

export type AudioSpeciesLeaderboardResponse = paths['/api/audio/species']['get']['response'];

export async function fetchAudioSpeciesLeaderboard(
    span: LeaderboardSpan = 'week',
    signal?: AbortSignal
): Promise<AudioSpeciesLeaderboardResponse> {
    const response = await apiFetch(`${API_BASE}/audio/species?span=${encodeURIComponent(span)}`, {
        signal,
        timeoutMs: 15_000
    });
    return handleResponse<AudioSpeciesLeaderboardResponse>(response);
}

export type AudioContextDetection = paths['/api/audio/context']['get']['response'][number];

export type AudioSourceOption = paths['/api/audio/sources']['get']['response'][number];

export async function fetchEventAudioContext(
    eventId: string,
    signal?: AbortSignal
): Promise<AudioContextDetection[]> {
    const response = await apiFetch(`${API_BASE}/audio/context/event/${encodeURIComponent(eventId)}`, {
        signal,
        timeoutMs: 10_000
    });
    return handleResponse<AudioContextDetection[]>(response);
}

export async function fetchAudioSources(limit: number = 20): Promise<AudioSourceOption[]> {
    const response = await apiFetch(`${API_BASE}/audio/sources?limit=${limit}`);
    return handleResponse<AudioSourceOption[]>(response);
}
