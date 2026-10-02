import { describe, expect, it } from 'vitest';

import {
    MAX_MANUAL_IMAGE_BYTES,
    MAX_MANUAL_VIDEO_BYTES,
    findPredictionForSpecies,
    formatVideoOffset,
    validateManualObservationUpload
} from './manual-observation-upload';

describe('manual observation upload validation', () => {
    it('accepts supported media at the exact backend limits', () => {
        expect(validateManualObservationUpload({ type: 'image/jpeg', size: MAX_MANUAL_IMAGE_BYTES })).toEqual({ ok: true });
        expect(validateManualObservationUpload({ type: 'video/mp4', size: MAX_MANUAL_VIDEO_BYTES })).toEqual({ ok: true });
    });

    it('rejects images larger than 25 MiB before upload', () => {
        expect(validateManualObservationUpload({ type: 'image/webp', size: MAX_MANUAL_IMAGE_BYTES + 1 })).toEqual({
            ok: false,
            reason: 'image_too_large'
        });
    });

    it('rejects videos larger than 250 MiB before upload', () => {
        expect(validateManualObservationUpload({ type: 'video/quicktime', size: MAX_MANUAL_VIDEO_BYTES + 1 })).toEqual({
            ok: false,
            reason: 'video_too_large'
        });
    });

    it('rejects unsupported media types', () => {
        expect(validateManualObservationUpload({ type: 'application/octet-stream', size: 1 })).toEqual({
            ok: false,
            reason: 'unsupported_type'
        });
    });
});

describe('manual observation species photo', () => {
    const predictions = [
        { label: 'Baeolophus bicolor', common_name: 'Tufted Titmouse', photo_url: '/t' },
        { label: 'Dryobates_pubescens', scientific_name: 'Dryobates pubescens', common_name: 'Downy Woodpecker', photo_url: '/d' }
    ];

    it('finds the suggestion a species refers to by any of its names', () => {
        expect(findPredictionForSpecies(predictions, 'downy  woodpecker')?.photo_url).toBe('/d');
        expect(findPredictionForSpecies(predictions, 'Dryobates pubescens')?.photo_url).toBe('/d');
        expect(findPredictionForSpecies(predictions, 'Baeolophus bicolor')?.photo_url).toBe('/t');
    });

    it('finds nothing for a species the analysis did not suggest', () => {
        expect(findPredictionForSpecies(predictions, 'Carolina Wren')).toBeNull();
        expect(findPredictionForSpecies(predictions, '   ')).toBeNull();
    });

    it('says where a frame is in minutes and seconds', () => {
        expect(formatVideoOffset(4.6)).toBe('0:04');
        expect(formatVideoOffset(72)).toBe('1:12');
        expect(formatVideoOffset(-1)).toBe('0:00');
    });
});
