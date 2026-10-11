import { expect, it } from 'vitest';
import { guestHistoryRefreshDelayMs, guestRecentAudioPollDelayMs, normalizeGuestRateLimit } from './public-refresh-budget';

it.each([[30, 8000], [100, 2400], [1, 240000]])('budgets three events-route requests within75%% of cap %s', (cap, delay) => {
    expect(guestHistoryRefreshDelayMs(cap)).toBe(delay);
    expect(3 * 60000 / guestHistoryRefreshDelayMs(cap)).toBeLessThanOrEqual(cap * 0.75);
});

it.each([undefined, null, NaN, Infinity, 0, -1, 101, 30.5, '30'])('uses the server default for an invalid cap %s', (cap) => {
    expect(normalizeGuestRateLimit(cap)).toBe(30);
    expect(guestHistoryRefreshDelayMs(cap)).toBe(8000);
});

it.each([[30, 8000], [100, 5000], [1, 240000]])('reserves the guest audio polling quarter of cap %s', (cap, delay) => {
    expect(guestRecentAudioPollDelayMs(cap)).toBe(delay);
    expect(60000 / delay).toBeLessThanOrEqual(cap * 0.25);
});
