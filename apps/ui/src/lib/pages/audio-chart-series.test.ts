import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { dailySeries } from './audio-chart-series';

// The browser's zone is the reader's, not the server's; Auckland is a day ahead of UTC at noon.
const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
let previousZone: string | undefined;
beforeAll(() => { previousZone = env.TZ; env.TZ = 'Pacific/Auckland'; });
afterAll(() => { if (previousZone === undefined) delete env.TZ; else env.TZ = previousZone; });

describe('dailySeries', () => {
    it('reads each bucket as the calendar day the server counted, in every time zone', () => {
        // The old table formatted UTC noon in the local zone and showed 16 Nov in Auckland.
        expect(new Date('2026-11-15T12:00:00Z').getDate()).toBe(16);
        // The day reaches the label as the plain date the server sent, with no instant to shift.
        const series = dailySeries([{ date: '2026-11-15', count: 4 }, { date: '2026-11-16', count: 0 }], (day) => `day ${day}`);
        expect(series.map((point) => point.label)).toEqual(['day 2026-11-15', 'day 2026-11-16']);
        expect(series.map((point) => point.count)).toEqual([4, 0]);
    });
});
