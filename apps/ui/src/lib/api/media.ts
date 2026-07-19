import { API_BASE, apiFetch, getHeaders, handleResponse, withAuthParams } from './core';
import type { paths } from './generated/openapi';

export function getSnapshotUrl(frigateEvent: string): string {
    return withAuthParams(`${API_BASE}/frigate/${frigateEvent}/snapshot.jpg`);
}

export function getOriginalFrigateSnapshotUrl(frigateEvent: string): string {
    return withAuthParams(`${API_BASE}/frigate/${frigateEvent}/snapshot/original.jpg`);
}

export function getThumbnailUrl(frigateEvent: string): string {
    return withAuthParams(`${API_BASE}/frigate/${frigateEvent}/thumbnail.jpg`);
}

export function getClipUrl(frigateEvent: string): string {
    return withAuthParams(`${API_BASE}/frigate/${frigateEvent}/clip.mp4`);
}

export function getRecordingClipUrl(frigateEvent: string): string {
    return withAuthParams(`${API_BASE}/frigate/${frigateEvent}/recording-clip.mp4`);
}

export const RECORDING_CLIP_READY_HEADER = 'X-YAWAMF-Recording-Clip-Ready';

export type RecordingClipFetchResponse =
    paths['/api/frigate/{event_id}/recording-clip/fetch']['post']['response'];

export interface RecordingClipAvailabilityResponse {
    available: boolean;
    fetched: boolean;
}

export type SnapshotStatusResponse = paths['/api/frigate/{event_id}/snapshot/status']['get']['response'];

export type SnapshotGenerateResponse = paths['/api/frigate/{event_id}/snapshot/hq-bird-crop']['post']['response'];

export type SnapshotCandidate =
    paths['/api/frigate/{event_id}/snapshot/candidates']['get']['response']['candidates'][number];

export type SnapshotCandidateListResponse = paths['/api/frigate/{event_id}/snapshot/candidates']['get']['response'];

export type SnapshotApplyResponse = paths['/api/frigate/{event_id}/snapshot/apply']['post']['response'];

export function getClipPreviewTrackUrl(frigateEvent: string): string {
    return withAuthParams(`${API_BASE}/frigate/${frigateEvent}/clip-thumbnails.vtt`);
}

export async function fetchLatestCameraSnapshot(camera: string, signal?: AbortSignal): Promise<Blob> {
    const response = await apiFetch(`${API_BASE}/frigate/camera/${encodeURIComponent(camera)}/latest.jpg`, {
        cache: 'no-store',
        signal,
        timeoutMs: 10_000
    });
    if (!response.ok) {
        await handleResponse<never>(response);
        throw new Error(`Failed to load camera snapshot (${response.status})`);
    }
    return response.blob();
}

export type CameraStatusResponse = paths['/api/frigate/cameras/status']['get']['response'];

export async function fetchCameraStatuses(signal?: AbortSignal): Promise<CameraStatusResponse> {
    const response = await apiFetch(`${API_BASE}/frigate/cameras/status`, {
        cache: 'no-store',
        signal,
        timeoutMs: 10_000
    });
    return handleResponse<CameraStatusResponse>(response);
}

export type VideoShareCreateResponse = paths['/api/video-share']['post']['response'];

export type VideoShareInfoResponse = paths['/api/video-share/{event_id}']['get']['response'];

export type VideoShareLinkItem = paths['/api/video-share/{event_id}/links/{link_id}']['patch']['response'];

export type VideoShareLinkListResponse = paths['/api/video-share/{event_id}/links']['get']['response'];

export async function createVideoShareLink(
    eventId: string,
    options: { expiresInMinutes?: number; watermarkLabel?: string | null } = {}
): Promise<VideoShareCreateResponse> {
    const response = await apiFetch(`${API_BASE}/video-share`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            event_id: eventId,
            expires_in_minutes: options.expiresInMinutes ?? 24 * 60,
            watermark_label: options.watermarkLabel ?? null,
        }),
    });
    return handleResponse<VideoShareCreateResponse>(response);
}

export async function fetchVideoShareInfo(eventId: string, shareToken: string): Promise<VideoShareInfoResponse> {
    const response = await fetch(`${API_BASE}/video-share/${encodeURIComponent(eventId)}?share=${encodeURIComponent(shareToken)}`, {
        headers: getHeaders(),
    });
    return handleResponse<VideoShareInfoResponse>(response);
}

export async function listVideoShareLinks(eventId: string): Promise<VideoShareLinkListResponse> {
    const response = await apiFetch(`${API_BASE}/video-share/${encodeURIComponent(eventId)}/links`);
    return handleResponse<VideoShareLinkListResponse>(response);
}

export async function updateVideoShareLink(
    eventId: string,
    linkId: number,
    updates: { expiresInMinutes?: number; watermarkLabel?: string | null }
): Promise<VideoShareLinkItem> {
    const payload: Record<string, unknown> = {};
    if (typeof updates.expiresInMinutes === 'number') {
        payload.expires_in_minutes = updates.expiresInMinutes;
    }
    if ('watermarkLabel' in updates) {
        payload.watermark_label = updates.watermarkLabel ?? null;
    }

    const response = await apiFetch(`${API_BASE}/video-share/${encodeURIComponent(eventId)}/links/${linkId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    return handleResponse<VideoShareLinkItem>(response);
}

export async function revokeVideoShareLink(
    eventId: string,
    linkId: number
): Promise<paths['/api/video-share/{event_id}/links/{link_id}/revoke']['post']['response']> {
    const response = await apiFetch(`${API_BASE}/video-share/${encodeURIComponent(eventId)}/links/${linkId}/revoke`, {
        method: 'POST',
    });
    return handleResponse<paths['/api/video-share/{event_id}/links/{link_id}/revoke']['post']['response']>(response);
}

export async function checkClipAvailable(frigateEvent: string): Promise<boolean> {
    try {
        const response = await apiFetch(`${API_BASE}/frigate/${frigateEvent}/clip.mp4`, {
            method: 'HEAD'
        });
        return response.ok;
    } catch {
        return false;
    }
}

export async function checkRecordingClipAvailable(frigateEvent: string): Promise<RecordingClipAvailabilityResponse> {
    try {
        const response = await apiFetch(`${API_BASE}/frigate/${encodeURIComponent(frigateEvent)}/recording-clip.mp4`, {
            method: 'HEAD',
            timeoutMs: 10_000
        });
        return {
            available: response.ok,
            fetched: response.headers.get(RECORDING_CLIP_READY_HEADER)?.toLowerCase() === 'cached'
        };
    } catch {
        return { available: false, fetched: false };
    }
}

export async function fetchRecordingClip(frigateEvent: string): Promise<RecordingClipFetchResponse> {
    const response = await apiFetch(`${API_BASE}/frigate/${encodeURIComponent(frigateEvent)}/recording-clip/fetch`, {
        method: 'POST',
        timeoutMs: 60_000
    });
    return handleResponse<RecordingClipFetchResponse>(response);
}

export async function fetchSnapshotStatus(frigateEvent: string): Promise<SnapshotStatusResponse> {
    const response = await apiFetch(`${API_BASE}/frigate/${frigateEvent}/snapshot/status`);
    return handleResponse<SnapshotStatusResponse>(response);
}

export async function generateHighQualityBirdCropSnapshot(frigateEvent: string): Promise<SnapshotGenerateResponse> {
    const response = await apiFetch(`${API_BASE}/frigate/${frigateEvent}/snapshot/hq-bird-crop`, {
        method: 'POST',
    });
    return handleResponse<SnapshotGenerateResponse>(response);
}

export async function fetchSnapshotCandidates(frigateEvent: string): Promise<SnapshotCandidateListResponse> {
    const response = await apiFetch(`${API_BASE}/frigate/${frigateEvent}/snapshot/candidates`);
    const body = await handleResponse<SnapshotCandidateListResponse>(response);
    return {
        ...body,
        candidates: (body.candidates || []).map((candidate) => ({
            ...candidate,
            thumbnail_url: candidate.thumbnail_url ? withAuthParams(candidate.thumbnail_url) : candidate.thumbnail_url
        }))
    };
}

export async function applySnapshotCandidate(
    frigateEvent: string,
    input: {
        mode: paths['/api/frigate/{event_id}/snapshot/apply']['post']['requestBody']['mode'];
        candidate_id?: string | null;
    }
): Promise<SnapshotApplyResponse> {
    const response = await apiFetch(`${API_BASE}/frigate/${frigateEvent}/snapshot/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
    });
    return handleResponse<SnapshotApplyResponse>(response);
}
