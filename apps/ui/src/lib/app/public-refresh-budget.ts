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
