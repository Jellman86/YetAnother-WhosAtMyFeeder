import { expect, it } from 'vitest';
import { guestHistoryRefreshDelayMs, guestRecentAudioPollDelayMs, normalizeGuestRateLimit, telemetrySampleDelayMs } from './public-refresh-budget';

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

it.each([[30, 60000], [100, 60000], [1, 300000]])('samples the decorative telemetry once a minute, within a fifth of a visitor cap %s', (cap, delay) => {
    expect(telemetrySampleDelayMs({ guest: true, cap, failures: 0 })).toBe(delay);
    expect(60000 / delay).toBeLessThanOrEqual(cap * 0.2);
});

it('samples the decorative telemetry no more than once a minute without the pushed status', () => {
    expect(telemetrySampleDelayMs({ guest: false, cap: 1, failures: 0 })).toBe(60000);
});

it.each([[1, 120000], [2, 240000], [6, 300000], [40, 300000]])('backs off after %s failed telemetry samples in a row', (failures, delay) => {
    expect(telemetrySampleDelayMs({ guest: false, cap: 30, failures })).toBe(delay);
});

it('never samples a rate-limited visitor faster than the budget allows, even while backing off', () => {
    expect(telemetrySampleDelayMs({ guest: true, cap: 1, failures: 3 })).toBe(300000);
});
