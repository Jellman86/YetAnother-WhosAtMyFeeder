import { describe, expect, it } from 'vitest';

import {
    activityTimestampForMode,
    countForMode,
    deltaForMode,
    trendForMode
} from './source-metrics';

const row = {
    count: 8,
    heard_count: 12,
    delta: 4,
    percent: 100,
    prev_count: 4,
    heard_delta: 3,
    heard_percent: 33.3,
    heard_prev_count: 9,
    last_seen: '2026-08-12T10:00:00Z',
    heard_last: '2026-08-13T11:00:00Z'
};

describe('leaderboard source metrics', () => {
    it('uses the selected source for counts and deltas', () => {
        expect(countForMode(row, 'seen')).toBe(8);
        expect(countForMode(row, 'heard')).toBe(12);
        expect(countForMode(row, 'both')).toBe(20);
        expect(deltaForMode(row, 'both')).toBe(7);
    });

    it('keeps valid heard and combined comparisons', () => {
        expect(trendForMode(row, 'heard')).toBe('+3 (33.3%)');
        expect(trendForMode(row, 'both')).toBe('+7 (53.8%)');
    });

    it('does not invent a percentage without a previous window', () => {
        expect(trendForMode({ ...row, prev_count: 0 }, 'seen')).toBe('+4');
        expect(trendForMode({ ...row, heard_prev_count: null }, 'heard')).toBe('+3');
    });

    it('keeps a percentage against a tiny baseline out of the trend', () => {
        expect(trendForMode({ ...row, delta: 92, percent: 9200, prev_count: 1 }, 'seen')).toBe('+92');
        expect(trendForMode({ ...row, heard_delta: 45, heard_percent: 4500, heard_prev_count: 1 }, 'heard')).toBe('+45');
        expect(trendForMode({ ...row, delta: 8, percent: 200, prev_count: 4 }, 'seen')).toBe('+8');
    });

    it('keeps a runaway percentage out even when the baseline is readable', () => {
        expect(trendForMode({ ...row, delta: 60, percent: 1200, prev_count: 5 }, 'seen')).toBe('+60');
    });

    it('keeps a modest percentage on a readable baseline', () => {
        expect(trendForMode({ ...row, delta: 5, percent: 100, prev_count: 5 }, 'seen')).toBe('+5 (100.0%)');
    });

    it('uses the latest evidence timestamp for the combined source', () => {
        expect(activityTimestampForMode(row, 'seen')).toBe(row.last_seen);
        expect(activityTimestampForMode(row, 'heard')).toBe(row.heard_last);
        expect(activityTimestampForMode(row, 'both')).toBe(row.heard_last);
    });
});
