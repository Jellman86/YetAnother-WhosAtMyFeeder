import { describe, expect, it } from 'vitest';
import { retentionShrinks } from './retention-change';

describe('retentionShrinks', () => {
    it('is true when a shorter window replaces a longer one', () => {
        expect(retentionShrinks(30, 7)).toBe(true);
    });

    it('is true when any window replaces keep everything', () => {
        expect(retentionShrinks(0, 365)).toBe(true);
    });

    it('is false for the same or a longer window', () => {
        expect(retentionShrinks(30, 30)).toBe(false);
        expect(retentionShrinks(7, 30)).toBe(false);
    });

    it('is false when moving to keep everything', () => {
        expect(retentionShrinks(7, 0)).toBe(false);
        expect(retentionShrinks(0, 0)).toBe(false);
    });
});
