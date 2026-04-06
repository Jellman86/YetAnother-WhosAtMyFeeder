import { API_BASE, apiFetch, fetchWithAbort, handleResponse } from './core';
import type { Detection } from './types';

export interface FetchEventsOptions {
    limit?: number;
    offset?: number;
    startDate?: string;
    endDate?: string;
    species?: string;
    camera?: string;
    sort?: 'newest' | 'oldest' | 'confidence';
    includeHidden?: boolean;
    favoritesOnly?: boolean;
    audioConfirmedOnly?: boolean;
}

export async function fetchEvents(options: FetchEventsOptions = {}): Promise<Detection[]> {
    const { limit = 50, offset = 0, startDate, endDate, species, camera, sort, includeHidden, favoritesOnly, audioConfirmedOnly } = options;
    const params = new URLSearchParams();
    params.set('limit', limit.toString());
    params.set('offset', offset.toString());
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    if (species) params.set('species', species);
    if (camera) params.set('camera', camera);
    if (sort) params.set('sort', sort);
    if (includeHidden) params.set('include_hidden', 'true');
    if (favoritesOnly) params.set('favorites', 'true');
    if (audioConfirmedOnly) params.set('audio_confirmed_only', 'true');

    const filterKey = [
        'events',
        species || 'all',
        camera || 'all',
        sort || 'newest',
        includeHidden ? 'hidden' : 'visible',
        favoritesOnly ? 'favorites' : 'all',
        audioConfirmedOnly ? 'audio' : 'all',
        startDate || 'none',
        endDate || 'none',
        String(limit),
        String(offset)
    ].join('-');

    return fetchWithAbort<Detection[]>(filterKey, `${API_BASE}/events?${params.toString()}`);
}

export interface EventClassificationStatusResponse {
    event_id: string;
    video_classification_status: string | null;
    video_classification_error: string | null;
    video_classification_timestamp: string | null;
    video_classification_provider?: string | null;
    video_classification_backend?: string | null;
    video_classification_model_id?: string | null;
    video_classification_model_name?: string | null;
}

export async function fetchEventClassificationStatus(frigateEventId: string): Promise<EventClassificationStatusResponse> {
    const response = await apiFetch(`${API_BASE}/events/${encodeURIComponent(frigateEventId)}/classification-status`);
    return handleResponse<EventClassificationStatusResponse>(response);
}

export interface EventFilters {
    species: EventFilterSpecies[];
    cameras: string[];
}

export interface EventFilterSpecies {
    value: string;
    display_name: string;
    scientific_name?: string | null;
    common_name?: string | null;
    taxa_id?: number | null;
}

export interface FetchEventFiltersOptions {
    forceRefresh?: boolean;
}

export async function fetchEventFilters(options: FetchEventFiltersOptions = {}): Promise<EventFilters> {
    const params = new URLSearchParams();
    if (options.forceRefresh) params.set('force_refresh', 'true');
    const query = params.toString();
    const response = await apiFetch(`${API_BASE}/events/filters${query ? `?${query}` : ''}`);
    return handleResponse<EventFilters>(response);
}

export interface EventsCountOptions {
    startDate?: string;
    endDate?: string;
    species?: string;
    camera?: string;
    includeHidden?: boolean;
    favoritesOnly?: boolean;
    audioConfirmedOnly?: boolean;
}

export interface EventsCountResponse {
    count: number;
    filtered: boolean;
}

export async function fetchEventsCount(options: EventsCountOptions = {}): Promise<EventsCountResponse> {
    const { startDate, endDate, species, camera, includeHidden, favoritesOnly, audioConfirmedOnly } = options;
    const params = new URLSearchParams();
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    if (species) params.set('species', species);
    if (camera) params.set('camera', camera);
    if (includeHidden) params.set('include_hidden', 'true');
    if (favoritesOnly) params.set('favorites', 'true');
    if (audioConfirmedOnly) params.set('audio_confirmed_only', 'true');

    const response = await apiFetch(`${API_BASE}/events/count?${params.toString()}`);
    return handleResponse<EventsCountResponse>(response);
}

export async function deleteDetection(frigateEventId: string): Promise<{ status: string }> {
    const response = await apiFetch(`${API_BASE}/events/${encodeURIComponent(frigateEventId)}`, {
        method: 'DELETE'
    });
    return handleResponse<{ status: string }>(response);
}

export interface BulkDeleteResult {
    deleted_count: number;
    missing_count: number;
    deleted_event_ids: string[];
    missing_event_ids: string[];
}

export async function bulkDeleteDetections(eventIds: string[]): Promise<BulkDeleteResult> {
    const response = await apiFetch(`${API_BASE}/events/bulk/delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_ids: eventIds }),
    });
    return handleResponse<BulkDeleteResult>(response);
}

export interface HideDetectionResult {
    status: string;
    event_id: string;
    is_hidden: boolean;
}

export interface FavoriteDetectionResult {
    status: string;
    event_id: string;
    is_favorite: boolean;
}

export async function hideDetection(frigateEventId: string): Promise<HideDetectionResult> {
    const response = await apiFetch(`${API_BASE}/events/${encodeURIComponent(frigateEventId)}/hide`, {
        method: 'POST'
    });
    return handleResponse<HideDetectionResult>(response);
}

export async function favoriteDetection(frigateEventId: string): Promise<FavoriteDetectionResult> {
    const response = await apiFetch(`${API_BASE}/events/${encodeURIComponent(frigateEventId)}/favorite`, {
        method: 'POST'
    });
    return handleResponse<FavoriteDetectionResult>(response);
}

export async function unfavoriteDetection(frigateEventId: string): Promise<FavoriteDetectionResult> {
    const response = await apiFetch(`${API_BASE}/events/${encodeURIComponent(frigateEventId)}/favorite`, {
        method: 'DELETE'
    });
    return handleResponse<FavoriteDetectionResult>(response);
}

export async function fetchHiddenCount(): Promise<{ hidden_count: number }> {
    const response = await apiFetch(`${API_BASE}/events/hidden-count`);
    return handleResponse<{ hidden_count: number }>(response);
}
