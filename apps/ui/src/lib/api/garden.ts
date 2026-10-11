import { API_BASE, apiFetch, handleResponse } from './core';
import type { components } from './generated/openapi';

export type GardenCapture = components['schemas']['GardenCaptureResponse'];
type GardenPage = components['schemas']['GardenCapturePage'];
type GardenStatus = GardenCapture['status'];

export async function fetchGarden(status: GardenStatus, offset: number, signal: AbortSignal): Promise<GardenPage> {
    const response = await apiFetch(`${API_BASE}/garden?status=${status}&offset=${offset}&limit=8`, { signal, timeoutMs: 15000 });
    return handleResponse<GardenPage>(response);
}

export async function reviewGarden(id: string, action: 'confirm' | 'dismiss' | 'restore'): Promise<GardenCapture> {
    const response = await apiFetch(`${API_BASE}/garden/${encodeURIComponent(id)}/${action}`, { method: 'POST', timeoutMs: 15000 });
    return handleResponse<GardenCapture>(response);
}
