import { describe, expect, it } from 'vitest';
import {
    getClassificationInputKind,
    getDetectionClassificationSource,
    shouldShowVideoStatusNotice
} from './detection-classification-source';
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

    it('does not present a completed snapshot fallback as video evidence', () => {
        const detection = buildDetection({
            category_name: 'blue jay',
            video_classification_status: 'completed',
            video_classification_label: 'Blue Jay',
            video_classification_input_source: 'hq_candidate_frigate_hint_crop'
        });

        expect(getDetectionClassificationSource(detection)).toBe('snapshot');
    });

    it('maps persisted input provenance to honest user-facing source kinds', () => {
        expect(getClassificationInputKind('frigate_hint_crop')).toBe('video_crop');
        expect(getClassificationInputKind('full_frame')).toBe('video_full');
        expect(getClassificationInputKind('hq_candidate_model_crop')).toBe('snapshot_crop');
        expect(getClassificationInputKind('snapshot_model_crop')).toBe('snapshot_crop');
        expect(getClassificationInputKind('hq_candidate_full_frame')).toBe('snapshot_full');
        expect(getClassificationInputKind('cached_snapshot_unknown')).toBe('snapshot_full');
        expect(getClassificationInputKind('frigate_sublabel')).toBe('upstream');
        expect(getClassificationInputKind('unexpected')).toBe('unknown');
    });

    it('does not present a trusted Frigate fallback as video evidence', () => {
        const detection = buildDetection({
            category_name: 'robin',
            video_classification_status: 'completed',
            video_classification_label: 'Robin',
            video_classification_input_source: 'frigate_sublabel'
        });

        expect(getDetectionClassificationSource(detection)).toBe('snapshot');
    });
});

describe('shouldShowVideoStatusNotice', () => {
    it('hides an earlier inconclusive video result after a manual identification', () => {
        const detection = buildDetection({
            manual_tagged: true,
            category_name: 'Prunella modularis',
            video_classification_status: 'failed',
            video_classification_error: 'video_no_results'
        });

        expect(shouldShowVideoStatusNotice(detection, false)).toBe(false);
    });

    it('still shows an inconclusive video result when it remains relevant to the current identification', () => {
        const detection = buildDetection({
            video_classification_status: 'failed',
            video_classification_error: 'video_no_results'
        });

        expect(shouldShowVideoStatusNotice(detection, false)).toBe(true);
    });

    it('still explains missing upstream media for a snapshot identification', () => {
        expect(shouldShowVideoStatusNotice(buildDetection(), true)).toBe(true);
    });
});
