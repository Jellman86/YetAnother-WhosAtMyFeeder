import { API_BASE, apiFetch, handleResponse } from './core';
import type { paths } from './generated/openapi';

export type BackfillRequest = paths['/api/backfill']['post']['requestBody'];

export type BackfillResult = paths['/api/backfill']['post']['response'];

export async function runBackfill(request: BackfillRequest): Promise<BackfillResult> {
    const response = await apiFetch(`${API_BASE}/backfill`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
    });
    return handleResponse<BackfillResult>(response);
}

export type WeatherBackfillRequest = paths['/api/backfill/weather']['post']['requestBody'];

export type WeatherBackfillResult = paths['/api/backfill/weather']['post']['response'];

export async function runWeatherBackfill(request: WeatherBackfillRequest): Promise<WeatherBackfillResult> {
    const response = await apiFetch(`${API_BASE}/backfill/weather`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
    });
    return handleResponse<WeatherBackfillResult>(response);
}

export type BackfillJobStatus = paths['/api/backfill/async']['post']['response'];

export async function startBackfillJob(request: BackfillRequest): Promise<BackfillJobStatus> {
    const response = await apiFetch(`${API_BASE}/backfill/async`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
    });
    return handleResponse<BackfillJobStatus>(response);
}

export async function startWeatherBackfillJob(request: WeatherBackfillRequest): Promise<BackfillJobStatus> {
    const response = await apiFetch(`${API_BASE}/backfill/weather/async`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
    });
    return handleResponse<BackfillJobStatus>(response);
}

export async function getBackfillStatus(kind?: 'detections' | 'weather'): Promise<BackfillJobStatus | null> {
    const params = kind ? `?kind=${kind}` : '';
    const response = await apiFetch(`${API_BASE}/backfill/status${params}`);
    return handleResponse<BackfillJobStatus | null>(response);
}
