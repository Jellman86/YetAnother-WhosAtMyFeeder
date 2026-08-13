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

    it('uses the latest evidence timestamp for the combined source', () => {
        expect(activityTimestampForMode(row, 'seen')).toBe(row.last_seen);
        expect(activityTimestampForMode(row, 'heard')).toBe(row.heard_last);
        expect(activityTimestampForMode(row, 'both')).toBe(row.heard_last);
    });
});
