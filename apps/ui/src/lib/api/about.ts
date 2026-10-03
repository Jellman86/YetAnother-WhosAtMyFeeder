import { API_BASE, apiFetch, handleResponse, withAuthParams } from './core';
import type { paths } from './generated/openapi';

export type CommunityStatsResponse = paths['/api/about/community']['get']['response'];
export type FeederPortrait = paths['/api/about/portrait']['get']['response'];

/** This feeder in a few measured facts and its latest visit, counted by the viewer's calendar days. */
export async function fetchFeederPortrait(signal?: AbortSignal): Promise<FeederPortrait> {
    const offset = -new Date().getTimezoneOffset();
    const response = await apiFetch(`${API_BASE}/about/portrait?utc_offset_minutes=${offset}`, { signal });
    return handleResponse<FeederPortrait>(response);
}

/** The stored photograph at card size. */
export function getReelImageUrl(frigateEvent: string): string {
    return withAuthParams(`${API_BASE}/about/showcase/${encodeURIComponent(frigateEvent)}.jpg`);
}

/** A few silent seconds of the visit, framed on the bird; null while it is not made yet. */
export async function fetchVisitFilm(frigateEvent: string, signal?: AbortSignal): Promise<Blob | null> {
    const response = await apiFetch(`${API_BASE}/about/showcase/${encodeURIComponent(frigateEvent)}.webm`, {
        signal,
        timeoutMs: 30_000
    });
    if (response.status === 404) return null;
    if (!response.ok) throw new Error(`Film request failed: ${response.status}`);
    return response.blob();
}

/** How many installs reported to the telemetry service this week; null when unknown or opted out. */
export async function fetchCommunityStats(): Promise<CommunityStatsResponse> {
    const response = await apiFetch(`${API_BASE}/about/community`);
    return handleResponse<CommunityStatsResponse>(response);
}
