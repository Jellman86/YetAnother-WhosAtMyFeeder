import { describe, expect, it } from 'vitest';
import type { Detection } from '../api';
import { buildReviewQueue as buildQueue } from './review-queue';

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
