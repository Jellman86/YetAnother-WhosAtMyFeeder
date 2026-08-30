import { API_BASE, apiFetch, fetchWithAbort, handleResponse } from './core';
import type { paths } from './generated/openapi';
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
    onlyHidden?: boolean;
    favoritesOnly?: boolean;
    audioConfirmedOnly?: boolean;
    eventId?: string;
    fields?: 'list' | 'detail' | string;
    requestKey?: string | null;
    signal?: AbortSignal;
}

export async function fetchEvents(options: FetchEventsOptions = {}): Promise<Detection[]> {
    const { limit = 50, offset = 0, startDate, endDate, species, camera, sort, includeHidden, onlyHidden, favoritesOnly, audioConfirmedOnly, eventId, fields, requestKey, signal } = options;
    const params = new URLSearchParams();
    params.set('limit', limit.toString());
    params.set('offset', offset.toString());
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    if (species) params.set('species', species);
    if (camera) params.set('camera', camera);
    if (sort) params.set('sort', sort);
    if (includeHidden) params.set('include_hidden', 'true');
    if (onlyHidden) params.set('only_hidden', 'true');
    if (favoritesOnly) params.set('favorites', 'true');
    if (audioConfirmedOnly) params.set('audio_confirmed_only', 'true');
    if (eventId) params.set('event_id', eventId);
    if (fields) params.set('fields', fields);

    const filterKey = [
        'events',
        species || 'all',
        camera || 'all',
        sort || 'newest',
        onlyHidden ? 'only-hidden' : includeHidden ? 'hidden' : 'visible',
        favoritesOnly ? 'favorites' : 'all',
        audioConfirmedOnly ? 'audio' : 'all',
        eventId || 'all-events',
        fields || 'full',
        startDate || 'none',
        endDate || 'none',
        String(limit),
        String(offset)
    ].join('-');

    return fetchWithAbort<Detection[]>(requestKey === undefined ? filterKey : requestKey, `${API_BASE}/events?${params.toString()}`, {
        timeoutMs: 15_000,
        signal
    });
}

export type EventClassificationStatusResponse =
    paths['/api/events/{event_id}/classification-status']['get']['response'];

export async function fetchEventClassificationStatus(frigateEventId: string): Promise<EventClassificationStatusResponse> {
    const response = await apiFetch(`${API_BASE}/events/${encodeURIComponent(frigateEventId)}/classification-status`);
    return handleResponse<EventClassificationStatusResponse>(response);
}

export type EventFilters = paths['/api/events/filters']['get']['response'];
export type EventFilterSpecies = EventFilters['species'][number];

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
    onlyHidden?: boolean;
    favoritesOnly?: boolean;
    audioConfirmedOnly?: boolean;
    requestKey?: string | null;
}

export type EventsCountResponse = paths['/api/events/count']['get']['response'];

export async function fetchEventsCount(options: EventsCountOptions = {}): Promise<EventsCountResponse> {
    const { startDate, endDate, species, camera, includeHidden, onlyHidden, favoritesOnly, audioConfirmedOnly, requestKey } = options;
    const params = new URLSearchParams();
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    if (species) params.set('species', species);
    if (camera) params.set('camera', camera);
    if (includeHidden) params.set('include_hidden', 'true');
    if (onlyHidden) params.set('only_hidden', 'true');
    if (favoritesOnly) params.set('favorites', 'true');
    if (audioConfirmedOnly) params.set('audio_confirmed_only', 'true');

    const filterKey = [
        'events-count',
        species || 'all',
        camera || 'all',
        onlyHidden ? 'only-hidden' : includeHidden ? 'hidden' : 'visible',
        favoritesOnly ? 'favorites' : 'all',
        audioConfirmedOnly ? 'audio' : 'all',
        startDate || 'none',
        endDate || 'none'
    ].join('-');
    return fetchWithAbort<EventsCountResponse>(
        requestKey === undefined ? filterKey : requestKey,
        `${API_BASE}/events/count?${params.toString()}`,
        { timeoutMs: 15_000 }
    );
}

export async function deleteDetection(frigateEventId: string): Promise<{ status: string }> {
    const response = await apiFetch(`${API_BASE}/events/${encodeURIComponent(frigateEventId)}`, {
        method: 'DELETE'
    });
    return handleResponse<{ status: string }>(response);
}

export type BulkDeleteResult = paths['/api/events/bulk/delete']['post']['response'];

export async function bulkDeleteDetections(eventIds: string[]): Promise<BulkDeleteResult> {
    const response = await apiFetch(`${API_BASE}/events/bulk/delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_ids: eventIds }),
    });
    return handleResponse<BulkDeleteResult>(response);
}

export type HideDetectionResult = paths['/api/events/{event_id}/hide']['post']['response'];

export type FavoriteDetectionResult = paths['/api/events/{event_id}/favorite']['post']['response'];

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

export async function fetchHiddenCount(): Promise<paths['/api/events/hidden-count']['get']['response']> {
    const response = await apiFetch(`${API_BASE}/events/hidden-count`);
    return handleResponse<paths['/api/events/hidden-count']['get']['response']>(response);
}
