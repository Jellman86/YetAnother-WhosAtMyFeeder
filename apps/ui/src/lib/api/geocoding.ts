import { API_BASE, apiFetch, handleResponse } from './core';
import type { paths } from './generated/openapi';

export type ReverseGeocodeResult = paths['/api/location/reverse-geocode']['get']['response'];

export async function reverseGeocode(lat: number, lon: number): Promise<ReverseGeocodeResult> {
    const params = new URLSearchParams({ lat: String(lat), lon: String(lon) });
    const response = await apiFetch(`${API_BASE}/location/reverse-geocode?${params.toString()}`);
    return handleResponse<ReverseGeocodeResult>(response);
}
