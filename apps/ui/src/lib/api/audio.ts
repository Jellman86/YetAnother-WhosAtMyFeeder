import { API_BASE, apiFetch, handleResponse } from './core';

export interface AudioDetection {
    timestamp: string;
    species: string;
    confidence: number;
    sensor_id: string | null;
}

export async function fetchRecentAudio(limit: number = 10): Promise<AudioDetection[]> {
    const response = await apiFetch(`${API_BASE}/audio/recent?limit=${limit}`);
    return handleResponse<AudioDetection[]>(response);
}

export interface AudioContextDetection extends AudioDetection {
    offset_seconds: number;
}

export interface AudioSourceOption {
    source_name: string;
    last_seen: string;
    sample_source_id?: string | null;
    seen_count?: number;
}

export async function fetchAudioContext(
    timestamp: string,
    camera?: string,
    windowSeconds: number = 300,
    limit: number = 5
): Promise<AudioContextDetection[]> {
    const params = new URLSearchParams();
    params.set('timestamp', timestamp);
    params.set('window_seconds', String(windowSeconds));
    params.set('limit', String(limit));
    if (camera) {
        params.set('camera', camera);
    }
    const response = await apiFetch(`${API_BASE}/audio/context?${params.toString()}`);
    return handleResponse<AudioContextDetection[]>(response);
}

export async function fetchAudioSources(limit: number = 20): Promise<AudioSourceOption[]> {
    const response = await apiFetch(`${API_BASE}/audio/sources?limit=${limit}`);
    return handleResponse<AudioSourceOption[]>(response);
}
