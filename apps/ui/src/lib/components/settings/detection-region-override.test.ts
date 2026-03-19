import { describe, expect, it } from 'vitest';

import {
    BIRD_MODEL_REGION_OVERRIDE_VALUES,
    normalizeBirdModelRegionOverride,
    roundTripBirdModelRegionOverride,
} from '../../settings/bird-model-region-override';

describe('detection region override helpers', () => {
    it('normalizes unsupported values to auto', () => {
        expect(normalizeBirdModelRegionOverride(undefined)).toBe('auto');
        expect(normalizeBirdModelRegionOverride(null)).toBe('auto');
        expect(normalizeBirdModelRegionOverride('')).toBe('auto');
        expect(normalizeBirdModelRegionOverride('north-america')).toBe('auto');
    });

    it('exposes the supported override options in UI order', () => {
        expect(BIRD_MODEL_REGION_OVERRIDE_VALUES).toEqual(['auto', 'eu', 'na']);
    });

    it('round-trips the settings value through load and save helpers', () => {
        const roundTrip = roundTripBirdModelRegionOverride('north-america', 'eu');

        expect(roundTrip.loaded).toBe('auto');
        expect(roundTrip.payload).toEqual({
            bird_model_region_override: 'eu',
        });
    });
});
