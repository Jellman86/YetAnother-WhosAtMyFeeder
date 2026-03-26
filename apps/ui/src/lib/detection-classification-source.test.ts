import { describe, expect, it } from 'vitest';
import { getDetectionClassificationSource } from './detection-classification-source';
import type { Detection } from './api';

function buildDetection(overrides: Partial<Detection> = {}): Detection {
    return {
        frigate_event: 'evt-1',
        display_name: 'Blue Jay',
        category_name: 'blue jay',
        score: 0.88,
        detection_time: '2026-03-26T12:00:00Z',
        camera_name: 'BirdCam',
        manual_tagged: false,
        video_classification_status: null,
        video_classification_label: null as any,
        ...overrides,
    };
}

describe('getDetectionClassificationSource', () => {
    it('treats matching completed video labels as the current source even when manual feedback exists historically', () => {
        const detection = buildDetection({
            manual_tagged: true,
            category_name: "cassin's finch (adult male)",
            video_classification_status: 'completed',
            video_classification_label: "Cassin's Finch"
        });

        expect(getDetectionClassificationSource(detection)).toBe('video');
    });

    it('keeps manual as the current source when the completed video result did not override the primary species', () => {
        const detection = buildDetection({
            manual_tagged: true,
            category_name: 'house sparrow',
            video_classification_status: 'completed',
            video_classification_label: 'blue jay'
        });

        expect(getDetectionClassificationSource(detection)).toBe('manual');
    });

    it('falls back to snapshot when there is no manual or current video override', () => {
        expect(getDetectionClassificationSource(buildDetection())).toBe('snapshot');
    });
});
