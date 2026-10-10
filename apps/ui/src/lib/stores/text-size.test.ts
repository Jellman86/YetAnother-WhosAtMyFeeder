import { describe, expect, it } from 'vitest';
import { normalizeTextSize, TEXT_SIZE_SCALE } from './theme.svelte';

describe('the reader’s text size', () => {
    it('steps up from smaller to largest, with standard leaving the page as designed', () => {
        const steps = Object.values(TEXT_SIZE_SCALE);
        expect(steps).toEqual([...steps].sort((a, b) => a - b));
        expect(TEXT_SIZE_SCALE.standard).toBe(1);
    });

    it('falls back to standard for anything a browser might have stored', () => {
        expect(normalizeTextSize('larger')).toBe('larger');
        expect(normalizeTextSize(null)).toBe('standard');
        expect(normalizeTextSize('huge')).toBe('standard');
        expect(normalizeTextSize('toString')).toBe('standard');
    });
});
