import { API_BASE, apiFetch, handleResponse } from './core';

export interface ReverseGeocodeResult {
    state: string | null;
    country: string | null;
    place_guess: string | null;
}

export async function reverseGeocode(lat: number, lon: number): Promise<ReverseGeocodeResult> {
    const params = new URLSearchParams({ lat: String(lat), lon: String(lon) });
    const response = await apiFetch(`${API_BASE}/location/reverse-geocode?${params.toString()}`);
    return handleResponse<ReverseGeocodeResult>(response);
}
