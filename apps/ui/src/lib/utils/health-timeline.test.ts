import { describe, expect, it } from 'vitest';

import { buildHealthTimeline, hiddenEventCount, instanceWindowMs } from './health-timeline';
import type { DetectionVisit } from './visit-grouping';

function visit(key: string, endTime: string): DetectionVisit {
    return {
        key,
        species: 'Cyanistes caeruleus',
        camera: 'birdcam',
        frames: [],
        lead: {} as DetectionVisit['lead'],
        best: {} as DetectionVisit['best'],
        startTime: endTime,
        endTime,
        needsReview: false
    };
}

const drop = (eventId: string, timestamp: string | null) => ({
    eventId,
    reason: 'filter_low_confidence',
    label: 'Oryctolagus cuniculus',
    score: 0.21,
    timestamp
});

describe('health timeline', () => {
    it('interleaves kept visits and filtered frames newest first', () => {
        const rows = buildHealthTimeline({
            visits: [visit('a', '2026-08-15T06:12:04Z'), visit('b', '2026-08-15T05:53:41Z')],
            filtered: [drop('x', '2026-08-15T06:15:57Z'), drop('y', '2026-08-15T06:01:29Z')]
        });
        expect(rows.map(row => row.key)).toEqual(['drop:x', 'visit:a', 'drop:y', 'visit:b']);
        expect(rows.map(row => row.kind)).toEqual(['filtered', 'visit', 'filtered', 'visit']);
    });

    it('keeps an unreadable timestamp at the end instead of dropping the event', () => {
        const rows = buildHealthTimeline({
            visits: [visit('a', '2026-08-15T06:12:04Z')],
            filtered: [drop('x', null), drop('y', 'not a date')]
        });
        expect(rows[0].key).toBe('visit:a');
        expect(rows.slice(1).map(row => row.key).sort()).toEqual(['drop:x', 'drop:y']);
    });

    it('honours the row limit and copes with an empty feeder', () => {
        const rows = buildHealthTimeline({
            filtered: [drop('x', '2026-08-15T06:15:57Z'), drop('y', '2026-08-15T06:01:29Z')],
            limit: 1
        });
        expect(rows).toHaveLength(1);
        expect(buildHealthTimeline({})).toEqual([]);
        expect(buildHealthTimeline({ visits: [], filtered: [], limit: 0 })).toEqual([]);
    });

    it('gives visits and drops distinct keys so one cannot displace the other', () => {
        const rows = buildHealthTimeline({
            visits: [visit('same', '2026-08-15T06:12:04Z')],
            filtered: [drop('same', '2026-08-15T06:12:04Z')]
        });
        expect(new Set(rows.map(row => row.key)).size).toBe(2);
    });
});

describe('instance window', () => {
    it('measures back to when this instance started', () => {
        const now = Date.parse('2026-08-15T06:22:54Z');
        expect(instanceWindowMs('2026-08-15T02:01:15Z', now)).toBe(now - Date.parse('2026-08-15T02:01:15Z'));
    });

    it('never returns a negative window when clocks disagree', () => {
        const now = Date.parse('2026-08-15T02:00:00Z');
        expect(instanceWindowMs('2026-08-15T02:01:15Z', now)).toBe(0);
    });

    it('reports null when the start time is unusable, so the caller can say so', () => {
        expect(instanceWindowMs(null)).toBe(null);
        expect(instanceWindowMs('nonsense')).toBe(null);
    });
});

describe('hidden events', () => {
    it('counts the remainder from the pipeline total, not from the rows', () => {
        expect(hiddenEventCount(34, 7)).toBe(27);
    });

    it('never goes negative when the store holds more than the counter', () => {
        expect(hiddenEventCount(3, 7)).toBe(0);
        expect(hiddenEventCount(0, 7)).toBe(0);
        expect(hiddenEventCount(Number.NaN, 7)).toBe(0);
    });
});
