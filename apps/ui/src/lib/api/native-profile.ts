import { API_BASE, apiFetch, handleResponse } from './core';
import type { components } from './generated/openapi';

export type RevalidationView = components['schemas']['RevalidationView'];
export type RevalidationStatus = components['schemas']['RevalidationStatus'];
const endpoint = `${API_BASE}/classifier/quarantine/revalidation`;

export async function fetchNativeProfileRevalidation(): Promise<RevalidationView> {
    return handleResponse<RevalidationView>(await apiFetch(endpoint, { cache: 'no-store', timeoutMs: 10_000 }));
}

export async function prepareNativeProfileRevalidation(fingerprint: string, attemptId: string): Promise<RevalidationStatus> {
    return handleResponse<RevalidationStatus>(await apiFetch(`${endpoint}/prepare`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile_fingerprint: fingerprint, attempt_id: attemptId }), timeoutMs: 10_000
    }));
}

export async function uploadNativeProfileInputs(attemptId: string, images: File[], video: File): Promise<RevalidationStatus> {
    const body = new FormData();
    for (const image of images) body.append('images', image);
    body.append('video', video);
    return handleResponse<RevalidationStatus>(await apiFetch(`${endpoint}/${encodeURIComponent(attemptId)}/inputs`, {
        method: 'POST', body, timeoutMs: 300_000
    }));
}

export async function cancelNativeProfileRevalidation(attemptId: string): Promise<RevalidationStatus> {
    return handleResponse<RevalidationStatus>(await apiFetch(`${endpoint}/${encodeURIComponent(attemptId)}/cancel`, {
        method: 'POST', timeoutMs: 45_000
    }));
}
