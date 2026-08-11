import { describe, expect, it } from 'vitest';

import {
    MAX_MANUAL_IMAGE_BYTES,
    MAX_MANUAL_VIDEO_BYTES,
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
