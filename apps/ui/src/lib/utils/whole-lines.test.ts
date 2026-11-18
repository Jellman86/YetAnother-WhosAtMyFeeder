import { describe, expect, it } from 'vitest';
import { wholeLinesHeight } from './whole-lines';

/** Where each line of the status readings ends, from the top of the readings, in px. */
const LINES = [16, 40, 64, 88, 106];

describe('wholeLinesHeight', () => {
    it('leaves the height alone when every line fits', () => {
        expect(wholeLinesHeight(LINES, 106)).toBeNull();
        expect(wholeLinesHeight(LINES, 120)).toBeNull();
    });

    it('ends the visible height at the last line that fits whole, so no line shows in part', () => {
        // 101px would show 13px of the last 18px line; it ends after the line before it instead.
        expect(wholeLinesHeight(LINES, 101)).toBe(88);
        expect(wholeLinesHeight(LINES, 88)).toBe(88);
        expect(wholeLinesHeight(LINES, 70)).toBe(64);
    });

    it('takes line ends in any order, and a sub-pixel overhang does not count as a line that does not fit', () => {
        expect(wholeLinesHeight([88.4, 16, 64, 40], 88)).toBeNull();
        expect(wholeLinesHeight([106.6, 16, 40, 64, 88], 106)).toBeNull();
    });

    it('keeps at least the first line, even in a space too small for it', () => {
        expect(wholeLinesHeight(LINES, 10)).toBe(16);
    });
});
