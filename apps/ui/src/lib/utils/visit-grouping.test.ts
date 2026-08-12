import { describe, expect, it } from 'vitest';
import type { Detection } from '../api';
import {
    VISIT_GAP_MS,
    groupDetectionsIntoVisits as groupVisits,
    needsReview,
    withinDeskWindow
} from './visit-grouping';

function detection(overrides: Partial<Detection> & { frigate_event: string }): Detection {
    return {
        display_name: 'Eurasian Blackbird',
        score: 0.9,
        detection_time: '2026-08-11T11:34:45Z',
        camera_name: 'birdcam',
        ...overrides
    } as Detection;
}

function groupDetectionsIntoVisits(detections: readonly Detection[], gapMs: number = VISIT_GAP_MS) {
    return groupVisits(detections, { reviewThreshold: 0.6, gapMs });
}

describe('groupDetectionsIntoVisits', () => {
    it('uses the saved classification threshold instead of a hard-coded review floor', () => {
        const named = detection({ frigate_event: 'named', score: 0.52 });

        expect(needsReview(named, 0.3)).toBe(false);
        expect(needsReview(named, 0.6)).toBe(true);
        expect(needsReview(named, null)).toBe(false);
        expect(needsReview(detection({ frigate_event: 'unknown', display_name: 'Unknown Bird' }), null)).toBe(true);
    });

    it('folds repeat frames of one species on one camera into a single visit', () => {
        const visits = groupDetectionsIntoVisits([
            detection({ frigate_event: 'b', detection_time: '2026-08-11T11:34:45Z', score: 0.72 }),
            detection({ frigate_event: 'a', detection_time: '2026-08-11T11:34:16Z', score: 0.94 })
        ]);

        expect(visits).toHaveLength(1);
        expect(visits[0].frames).toHaveLength(2);
        expect(visits[0].lead.frigate_event).toBe('b');
        expect(visits[0].best.frigate_event).toBe('a');
        expect(visits[0].best.score).toBe(0.94);
    });

    it('keeps the same species apart when the gap exceeds the visit window', () => {
        const visits = groupDetectionsIntoVisits([
            detection({ frigate_event: 'late', detection_time: '2026-08-11T07:44:00Z' }),
            detection({ frigate_event: 'early', detection_time: '2026-08-11T06:18:00Z' })
        ]);

        expect(visits).toHaveLength(2);
        expect(visits.map((visit) => visit.lead.frigate_event)).toEqual(['late', 'early']);
    });

    it('never merges across cameras or across species', () => {
        const visits = groupDetectionsIntoVisits([
            detection({ frigate_event: 'a', detection_time: '2026-08-11T11:34:45Z' }),
            detection({
                frigate_event: 'b',
                detection_time: '2026-08-11T11:34:40Z',
                camera_name: 'nestcam'
            }),
            detection({
                frigate_event: 'c',
                detection_time: '2026-08-11T11:34:35Z',
                display_name: 'House Sparrow'
            })
        ]);

        expect(visits).toHaveLength(3);
    });

    it('orders visits newest first even when the input is not sorted', () => {
        const visits = groupDetectionsIntoVisits([
            detection({ frigate_event: 'old', detection_time: '2026-08-11T06:18:00Z' }),
            detection({ frigate_event: 'new', detection_time: '2026-08-11T17:49:00Z' })
        ]);

        expect(visits.map((visit) => visit.lead.frigate_event)).toEqual(['new', 'old']);
    });

    it('measures the gap against the nearest frame, not the first of the visit', () => {
        const withinWindow = groupDetectionsIntoVisits([
            detection({ frigate_event: 'c', detection_time: '2026-08-11T11:16:00Z' }),
            detection({ frigate_event: 'b', detection_time: '2026-08-11T11:08:00Z' }),
            detection({ frigate_event: 'a', detection_time: '2026-08-11T11:00:00Z' })
        ]);

        expect(withinWindow).toHaveLength(1);
        expect(withinWindow[0].frames).toHaveLength(3);
    });

    it('exposes the span of the visit and flags frames needing review', () => {
        const visits = groupDetectionsIntoVisits([
            detection({
                frigate_event: 'b',
                display_name: 'Unknown Bird',
                score: 0.56,
                detection_time: '2026-08-11T11:11:05Z'
            }),
            detection({
                frigate_event: 'a',
                display_name: 'Unknown Bird',
                score: 0.51,
                detection_time: '2026-08-11T11:10:05Z'
            })
        ]);

        expect(visits[0].startTime).toBe('2026-08-11T11:10:05Z');
        expect(visits[0].endTime).toBe('2026-08-11T11:11:05Z');
        expect(visits[0].needsReview).toBe(true);
    });

    it('treats a named detection above the threshold as resolved', () => {
        const visits = groupDetectionsIntoVisits([detection({ frigate_event: 'a', score: 0.98 })]);

        expect(visits[0].needsReview).toBe(false);
    });

    it('survives detections with unusable timestamps instead of collapsing them', () => {
        const visits = groupDetectionsIntoVisits([
            detection({ frigate_event: 'a', detection_time: 'not-a-date' }),
            detection({ frigate_event: 'b', detection_time: 'also-not-a-date' })
        ]);

        expect(visits).toHaveLength(2);
    });

    it('returns an empty list for no detections', () => {
        expect(groupDetectionsIntoVisits([])).toEqual([]);
    });

    it('accepts a custom gap window', () => {
        const visits = groupDetectionsIntoVisits(
            [
                detection({ frigate_event: 'b', detection_time: '2026-08-11T11:20:00Z' }),
                detection({ frigate_event: 'a', detection_time: '2026-08-11T11:00:00Z' })
            ],
            30 * 60 * 1000
        );

        expect(visits).toHaveLength(1);
        expect(VISIT_GAP_MS).toBe(10 * 60 * 1000);
    });

    it('keeps the desk on one window so its numbers cannot contradict each other', () => {
        const now = Date.parse('2026-08-11T18:00:00Z');
        const kept = withinDeskWindow(
            [
                detection({ frigate_event: 'today', detection_time: '2026-08-11T09:00:00Z' }),
                detection({ frigate_event: 'yesterday', detection_time: '2026-08-10T09:00:00Z' }),
                detection({ frigate_event: 'undated', detection_time: 'not-a-date' })
            ],
            now
        );

        // The undated one is kept: dropping a real detection is worse than an odd sort.
        expect(kept.map((item) => item.frigate_event)).toEqual(['today', 'undated']);
    });

    it('does not mutate the array it is given', () => {
        const input = [
            detection({ frigate_event: 'old', detection_time: '2026-08-11T06:18:00Z' }),
            detection({ frigate_event: 'new', detection_time: '2026-08-11T17:49:00Z' })
        ];
        const snapshot = input.map((item) => item.frigate_event);

        groupDetectionsIntoVisits(input);

        expect(input.map((item) => item.frigate_event)).toEqual(snapshot);
    });
});
