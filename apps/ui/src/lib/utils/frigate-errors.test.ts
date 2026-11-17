import { describe, expect, it } from 'vitest';

import type { Detection } from '../api';
import { getVideoFailureInsight, hasFrigateMediaIssue } from './frigate-errors';

const t = (_key: string, options?: Record<string, unknown>) =>
    String(options?.default ?? _key);

function buildDetection(overrides: Partial<Detection> = {}): Detection {
    return {
        frigate_event: 'evt-1',
        display_name: 'Unknown Bird',
        score: 0.81,
        detection_time: '2026-04-05T10:00:00Z',
        camera_name: 'cam1',
        has_clip: false,
        has_snapshot: false,
        has_frigate_event: false,
        video_classification_error: 'event_not_found',
        ...overrides
    };
}

describe('frigate media error insights', () => {
    it('does not treat cached media as a missing-Frigate event failure', () => {
        const detection = buildDetection({
            has_clip: true,
            has_snapshot: true
        });

        expect(hasFrigateMediaIssue(detection)).toBe(false);

        const insight = getVideoFailureInsight(detection, t);
        expect(insight.summary).toBe('Frigate no longer has this event, but YA-WAMF still has its media.');
        expect(insight.isFrigateRelated).toBe(true);
    });

    it('still treats a missing Frigate event with no media as a real media issue', () => {
        const detection = buildDetection();

        expect(hasFrigateMediaIssue(detection)).toBe(true);

        const insight = getVideoFailureInsight(detection, t);
        expect(insight.summary).toBe('Event not found in Frigate.');
        expect(insight.isFrigateRelated).toBe(true);
    });

    it('does not report an event as missing when Frigate could not be asked', () => {
        const detection = buildDetection({
            has_clip: true,
            has_snapshot: true,
            has_frigate_event: false,
            frigate_event_check: 'unreachable',
            video_classification_error: null
        });

        expect(hasFrigateMediaIssue(detection)).toBe(false);
        const insight = getVideoFailureInsight(detection, t);
        expect(insight.summary).not.toContain('gone');
        expect(insight.summary).not.toBe('Event not found in Frigate.');
    });
});
