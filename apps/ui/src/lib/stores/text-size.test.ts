import { describe, expect, it } from 'vitest';
import { normalizeTextSize, TEXT_SIZE_SCALE } from './theme.svelte';

describe('the reader’s text size', () => {
    it('steps up from smallest to largest, with two sizes below standard', () => {
        const steps = Object.values(TEXT_SIZE_SCALE);
        expect(steps).toEqual([...steps].sort((a, b) => a - b));
        expect(Object.keys(TEXT_SIZE_SCALE).indexOf('standard')).toBe(2);
    });

    it('reads standard a step under the browser size, and gives it back at large', () => {
        expect(TEXT_SIZE_SCALE.standard).toBe(0.875);
        expect(TEXT_SIZE_SCALE.large).toBe(1);
    });

    it('falls back to standard for anything a browser might have stored', () => {
        expect(normalizeTextSize('larger')).toBe('larger');
        expect(normalizeTextSize(null)).toBe('standard');
        expect(normalizeTextSize('huge')).toBe('standard');
        expect(normalizeTextSize('toString')).toBe('standard');
    });
});
