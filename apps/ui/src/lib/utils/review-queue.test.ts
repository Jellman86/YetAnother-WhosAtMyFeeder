import { describe, expect, it } from 'vitest';
import type { Detection } from '../api';
import {
    buildReviewQueue,
    readingFromResponse,
    reviewReasonMessage,
    visibleUnresolvedCount,
    withoutEvent,
    type QueuedDetection,
    type ReviewQueueReading,
    type ReviewReason
} from './review-queue';

function detection(overrides: Partial<Detection> & { frigate_event: string }): Detection {
    return {
        display_name: 'Eurasian Blackbird',
        score: 0.94,
        detection_time: '2026-08-11T11:34:45Z',
        camera_name: 'birdcam',
        ...overrides
    } as Detection;
}

function entry(item: Detection, reason: ReviewReason = 'low_score', sightings: number | null = null): QueuedDetection {
    return { detection: item, reason, sightings };
}

function reading(entries: QueuedDetection[], total: number = entries.length): ReviewQueueReading {
    return { entries, total };
}

describe('buildReviewQueue', () => {
    it('keeps the server total when it lists fewer than are waiting (#917)', () => {
        const queue = buildReviewQueue(
            reading([entry(detection({ frigate_event: 'a' })), entry(detection({ frigate_event: 'b' }))], 24),
            { reviewThreshold: 0.99 }
        );

        expect(queue.total).toBe(24);
        expect(queue.items).toHaveLength(2);
        expect(queue.remaining).toBe(22);
    });

    it('says why each detection waits, as the server read it', () => {
        const queue = buildReviewQueue(
            reading([
                entry(detection({ frigate_event: 'unnamed', display_name: 'Unknown Bird' }), 'unknown_species'),
                entry(detection({ frigate_event: 'shaky', score: 0.42 }), 'low_score'),
                entry(detection({ frigate_event: 'ibis' }), 'new_species', 2)
            ]),
            { reviewThreshold: 0.6 }
        );

        expect(queue.reasons.get('unnamed')).toBe('unknown_species');
        expect(queue.reasons.get('shaky')).toBe('low_score');
        expect(queue.reasons.get('ibis')).toBe('new_species');
        expect(queue.newSpeciesSightings.get('ibis')).toBe(2);
        expect(queue.newSpeciesSightings.has('shaky')).toBe(false);
    });

    it('puts the longest-waiting detection first so the backlog drains from the back', () => {
        const queue = buildReviewQueue(
            reading([
                entry(detection({ frigate_event: 'recent', score: 0.1, detection_time: '2026-08-11T17:49:00Z' })),
                entry(detection({ frigate_event: 'oldest', score: 0.1, detection_time: '2026-08-11T05:19:00Z' }))
            ]),
            { reviewThreshold: 0.6 }
        );

        expect(queue.items[0].frigate_event).toBe('oldest');
        expect(queue.oldest?.frigate_event).toBe('oldest');
    });

    it('previews the first few but keeps reporting everything else as remaining', () => {
        const entries = Array.from({ length: 9 }, (_unused, index) =>
            entry(detection({ frigate_event: `unknown-${index}`, display_name: 'Unknown Bird' }), 'unknown_species')
        );
        const queue = buildReviewQueue(reading(entries), { reviewThreshold: 0.6, limit: 4 });

        expect(queue.items).toHaveLength(4);
        expect(queue.total).toBe(9);
        expect(queue.remaining).toBe(5);
    });

    it('reports an empty reading as done rather than as missing data', () => {
        const queue = buildReviewQueue(reading([]), { reviewThreshold: 0.6 });

        expect(queue.total).toBe(0);
        expect(queue.items).toEqual([]);
        expect(queue.oldest).toBeNull();
        expect(queue.remaining).toBe(0);
    });

    it('does not requeue a low score the live record has since named confidently', () => {
        const listed = detection({ frigate_event: 'renamed', score: 0.2 });
        const queue = buildReviewQueue(reading([entry(listed)], 3), {
            reviewThreshold: 0.6,
            knownDetections: [{ ...listed, score: 0.9 }]
        });

        expect(queue.total).toBe(2);
        expect(queue.items).toEqual([]);
    });

    it('keeps an unknown bird waiting until the next reading says otherwise', () => {
        const listed = detection({ frigate_event: 'raw', display_name: 'Unknown Bird', score: 0.9 });
        const queue = buildReviewQueue(reading([entry(listed, 'unknown_species')]), {
            reviewThreshold: 0.6,
            knownDetections: [{ ...listed, display_name: 'background' }]
        });

        expect(queue.total).toBe(1);
    });

    it('keeps a waiting low score while settings have not said what the threshold is', () => {
        const queue = buildReviewQueue(reading([entry(detection({ frigate_event: 'weak', score: 0.2 }))]), { reviewThreshold: null });

        expect(queue.total).toBe(1);
    });

    it('a new species waits for confirmation even when its score is confident', () => {
        const queue = buildReviewQueue(reading([entry(detection({ frigate_event: 'ibis', score: 0.97 }), 'new_species', 1)]), { reviewThreshold: 0.6 });

        expect(queue.total).toBe(1);
    });
});

describe('newer knowledge settles a queued detection before the next reading', () => {
    it('honors a saved choice after that event leaves the recent history page', () => {
        const old = detection({ frigate_event: 'outside-page', score: 0.2 });
        const localChoices = new Map([['outside-page', { manual_tagged: true, classification_input: { source: 'owner_species_choice' } }]]);
        expect(buildReviewQueue(reading([entry(old, 'new_species', 1)]), { reviewThreshold: 0.6, localChoices }).total).toBe(0);
    });

    it('does not treat an ordinary automatic patch as an owner decision', () => {
        const old = detection({ frigate_event: 'automatic' });
        const localChoices = new Map([['automatic', { score: 0.98, classification_input: { source: 'full_frame', is_cropped: false } }]]);
        expect(buildReviewQueue(reading([entry(old, 'new_species', 1)]), { reviewThreshold: 0.6, localChoices }).total).toBe(1);
    });

    it('allows review after an explicit new generation replaces the local choice', () => {
        const old = detection({ frigate_event: 'reanalysed' });
        const localChoices = new Map([['reanalysed', { manual_tagged: false, classification_input: { source: 'full_frame', is_cropped: false } }]]);
        expect(buildReviewQueue(reading([entry(old, 'new_species', 1)]), { reviewThreshold: 0.6, localChoices }).total).toBe(1);
    });

    it('uses a saved owner decision over a stale reading', () => {
        const old = detection({ frigate_event: 'yesterday', score: 0.2 });
        const reviewed = { ...old, manual_tagged: true, classification_input: { source: 'owner_species_choice' } };
        expect(buildReviewQueue(reading([entry(old, 'new_species', 2)]), { reviewThreshold: 0.6, knownDetections: [reviewed] }).total).toBe(0);
    });

    it('uses a hidden live record over a stale reading', () => {
        const old = detection({ frigate_event: 'hidden-yesterday' });
        expect(buildReviewQueue(reading([entry(old, 'new_species', 2)]), { reviewThreshold: 0.6, knownDetections: [{ ...old, is_hidden: true }] }).total).toBe(0);
    });

    it('takes a hidden or deleted detection out of the reading at once', () => {
        const before = reading([entry(detection({ frigate_event: 'gone' })), entry(detection({ frigate_event: 'kept' }))], 5);
        const after = withoutEvent(before, 'gone');

        expect(after.total).toBe(4);
        expect(after.entries.map((item) => item.detection.frigate_event)).toEqual(['kept']);
        expect(withoutEvent(before, 'not-listed').total).toBe(5);
    });
});

describe('readingFromResponse', () => {
    it('carries each event, its reason and the full total', () => {
        const event = detection({ frigate_event: 'ibis' });
        const result = readingFromResponse({
            items: [{ event, reason: 'new_species', species_sightings: 2 }, { event: { ...event, frigate_event: 'weak' }, reason: 'low_score' }],
            total: 30,
            window_start: '2026-08-10T00:00:00Z',
            window_end: '2026-08-11T00:00:00Z'
        } as never);

        expect(result.total).toBe(30);
        expect(result.entries[0]).toEqual({ detection: event, reason: 'new_species', sightings: 2 });
        expect(result.entries[1].sightings).toBeNull();
    });
});

describe('visibleUnresolvedCount', () => {
    it('counts what a guest can see waiting, leaving out decided and hidden records', () => {
        expect(visibleUnresolvedCount([
            detection({ frigate_event: 'named' }),
            detection({ frigate_event: 'unknown', display_name: 'Unknown Bird' }),
            detection({ frigate_event: 'weak', score: 0.2 }),
            detection({ frigate_event: 'tagged', score: 0.2, manual_tagged: true }),
            detection({ frigate_event: 'hidden', display_name: 'Unknown Bird', is_hidden: true })
        ], 0.6)).toBe(2);
    });
});

describe('reviewReasonMessage', () => {
    it('words every reason a detection can wait for', () => {
        expect(reviewReasonMessage('unknown_species', 0)).toEqual({
            key: 'dashboard.review_queue.reason_unknown_species',
            default: 'Unknown species'
        });
        expect(reviewReasonMessage('low_score', 0)).toEqual({
            key: 'dashboard.review_queue.reason_low_score',
            default: 'Below the naming threshold'
        });
        expect(reviewReasonMessage('new_species', 3)).toEqual({
            key: 'dashboard.review_queue.new_species_tag',
            default: 'New species · {count, plural, one {# sighting} other {# sightings}}',
            values: { count: 3 }
        });
    });
});
