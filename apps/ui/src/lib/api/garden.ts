import { API_BASE, apiFetch, handleResponse } from './core';
import type { components } from './generated/openapi';

export type GardenCapture = components['schemas']['GardenCaptureResponse'];
type GardenPage = components['schemas']['GardenCapturePage'];
type GardenStatus = GardenCapture['status'];
export type GardenIdentificationStatus = components['schemas']['GardenIdentificationStatus'];
export type GardenIdentifyRequest = components['schemas']['GardenIdentifyRequest'];
export type GardenMotionStatus = components['schemas']['GardenMotionStatus'];

export async function fetchGardenMotion(signal: AbortSignal): Promise<GardenMotionStatus> {
    return handleResponse<GardenMotionStatus>(await apiFetch(`${API_BASE}/garden/motion`, { signal }));
}

export async function installGardenMotion(): Promise<GardenMotionStatus> {
    return handleResponse<GardenMotionStatus>(await apiFetch(`${API_BASE}/garden/motion/install`, { method: 'POST', timeoutMs: 240000 }));
}

export async function fetchGarden(status: GardenStatus, offset: number, signal: AbortSignal): Promise<GardenPage> {
    const response = await apiFetch(`${API_BASE}/garden?status=${status}&offset=${offset}&limit=8`, { signal, timeoutMs: 15000 });
    return handleResponse<GardenPage>(response);
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
