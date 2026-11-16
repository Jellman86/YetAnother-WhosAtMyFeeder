import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { dailySeries, hourlySeries } from './audio-chart-series';

// The browser's zone is the reader's, not the server's; Auckland is a day ahead of UTC at noon.
const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
let previousZone: string | undefined;
beforeAll(() => { previousZone = env.TZ; env.TZ = 'Pacific/Auckland'; });
afterAll(() => { if (previousZone === undefined) delete env.TZ; else env.TZ = previousZone; });

describe('dailySeries', () => {
    it('reads each bucket as the calendar day the server counted, in every time zone', () => {
        // The old table formatted UTC noon in the local zone and showed 16 Nov in Auckland.
        expect(new Date('2026-11-15T12:00:00Z').getDate()).toBe(16);
        const series = dailySeries([{ date: '2026-11-15', count: 4 }, { date: '2026-11-16', count: 0 }], 'en-GB');
        expect(series.map((point) => point.label)).toEqual(['15 Nov', '16 Nov']);
        expect(series.map((point) => point.count)).toEqual([4, 0]);
    });
});

describe('hourlySeries', () => {
    it('is always 24 hours, with the hours nothing was heard in as zero', () => {
        const series = hourlySeries([{ hour: 6, count: 3 }, { hour: 23, count: 1 }, { hour: 24, count: 9 }, { hour: -1, count: 9 }]);
        expect(series).toHaveLength(24);
        expect(series[0]).toEqual({ hour: 0, label: '00:00', count: 0 });
        expect(series[6]).toEqual({ hour: 6, label: '06:00', count: 3 });
        expect(series[23].count).toBe(1);
        expect(series.reduce((sum, point) => sum + point.count, 0)).toBe(4);
    });
});
