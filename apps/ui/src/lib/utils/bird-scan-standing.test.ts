import { describe, expect, it } from 'vitest';
import { birdScanStandingReason, birdScanUnavailableReason, birdScanUnavailableText, isStandingUnavailability } from './bird-scan-standing';

const say = (_id: string, options: { default: string }): string => options.default;

describe('isStandingUnavailability', () => {
    it('treats reasons the photograph cannot change as standing', () => {
        for (const reason of ['full_scene_unavailable', 'crop_model_unavailable', 'scan_in_progress', 'reviewed_other_frame']) {
            expect(isStandingUnavailability(reason), reason).toBe(true);
        }
    });

    it('keeps feedback on the scan just run, and an available finder, under the photograph', () => {
        expect(isStandingUnavailability('media_changed')).toBe(false);
        expect(isStandingUnavailability(null)).toBe(false);
        expect(isStandingUnavailability(undefined)).toBe(false);
    });
});

describe('birdScanUnavailableReason', () => {
    it('says no whole frame was kept when there is no frame or no image revision to scan', () => {
        expect(birdScanUnavailableReason(null, 'v1', null)).toBe('full_scene_unavailable');
        expect(birdScanUnavailableReason('scene', null, null)).toBe('full_scene_unavailable');
    });

    it('otherwise takes the reason the server gave, or none', () => {
        expect(birdScanUnavailableReason('scene', 'v1', { unavailable_reason: 'crop_model_unavailable' })).toBe('crop_model_unavailable');
        expect(birdScanUnavailableReason('scene', 'v1', { unavailable_reason: null })).toBeNull();
        expect(birdScanUnavailableReason('scene', 'v1', null)).toBeNull();
    });
});

describe('birdScanStandingReason', () => {
    it('is the standing reason while nothing is running and the status was read', () => {
        expect(birdScanStandingReason('full_scene_unavailable', { active: false, readError: false })).toBe('full_scene_unavailable');
    });

    it('is none while a scan runs, when the status could not be read, or for feedback on a scan', () => {
        expect(birdScanStandingReason('scan_in_progress', { active: true, readError: false })).toBeNull();
        expect(birdScanStandingReason('crop_model_unavailable', { active: false, readError: true })).toBeNull();
        expect(birdScanStandingReason('media_changed', { active: false, readError: false })).toBeNull();
        expect(birdScanStandingReason(null, { active: false, readError: false })).toBeNull();
    });
});

describe('birdScanUnavailableText', () => {
    it('says each reason in words', () => {
        expect(birdScanUnavailableText('crop_model_unavailable', say)).toBe('Install the bird finder to look for more birds in this photo.');
        expect(birdScanUnavailableText('full_scene_unavailable', say)).toMatch(/whole frame behind this photograph was not kept/);
        expect(birdScanUnavailableText('media_changed', say)).toMatch(/frame changed during the scan/);
    });
});
