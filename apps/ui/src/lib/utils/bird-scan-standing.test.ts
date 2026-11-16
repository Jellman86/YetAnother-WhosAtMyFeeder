import { describe, expect, it } from 'vitest';
import { isStandingUnavailability } from './bird-scan-standing';

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
