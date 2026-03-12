import { API_BASE, apiFetch, handleResponse } from './core';

export interface BackfillRequest {
    date_range: 'day' | 'week' | 'month' | 'custom';
    start_date?: string;
    end_date?: string;
    cameras?: string[];
}

export interface BackfillResult {
    status: string;
    processed: number;
    new_detections: number;
    skipped: number;
    errors: number;
    skipped_reasons?: Record<string, number>;
    error_reasons?: Record<string, number>;
    message: string;
}

export async function runBackfill(request: BackfillRequest): Promise<BackfillResult> {
    const response = await apiFetch(`${API_BASE}/backfill`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
    });
    return handleResponse<BackfillResult>(response);
}

export interface WeatherBackfillRequest {
    date_range: 'day' | 'week' | 'month' | 'custom';
    start_date?: string;
    end_date?: string;
    only_missing?: boolean;
}

export interface WeatherBackfillResult {
    status: string;
    processed: number;
    updated: number;
    skipped: number;
    errors: number;
    error_reasons?: Record<string, number>;
    message: string;
}

export async function runWeatherBackfill(request: WeatherBackfillRequest): Promise<WeatherBackfillResult> {
    const response = await apiFetch(`${API_BASE}/backfill/weather`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
    });
    return handleResponse<WeatherBackfillResult>(response);
}

export interface BackfillJobStatus {
    id: string;
    kind: string;
    status: string;
    processed: number;
    total: number;
    new_detections?: number;
    updated?: number;
    skipped: number;
    skipped_reasons?: Record<string, number>;
    errors: number;
    error_reasons?: Record<string, number>;
    message?: string;
    started_at?: string | null;
    finished_at?: string | null;
}

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
