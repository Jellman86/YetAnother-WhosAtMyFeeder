import { describe, expect, it } from 'vitest';

import {
    EBIRD_RADIUS_MAX_KM,
    EBIRD_RADIUS_MIN_KM,
    ebirdRadiusFromDisplayValue,
    ebirdRadiusToDisplayValue,
    getEbirdRadiusBounds
} from './ebird-radius';

describe('eBird radius conversion', () => {
    it('reports eBird own limits when the radius is shown in kilometres', () => {
        expect(getEbirdRadiusBounds('metric')).toEqual({ min: EBIRD_RADIUS_MIN_KM, max: EBIRD_RADIUS_MAX_KM });
    });

    it.each(['imperial', 'british'] as const)('reports the same ceiling in miles for %s', system => {
        expect(getEbirdRadiusBounds(system)).toEqual({ min: 1, max: 31 });
    });

    it('leaves a kilometre radius untouched for metric owners', () => {
        expect(ebirdRadiusToDisplayValue(25, 'metric')).toBe(25);
        expect(ebirdRadiusFromDisplayValue(25, 'metric')).toBe(25);
    });

    it('converts a stored radius into whole miles for display', () => {
        expect(ebirdRadiusToDisplayValue(25, 'imperial')).toBe(16);
        expect(ebirdRadiusToDisplayValue(25, 'british')).toBe(16);
    });

    it('converts an edited mile value back into stored kilometres', () => {
        expect(ebirdRadiusFromDisplayValue(16, 'imperial')).toBe(26);
    });

    it('holds steady across repeated edits so a saved radius never drifts', () => {
        const stored = ebirdRadiusFromDisplayValue(16, 'imperial');
        expect(stored).toBe(26);
        const redisplayed = ebirdRadiusToDisplayValue(stored as number, 'imperial');
        expect(redisplayed).toBe(16);
        expect(ebirdRadiusFromDisplayValue(redisplayed, 'imperial')).toBe(stored);
    });

    it('clamps to the range eBird accepts rather than sending a rejected request', () => {
        expect(ebirdRadiusFromDisplayValue(40, 'imperial')).toBe(EBIRD_RADIUS_MAX_KM);
        expect(ebirdRadiusFromDisplayValue(999, 'metric')).toBe(EBIRD_RADIUS_MAX_KM);
        expect(ebirdRadiusFromDisplayValue(0, 'imperial')).toBe(EBIRD_RADIUS_MIN_KM);
        expect(ebirdRadiusFromDisplayValue(-5, 'metric')).toBe(EBIRD_RADIUS_MIN_KM);
    });

    it('returns null for a cleared or unusable field instead of guessing', () => {
        expect(ebirdRadiusFromDisplayValue(Number.NaN, 'metric')).toBe(null);
        expect(ebirdRadiusFromDisplayValue(null, 'imperial')).toBe(null);
        expect(ebirdRadiusFromDisplayValue(undefined, 'metric')).toBe(null);
    });
});
