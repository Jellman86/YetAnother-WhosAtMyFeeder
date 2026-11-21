import { REFRESH_CADENCE_MS } from './refresh-cadence';

/** Server public cap is1..100 requests/minute per endpoint and source IP. */
export function normalizeGuestRateLimit(value: unknown): number {
    return typeof value === 'number' && Number.isInteger(value) && value >= 1 && value <= 100 ? value : 30;
}

export function guestHistoryRefreshDelayMs(cap: unknown): number {
    // Recent list + Explorer list + open detail all use the events endpoint.
    return Math.max(2000, Math.ceil(180000 / (normalizeGuestRateLimit(cap) * 0.75)));
}

export function guestRecentAudioPollDelayMs(cap: unknown): number {
    return Math.max(5000, Math.ceil(60000 / (normalizeGuestRateLimit(cap) * 0.25)));
}

const TELEMETRY_SAMPLE_MS = REFRESH_CADENCE_MS.sidebarTelemetry;
const TELEMETRY_BACKOFF_CEILING_MS = 5 * 60_000;

/**
 * The wait before the sidebar's decorative CPU graph samples again. Only a session without the
 * pushed status samples it (an owner draws it from the status the live stream pushes): once a
 * minute, and never more than a fifth of a visitor's public per-endpoint budget. Each failed sample
 * in a row doubles the wait up to five minutes, so a rate-limited graph backs off instead of adding to it.
 */
export function telemetrySampleDelayMs(options: { guest: boolean; cap: unknown; failures: number }): number {
    const base = options.guest
        ? Math.max(TELEMETRY_SAMPLE_MS, Math.ceil(60000 / (normalizeGuestRateLimit(options.cap) * 0.2)))
        : TELEMETRY_SAMPLE_MS;
    return Math.min(base * 2 ** Math.max(0, options.failures), Math.max(base, TELEMETRY_BACKOFF_CEILING_MS));
}
