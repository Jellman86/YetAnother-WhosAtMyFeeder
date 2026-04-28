import { describe, expect, it } from 'vitest';
import type { Detection } from './api';
import { isVideoPromotionGated } from './video-promotion-gate';

function detection(overrides: Partial<Detection>): Detection {
    return {
        frigate_event: 'evt',
        display_name: 'Unknown Bird',
        score: 0.1,
        detection_time: '2026-04-28T00:00:00Z',
        camera_name: 'cam',
        ...overrides
    };
}

describe('isVideoPromotionGated', () => {
    it('does not show the gated notice when video scientific name matches the primary species identity', () => {
        expect(isVideoPromotionGated(detection({
            display_name: 'Common Wood-Pigeon',
            category_name: 'Columba palumbus',
            scientific_name: 'Columba palumbus',
            common_name: 'Common Wood-Pigeon',
            video_classification_status: 'completed',
            video_classification_label: 'Columba palumbus',
            video_classification_score: 0.98
        }))).toBe(false);
    });

    it('shows the gated notice when a completed real video result differs from the primary identity', () => {
        expect(isVideoPromotionGated(detection({
            display_name: 'Unknown Bird',
            video_classification_status: 'completed',
            video_classification_label: 'Blue Tit',
            video_classification_score: 0.42
        }))).toBe(true);
    });

    it('does not show the gated notice for blocked video results', () => {
        expect(isVideoPromotionGated(detection({
            display_name: 'Unknown Bird',
            video_classification_status: 'completed',
            video_classification_label: 'House Sparrow',
            video_result_blocked: true
        }))).toBe(false);
    });
});
