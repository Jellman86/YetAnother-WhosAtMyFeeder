import { describe, expect, it } from 'vitest';
import type { Detection } from '../api';
import type { DetectionVisit } from './visit-grouping';
import { visitBirdMarker } from './visit-birds';

type Summary = NonNullable<Detection['bird_summary']>;

function summary(counted: number, overrides: Partial<Summary> = {}): Summary {
    return { counted, unknown: 0, excluded: 0, species: [], hint_only: false, ...overrides };
}

function frame(event: string, birdSummary: Summary | null | undefined, score = 0.9): Detection {
    return {
        frigate_event: event,
        display_name: 'House Finch',
        score,
        detection_time: '2026-09-30T12:00:00Z',
        camera_name: 'feeder',
        ...(birdSummary === undefined ? {} : { bird_summary: birdSummary })
    };
}

function visit(frames: Detection[], best = frames[0]): DetectionVisit {
    return {
        key: frames[0].frigate_event,
        species: 'House Finch',
        camera: 'feeder',
        frames,
        lead: frames[0],
        best,
        startTime: frames[frames.length - 1].detection_time,
        endTime: frames[0].detection_time,
        needsReview: false,
        audioConfirmed: false
    };
}

describe('visitBirdMarker', () => {
    it('says nothing when no capture in the visit has stored observation evidence', () => {
        expect(visitBirdMarker(visit([frame('a', undefined), frame('b', null)]))).toBeNull();
    });

    it('says nothing for one counted bird, which is what a visit row already implies', () => {
        expect(visitBirdMarker(visit([frame('a', summary(1))]))).toBeNull();
    });

    it('reports the single capture with the most birds rather than summing repeat frames', () => {
        const busiest = frame('b', summary(3, { unknown: 1 }));
        const marker = visitBirdMarker(visit([frame('a', summary(2)), busiest, frame('c', summary(2))]));
        expect(marker?.detection.frigate_event).toBe('b');
        expect(marker?.summary.counted).toBe(3);
    });

    it('prefers the clearest capture on a tie, so the marker opens the frame the row shows', () => {
        const best = frame('b', summary(2), 0.95);
        const marker = visitBirdMarker(visit([frame('a', summary(2)), best], best));
        expect(marker?.detection.frigate_event).toBe('b');
    });

    it('states a measured zero only when every stored bird was excluded', () => {
        const marker = visitBirdMarker(visit([frame('a', summary(0, { excluded: 2 }))]));
        expect(marker?.summary).toEqual(summary(0, { excluded: 2 }));
        expect(visitBirdMarker(visit([frame('a', summary(0))]))).toBeNull();
    });

    it('lets a counted capture outrank an all-excluded one', () => {
        const marker = visitBirdMarker(visit([frame('a', summary(0, { excluded: 1 })), frame('b', summary(2))]));
        expect(marker?.detection.frigate_event).toBe('b');
    });
});
