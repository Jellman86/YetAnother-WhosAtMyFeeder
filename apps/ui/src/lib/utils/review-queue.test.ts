import { describe, expect, it } from 'vitest';
import type { Detection } from '../api';
import { buildReviewQueue as buildQueue, reviewReasonMessage } from './review-queue';

function detection(overrides: Partial<Detection> & { frigate_event: string }): Detection {
    return {
        display_name: 'Eurasian Blackbird',
        score: 0.94,
        detection_time: '2026-08-11T11:34:45Z',
        camera_name: 'birdcam',
        ...overrides
    } as Detection;
}

function buildReviewQueue(detections: readonly Detection[], limit: number = 4) {
    return buildQueue(detections, { reviewThreshold: 0.6, limit });
}

describe('buildReviewQueue', () => {
    it('says whether each detection waits for want of a species or for a shaky score', () => {
        const queue = buildReviewQueue([
            detection({ frigate_event: 'unnamed', display_name: 'Unknown Bird', score: 0.91 }),
            detection({ frigate_event: 'blank', display_name: '  ', score: 0.91 }),
            detection({ frigate_event: 'shaky', display_name: 'Dunnock', score: 0.42 })
        ]);

        expect(queue.reasons.get('unnamed')).toBe('unknown_species');
        expect(queue.reasons.get('blank')).toBe('unknown_species');
        expect(queue.reasons.get('shaky')).toBe('low_score');
    });

    it('uses the configured naming threshold when deciding what needs a person', () => {
        const queue = buildQueue(
            [
                detection({ frigate_event: 'accepted', score: 0.52 }),
                detection({ frigate_event: 'weak', score: 0.22 })
            ],
            { reviewThreshold: 0.3 }
        );

        expect(queue.items.map((item) => item.frigate_event)).toEqual(['weak']);
    });

    it('collects unnamed and low-confidence detections and leaves confident ones alone', () => {
        const queue = buildReviewQueue([
            detection({ frigate_event: 'named', score: 0.98 }),
            detection({ frigate_event: 'unknown', display_name: 'Unknown Bird', score: 0.51 }),
            detection({ frigate_event: 'weak', display_name: 'Dunnock', score: 0.42 })
        ]);

        expect(queue.total).toBe(2);
        expect(queue.items.map((item) => item.frigate_event)).toEqual(['unknown', 'weak']);
    });

    it('accepts confident whole-view names while keeping low-confidence whole-view names for review', () => {
        const queue = buildReviewQueue([
            detection({ frigate_event: 'confident-whole', display_name: 'Dunnock', score: 0.8688878715,
                classification_input: { source: 'full_frame', is_cropped: false } }),
            detection({ frigate_event: 'weak-whole', score: 0.59,
                classification_input: { source: 'full_frame', is_cropped: false } }),
            detection({ frigate_event: 'owner-whole', score: 0.2, manual_tagged: true,
                classification_input: { source: 'full_frame', is_cropped: false } })
        ]);
        expect(queue.items.map(item => item.frigate_event)).toEqual(['weak-whole']);
        expect(queue.reasons.get('weak-whole')).toBe('low_score');
    });

    it('puts the longest-waiting detection first so the backlog drains from the back', () => {
        const queue = buildReviewQueue([
            detection({
                frigate_event: 'recent',
                display_name: 'Unknown Bird',
                detection_time: '2026-08-11T17:49:00Z'
            }),
            detection({
                frigate_event: 'oldest',
                display_name: 'Unknown Bird',
                detection_time: '2026-08-11T05:19:00Z'
            })
        ]);

        expect(queue.items[0].frigate_event).toBe('oldest');
        expect(queue.oldest?.frigate_event).toBe('oldest');
    });

    it('caps the previewed items but keeps reporting the real total', () => {
        const queue = buildReviewQueue(
            Array.from({ length: 9 }, (_unused, index) =>
                detection({
                    frigate_event: `unknown-${index}`,
                    display_name: 'Unknown Bird',
                    detection_time: `2026-08-11T0${index}:00:00Z`
                })
            ),
            4
        );

        expect(queue.items).toHaveLength(4);
        expect(queue.total).toBe(9);
        expect(queue.remaining).toBe(5);
    });

    it('skips hidden detections because they are already dealt with', () => {
        const queue = buildReviewQueue([
            detection({ frigate_event: 'hidden', display_name: 'Unknown Bird', is_hidden: true }),
            detection({ frigate_event: 'open', display_name: 'Unknown Bird' })
        ]);

        expect(queue.items.map((item) => item.frigate_event)).toEqual(['open']);
    });

    it('skips detections a human has already tagged even if the score stayed low', () => {
        const queue = buildReviewQueue([
            detection({ frigate_event: 'tagged', score: 0.3, manual_tagged: true }),
            detection({ frigate_event: 'open', score: 0.3 })
        ]);

        expect(queue.items.map((item) => item.frigate_event)).toEqual(['open']);
    });

    it('reports an empty queue as done rather than as missing data', () => {
        const queue = buildReviewQueue([detection({ frigate_event: 'named' })]);

        expect(queue.total).toBe(0);
        expect(queue.items).toEqual([]);
        expect(queue.oldest).toBeNull();
        expect(queue.remaining).toBe(0);
    });
});

describe('buildReviewQueue with new-species candidates (#310)', () => {
    it('honors a saved choice after that event leaves the recent history page', () => {
        const old = detection({ frigate_event: 'outside-page', score: 0.2 });
        const localChoices = new Map([['outside-page', { manual_tagged: true, classification_input: { source: 'owner_species_choice' } }]]);
        expect(buildQueue([], { reviewThreshold: 0.6, localChoices, newSpecies: [{ detection: old, sightings: 1 }] }).total).toBe(0);
    });

    it('does not treat an ordinary automatic patch as an owner decision', () => {
        const old = detection({ frigate_event: 'automatic' });
        const localChoices = new Map([['automatic', { score: 0.98, classification_input: { source: 'full_frame', is_cropped: false } }]]);
        expect(buildQueue([], { reviewThreshold: 0.6, localChoices, newSpecies: [{ detection: old, sightings: 1 }] }).total).toBe(1);
    });

    it('allows review after an explicit new generation replaces the local choice', () => {
        const old = detection({ frigate_event: 'reanalysed' });
        const localChoices = new Map([['reanalysed', { manual_tagged: false, classification_input: { source: 'full_frame', is_cropped: false } }]]);
        expect(buildQueue([], { reviewThreshold: 0.6, localChoices, newSpecies: [{ detection: old, sightings: 1 }] }).total).toBe(1);
    });

    it('uses a saved owner decision outside the desk window over a stale newcomer', () => {
        const old = detection({ frigate_event: 'yesterday', score: 0.2, detection_time: '2026-08-10T08:00:00Z' });
        const reviewed = { ...old, manual_tagged: true, classification_input: { source: 'owner_species_choice' } };
        const queue = buildQueue([], { reviewThreshold: 0.6, knownDetections: [reviewed], newSpecies: [{ detection: old, sightings: 2 }] });
        expect(queue.total).toBe(0);
    });

    it('uses a hidden historical record over an older visible newcomer', () => {
        const old = detection({ frigate_event: 'hidden-yesterday' });
        const queue = buildQueue([], { reviewThreshold: 0.6, knownDetections: [{ ...old, is_hidden: true }], newSpecies: [{ detection: old, sightings: 2 }] });
        expect(queue.total).toBe(0);
    });

    it('keeps an unreviewed historical newcomer without admitting other old low scores', () => {
        const newcomer = detection({ frigate_event: 'yesterday-newcomer', score: 0.2 });
        const oldLowScore = detection({ frigate_event: 'yesterday-low-score', score: 0.1 });
        const queue = buildQueue([], { reviewThreshold: 0.6, knownDetections: [newcomer, oldLowScore], newSpecies: [{ detection: newcomer, sightings: 2 }] });
        expect(queue.items.map(item => item.frigate_event)).toEqual(['yesterday-newcomer']);
        expect(queue.reasons.get('yesterday-newcomer')).toBe('new_species');
    });

    it('does not requeue a saved owner choice from an older new-species response', () => {
        const old = detection({ frigate_event: 'reviewed', score: 0.2 });
        const reviewed = { ...old, manual_tagged: true, classification_input: { source: 'owner_species_choice' } };
        const queue = buildQueue([reviewed], { reviewThreshold: 0.6, newSpecies: [{ detection: old, sightings: 2 }] });
        expect(queue.total).toBe(0);
        expect(queue.reasons.size).toBe(0);
    });

    it('queues an unconfirmed newcomer with its reason and sighting count', () => {
        const newcomer = detection({ frigate_event: 'ibis', display_name: 'Hadeda Ibis', score: 0.34 });
        const queue = buildQueue([detection({ frigate_event: 'named', score: 0.98 })], {
            reviewThreshold: 0.3,
            newSpecies: [{ detection: newcomer, sightings: 2 }]
        });

        expect(queue.items.map((item) => item.frigate_event)).toEqual(['ibis']);
        expect(queue.reasons.get('ibis')).toBe('new_species');
        expect(queue.newSpeciesSightings.get('ibis')).toBe(2);
    });

    it('one detection qualifying both ways appears once, wearing the sharper reason', () => {
        const both = detection({ frigate_event: 'both', score: 0.2 });
        const queue = buildQueue([both], {
            reviewThreshold: 0.6,
            newSpecies: [{ detection: both, sightings: 1 }]
        });

        expect(queue.total).toBe(1);
        expect(queue.reasons.get('both')).toBe('new_species');
    });

    it('a hidden or already-confirmed newcomer asks for nothing', () => {
        const hidden = detection({ frigate_event: 'hid', is_hidden: true });
        const confirmed = detection({ frigate_event: 'conf', manual_tagged: true });
        const queue = buildQueue([], {
            reviewThreshold: 0.6,
            newSpecies: [
                { detection: hidden, sightings: 1 },
                { detection: confirmed, sightings: 1 }
            ]
        });

        expect(queue.total).toBe(0);
    });

    it('merged entries keep the oldest-first order', () => {
        const older = detection({ frigate_event: 'older', score: 0.2, detection_time: '2026-08-10T08:00:00Z' });
        const newer = detection({ frigate_event: 'newer', detection_time: '2026-08-11T08:00:00Z' });
        const queue = buildQueue([older], {
            reviewThreshold: 0.6,
            newSpecies: [{ detection: newer, sightings: 1 }]
        });

        expect(queue.items.map((item) => item.frigate_event)).toEqual(['older', 'newer']);
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
