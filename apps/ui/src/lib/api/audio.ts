import { API_BASE, apiFetch, apiFetchJson, handleResponse, type Guarded } from './core';
import type { components, paths } from './generated/openapi';
import type { LeaderboardSpan } from './leaderboard';

export type AudioDetection = paths['/api/audio/recent']['get']['response'][number];

export type AudioHistoryDetection = paths['/api/audio/history']['get']['response']['items'][number];

export type AudioHistoryParams = paths['/api/audio/history']['get']['query'];

export type AudioHistoryResponse = paths['/api/audio/history']['get']['response'];

export type AudioSummaryResponse = paths['/api/audio/summary']['get']['response'];

export type AudioActivityHeatmapResponse = paths['/api/audio/activity-heatmap']['get']['response'];

export type AudioActivityHeatmapParams = NonNullable<paths['/api/audio/activity-heatmap']['get']['query']>;

export async function fetchRecentAudio(limit: number = 10, signal?: AbortSignal): Promise<AudioDetection[]> {
    const response = await apiFetch(`${API_BASE}/audio/recent?limit=${limit}`, {
        signal,
        timeoutMs: 10_000
    });
    return handleResponse<AudioDetection[]>(response);
}

function buildAudioHistoryParams(params: AudioHistoryParams | AudioActivityHeatmapParams = {}): URLSearchParams {
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

/** Calls heard by weekday and hour, over the same window and filters as the summary, or one species exactly. */
export async function fetchAudioActivityHeatmap(
    params: AudioActivityHeatmapParams = {},
    signal?: AbortSignal
): Promise<AudioActivityHeatmapResponse> {
    const query = buildAudioHistoryParams(params);
    const response = await apiFetch(`${API_BASE}/audio/activity-heatmap?${query.toString()}`, {
        signal,
        timeoutMs: 15_000
    });
    return handleResponse<AudioActivityHeatmapResponse>(response);
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

export interface AudioContextResponse {
    detections: AudioContextDetection[];
    suppressed_by_mapping: number;
}

const AUDIO_SUPPRESSED_BY_MAPPING_HEADER = 'X-YAWAMF-Audio-Suppressed-By-Mapping';

export type AudioSourceOption = paths['/api/audio/sources']['get']['response'][number];

export async function fetchEventAudioContext(
    eventId: string,
    signal?: AbortSignal
): Promise<AudioContextResponse> {
    const response = await apiFetch(`${API_BASE}/audio/context/event/${encodeURIComponent(eventId)}`, {
        signal,
        timeoutMs: 10_000
    });
    const detections = await handleResponse<AudioContextDetection[]>(response);
    const headerValue = response.headers.get(AUDIO_SUPPRESSED_BY_MAPPING_HEADER);
    const parsedSuppressedCount = headerValue === null ? 0 : Number.parseInt(headerValue, 10);
    const suppressedByMapping = Number.isFinite(parsedSuppressedCount) && parsedSuppressedCount > 0
        ? parsedSuppressedCount
        : 0;
    return { detections, suppressed_by_mapping: suppressedByMapping };
}

/** Timed out after 15 s, body included; `signal` cancels it when the tab that asked closes. */
export function fetchAudioSources(limit: number = 20, signal?: AbortSignal): Guarded<AudioSourceOption[]> {
    return apiFetchJson<AudioSourceOption[]>(`${API_BASE}/audio/sources?limit=${limit}`, { timeoutMs: 15_000, signal });
}

export async function setAudioHidden(id: number, hidden: boolean): Promise<paths['/api/audio/history/{detection_id}']['patch']['response']> {
    const response = await apiFetch(`${API_BASE}/audio/history/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ hidden })
    });
    return handleResponse<paths['/api/audio/history/{detection_id}']['patch']['response']>(response);
}

export type HeardGroup = components['schemas']['HeardGroupResponse'];

export type HeardGroupsResponse = components['schemas']['HeardGroupsResponse'];

export type HeardVisitCalls = components['schemas']['HeardVisitCallsResponse'];

export async function fetchHeardGroups(
    startDate: string,
    endDate: string,
    signal?: AbortSignal
): Promise<HeardGroupsResponse> {
    const query = new URLSearchParams({ start_date: startDate, end_date: endDate });
    const response = await apiFetch(`${API_BASE}/audio/heard-groups?${query.toString()}`, {
        signal,
        timeoutMs: 15_000
    });
    return handleResponse<HeardGroupsResponse>(response);
}
