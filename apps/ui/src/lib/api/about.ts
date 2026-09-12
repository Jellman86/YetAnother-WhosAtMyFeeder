import { API_BASE, apiFetch, handleResponse, withAuthParams } from './core';
import type { paths } from './generated/openapi';

export type AboutShowcaseResponse = paths['/api/about/showcase']['get']['response'];
export type AboutShowcaseItem = AboutShowcaseResponse['items'][number];
export type CommunityStatsResponse = paths['/api/about/community']['get']['response'];

/** One recent crop per species from this install, newest first, for the About page's reel. */
export async function fetchAboutShowcase(limit = 12): Promise<AboutShowcaseResponse> {
    const response = await apiFetch(`${API_BASE}/about/showcase?limit=${limit}`);
    return handleResponse<AboutShowcaseResponse>(response);
}

/** The stored photograph at card size, for the About page's reel. */
export function getReelImageUrl(frigateEvent: string): string {
    return withAuthParams(`${API_BASE}/about/showcase/${encodeURIComponent(frigateEvent)}.jpg`);
}

/** How many installs reported to the telemetry service this week; null when unknown or opted out. */
export async function fetchCommunityStats(): Promise<CommunityStatsResponse> {
    const response = await apiFetch(`${API_BASE}/about/community`);
    return handleResponse<CommunityStatsResponse>(response);
}
