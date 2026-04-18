import { API_BASE, apiFetch, getHeaders, handleResponse, withAuthParams } from './core';

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

export interface RecordingClipFetchResponse {
    event_id: string;
    status: 'ready';
    clip_variant: 'recording';
    cached: boolean;
}

export interface RecordingClipAvailabilityResponse {
    available: boolean;
    fetched: boolean;
}

export interface SnapshotStatusResponse {
    event_id: string;
    cached: boolean;
    source: string | null;
    high_quality_event_snapshots_enabled: boolean;
    high_quality_bird_crop_enabled: boolean;
    already_hq_bird_crop: boolean;
    can_generate_hq_bird_crop: boolean;
}

export interface SnapshotGenerateResponse extends SnapshotStatusResponse {
    status: 'already_hq_bird_crop' | 'generated_hq_bird_crop' | 'generated_hq_snapshot';
    result: string;
}

export interface SnapshotCandidate {
    candidate_id: string;
    frame_index: number;
    frame_offset_seconds?: number | null;
    source_mode: string;
    clip_variant: string;
    crop_box?: number[] | null;
    crop_confidence?: number | null;
    classifier_label?: string | null;
    classifier_score?: number | null;
    ranking_score: number;
    selected: boolean;
    snapshot_source?: string | null;
    thumbnail_url?: string | null;
}

export interface SnapshotCandidateListResponse {
    event_id: string;
    current_source?: string | null;
    current_candidate_id?: string | null;
    candidates: SnapshotCandidate[];
}

export interface SnapshotApplyResponse extends SnapshotStatusResponse {
    status: 'applied';
    applied_mode: string;
    applied_candidate_id?: string | null;
}

export function getClipPreviewTrackUrl(frigateEvent: string): string {
    return withAuthParams(`${API_BASE}/frigate/${frigateEvent}/clip-thumbnails.vtt`);
}

export interface VideoShareCreateResponse {
    link_id: number;
    event_id: string;
    token: string;
    share_url: string;
    expires_at: string;
    expires_in_minutes: number;
    watermark_label?: string | null;
}

export interface VideoShareInfoResponse {
    event_id: string;
    expires_at: string;
    watermark_label?: string | null;
}

export interface VideoShareLinkItem {
    id: number;
    event_id: string;
    created_by?: string | null;
    watermark_label?: string | null;
    created_at: string;
    expires_at: string;
    is_active: boolean;
    remaining_seconds: number;
}

export interface VideoShareLinkListResponse {
    event_id: string;
    links: VideoShareLinkItem[];
}

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

export async function revokeVideoShareLink(eventId: string, linkId: number): Promise<{ status: string; event_id: string; link_id: number }> {
    const response = await apiFetch(`${API_BASE}/video-share/${encodeURIComponent(eventId)}/links/${linkId}/revoke`, {
        method: 'POST',
    });
    return handleResponse<{ status: string; event_id: string; link_id: number }>(response);
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
        const response = await apiFetch(`${API_BASE}/frigate/${frigateEvent}/recording-clip.mp4`, {
            method: 'HEAD'
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
    const response = await apiFetch(`${API_BASE}/frigate/${frigateEvent}/recording-clip/fetch`, {
        method: 'POST',
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
        mode: 'candidate' | 'auto_best' | 'full_frame' | 'frigate_hint_crop' | 'model_crop' | 'revert_original';
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
