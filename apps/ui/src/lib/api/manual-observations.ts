import { API_BASE, apiFetch, handleResponse } from './core';

export interface ManualObservationPrediction {
    label: string;
    score: number;
    model_id?: string | null;
    model_name?: string | null;
    inference_provider?: string | null;
    inference_backend?: string | null;
    input_source?: string | null;
    input_is_cropped?: boolean | null;
    scientific_name?: string | null;
    common_name?: string | null;
    taxa_id?: number | null;
}

export interface ManualObservation {
    id: string;
    status: 'queued' | 'analyzing' | 'ready' | 'failed' | 'saved';
    media_type: 'image' | 'video';
    original_filename: string;
    content_type: string;
    content_sha256: string;
    size_bytes: number;
    progress_current: number;
    progress_total: number;
    progress_percent: number;
    progress_message?: string | null;
    predictions: ManualObservationPrediction[];
    error_code?: string | null;
    error_message?: string | null;
    saved_event_id?: string | null;
    latitude?: number | null;
    longitude?: number | null;
    location_source?: 'image_metadata' | 'manual_pin' | null;
    preview_url: string;
    media_url: string;
    created_at?: string | null;
    updated_at?: string | null;
}

export interface ConfirmManualObservation {
    label: string;
    camera_name: string;
    notes?: string | null;
    observed_at?: string | null;
    latitude?: number | null;
    longitude?: number | null;
    location_source?: 'image_metadata' | 'manual_pin' | 'none' | null;
}

export interface SavedManualObservation {
    status: 'saved';
    event_id: string;
    detection_url: string;
}

export async function uploadManualObservation(file: File): Promise<ManualObservation> {
    const form = new FormData();
    form.append('media', file);
    const response = await apiFetch(`${API_BASE}/manual-observations`, { method: 'POST', body: form });
    return handleResponse<ManualObservation>(response);
}

export async function fetchManualObservation(id: string): Promise<ManualObservation> {
    const response = await apiFetch(`${API_BASE}/manual-observations/${encodeURIComponent(id)}`, { timeoutMs: 10_000 });
    return handleResponse<ManualObservation>(response);
}

export async function retryManualObservation(id: string): Promise<ManualObservation> {
    const response = await apiFetch(`${API_BASE}/manual-observations/${encodeURIComponent(id)}/retry`, { method: 'POST' });
    return handleResponse<ManualObservation>(response);
}

export async function confirmManualObservation(id: string, input: ConfirmManualObservation): Promise<SavedManualObservation> {
    const response = await apiFetch(`${API_BASE}/manual-observations/${encodeURIComponent(id)}/confirm`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input)
    });
    return handleResponse<SavedManualObservation>(response);
}

export async function discardManualObservation(id: string): Promise<void> {
    const response = await apiFetch(`${API_BASE}/manual-observations/${encodeURIComponent(id)}`, { method: 'DELETE' });
    await handleResponse(response);
}
