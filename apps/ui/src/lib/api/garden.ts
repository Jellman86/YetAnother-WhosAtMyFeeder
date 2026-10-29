import { API_BASE, apiFetch, handleResponse } from './core';
import type { components } from './generated/openapi';

export type GardenCapture = components['schemas']['GardenCaptureResponse'];
type GardenPage = components['schemas']['GardenCapturePage'];
export type GardenIdentificationStatus = components['schemas']['GardenIdentificationStatus'];
export type GardenIdentifyRequest = components['schemas']['GardenIdentifyRequest'];
export type GardenMotionStatus = components['schemas']['GardenMotionStatus'];

export async function fetchGardenMotion(signal: AbortSignal): Promise<GardenMotionStatus> {
    return handleResponse<GardenMotionStatus>(await apiFetch(`${API_BASE}/garden/motion`, { signal }));
}

export async function installGardenMotion(): Promise<GardenMotionStatus> {
    return handleResponse<GardenMotionStatus>(await apiFetch(`${API_BASE}/garden/motion/install`, { method: 'POST', timeoutMs: 240000 }));
}

export interface GardenTimelineQuery {
    start?: string | null;
    end?: string;
    camera?: string;
    order: 'newest' | 'oldest';
    status?: 'reviewable' | 'pending' | 'confirmed' | 'dismissed';
    limit: number;
    offset?: number;
}

/** Confirmed animals and captures awaiting review, by time, for the Explorer. */
export async function fetchGardenTimeline(query: GardenTimelineQuery, signal?: AbortSignal): Promise<GardenPage> {
    const params = new URLSearchParams({ order: query.order, limit: String(query.limit), offset: String(query.offset ?? 0) });
    if (query.start) params.set('start', query.start);
    if (query.end) params.set('end', query.end);
    if (query.camera) params.set('camera', query.camera);
    if (query.status && query.status !== 'reviewable') params.set('status', query.status);
    return handleResponse<GardenPage>(await apiFetch(`${API_BASE}/garden/timeline?${params}`, { signal, timeoutMs: 15000 }));
}

export async function reviewGardenBatch(ids: string[], action: 'dismiss' | 'restore'): Promise<components['schemas']['GardenBatchReviewResponse']> {
    return handleResponse<components['schemas']['GardenBatchReviewResponse']>(await apiFetch(`${API_BASE}/garden/review-batch`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids, action }), timeoutMs: 15000
    }));
}

export async function dismissGardenCaptures(captures: components['schemas']['GardenDismissTarget'][]): Promise<components['schemas']['GardenBatchReviewResponse']> {
    return handleResponse<components['schemas']['GardenBatchReviewResponse']>(await apiFetch(`${API_BASE}/garden/dismiss-captures`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ captures }), timeoutMs: 15000
    }));
}

export async function reviewGarden(id: string, action: 'confirm' | 'dismiss' | 'restore'): Promise<GardenCapture> {
    const response = await apiFetch(`${API_BASE}/garden/${encodeURIComponent(id)}/${action}`, { method: 'POST', timeoutMs: 15000 });
    return handleResponse<GardenCapture>(response);
}

export async function fetchGardenIdentification(signal: AbortSignal): Promise<GardenIdentificationStatus> {
    return handleResponse<GardenIdentificationStatus>(await apiFetch(`${API_BASE}/garden/identification`, { signal }));
}

export async function installGardenModel(variant: GardenIdentifyRequest['variant']): Promise<GardenIdentificationStatus> {
    return handleResponse<GardenIdentificationStatus>(await apiFetch(`${API_BASE}/garden/models/${variant}/install`, { method: 'POST', timeoutMs: 240000 }));
}

export async function identifyGarden(id: string, request: GardenIdentifyRequest): Promise<GardenCapture> {
    return handleResponse<GardenCapture>(await apiFetch(`${API_BASE}/garden/${encodeURIComponent(id)}/identify`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request), timeoutMs: 160000 }));
}

export async function reviewGardenIdentification(id: string, action: 'accept' | 'dismiss'): Promise<GardenCapture> {
    return handleResponse<GardenCapture>(await apiFetch(`${API_BASE}/garden/${encodeURIComponent(id)}/identification/${action}`, { method: 'POST' }));
}

export type GardenPhotoCheck = components['schemas']['GardenPhotoCheck'];
export type GardenPhotoCheckRequest = components['schemas']['GardenPhotoCheckRequest'];

export async function checkGardenPhoto(id: string, request: GardenPhotoCheckRequest, signal: AbortSignal): Promise<GardenPhotoCheck> {
    return handleResponse<GardenPhotoCheck>(await apiFetch(`${API_BASE}/garden/${encodeURIComponent(id)}/check-photo`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request), signal, timeoutMs: 160000
    }));
}


export type GardenServerVisit = components['schemas']['GardenVisitResponse'];
export type GardenVisitPage = components['schemas']['GardenVisitPage'];
export interface GardenVisitQuery extends GardenTimelineQuery {
    pageStart?: string;
    pageEnd?: string;
}

function gardenScope(query: Pick<GardenTimelineQuery, 'start' | 'end' | 'camera' | 'status'>): URLSearchParams {
    const params = new URLSearchParams();
    if (query.start) params.set('start', query.start);
    if (query.end) params.set('end', query.end);
    if (query.camera) params.set('camera', query.camera);
    if (query.status && query.status !== 'reviewable') params.set('status', query.status);
    return params;
}

export async function fetchGardenVisits(query: GardenVisitQuery, signal?: AbortSignal): Promise<GardenVisitPage> {
    const params = gardenScope(query);
    params.set('order', query.order);
    params.set('limit', String(query.limit));
    params.set('offset', String(query.offset ?? 0));
    if (query.pageStart) params.set('page_start', query.pageStart);
    if (query.pageEnd) params.set('page_end', query.pageEnd);
    return handleResponse<GardenVisitPage>(await apiFetch(`${API_BASE}/garden/visits?${params}`, { signal, timeoutMs: 15000 }));
}

export async function fetchGardenVisitCaptures(
    id: string,
    query: Pick<GardenTimelineQuery, 'start' | 'end' | 'camera' | 'status'>,
    offset: number,
    options: { limit?: number; signal?: AbortSignal } = {}
): Promise<GardenPage> {
    const params = gardenScope(query);
    params.set('limit', String(options.limit ?? 128));
    params.set('offset', String(offset));
    return handleResponse<GardenPage>(await apiFetch(`${API_BASE}/garden/visits/${encodeURIComponent(id)}/captures?${params}`, { signal: options.signal, timeoutMs: 15000 }));
}


export type GardenNotificationStatus = components['schemas']['GardenNotificationStatus'];
export type GardenNotificationChannel = GardenNotificationStatus['channels'][number];

export async function fetchGardenNotifications(signal?: AbortSignal): Promise<GardenNotificationStatus> {
    return handleResponse<GardenNotificationStatus>(await apiFetch(`${API_BASE}/garden/notifications`, { signal }));
}


export type GardenSpecies = components['schemas']['GardenSpecies'];

export async function searchGardenSpecies(query: string, signal: AbortSignal): Promise<GardenSpecies[]> {
    return handleResponse<GardenSpecies[]>(await apiFetch(`${API_BASE}/garden/species?${new URLSearchParams({ q: query })}`, { signal, timeoutMs: 15000 }));
}

export async function renameGardenSpecies(id: string, speciesId: number, token: string): Promise<GardenCapture> {
    const request: components['schemas']['GardenRenameRequest'] = { species_id: speciesId, review_token: token };
    return handleResponse<GardenCapture>(await apiFetch(`${API_BASE}/garden/${encodeURIComponent(id)}/species`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request), timeoutMs: 15000
    }));
}

export async function clearGardenSpecies(id: string, token: string): Promise<GardenCapture> {
    return handleResponse<GardenCapture>(await apiFetch(`${API_BASE}/garden/${encodeURIComponent(id)}/species?${new URLSearchParams({ review_token: token })}`, { method: 'DELETE', timeoutMs: 15000 }));
}

/** Re-read a selected capture when a correction moved it out of its former visit. */
export async function fetchGardenCaptureAtTime(capture: Pick<GardenCapture, 'id' | 'camera' | 'observed_at'>, status: GardenTimelineQuery['status']): Promise<GardenCapture | null> {
    const page = await fetchGardenTimeline({ start: capture.observed_at, end: capture.observed_at, camera: capture.camera, status, order: 'newest', limit: 200 });
    return page.items?.find(item => item.id === capture.id) ?? null;
}
