import { describe, expect, it } from 'vitest';
import { SCORE_FILL, SCORE_TEXT, SCORE_TEXT_ON_MEDIA, scoreBand, type ScoreBand } from './score-tone';

/**
 * layout-patterns.md §6: a score is a percentage in a tone band, under 60 amber,
 * under 85 brand, and green from 85. Cards, the list, the record and the field log
 * all read these bands, so one score is one colour wherever it appears (EXP-02).
 */
describe('scoreBand', () => {
    it('puts a score under 60% in the band that needs a person', () => {
        expect(scoreBand(0)).toBe('low');
        expect(scoreBand(0.59)).toBe('low');
    });

    it('starts the brand band at exactly 60%', () => {
        expect(scoreBand(0.6)).toBe('mid');
        expect(scoreBand(0.84)).toBe('mid');
    });

    it('starts the confirmed band at exactly 85%', () => {
        expect(scoreBand(0.85)).toBe('high');
        expect(scoreBand(1)).toBe('high');
    });

    it('bands the percentage a person reads, so the number and its colour agree', () => {
        // 0.596 prints as 60%; colouring it as under 60 would contradict the figure beside it.
        expect(scoreBand(0.596)).toBe('mid');
        expect(scoreBand(0.594)).toBe('low');
        expect(scoreBand(0.846)).toBe('high');
    });

    it('treats a missing or unreadable score as the lowest band rather than inventing confidence', () => {
        expect(scoreBand(null)).toBe('low');
        expect(scoreBand(undefined)).toBe('low');
        expect(scoreBand(Number.NaN)).toBe('low');
    });
});

describe('score tone classes', () => {
    const bands: ScoreBand[] = ['low', 'mid', 'high'];

    it('uses only the attention, brand and success scales, never the theme accent', () => {
        for (const map of [SCORE_TEXT, SCORE_TEXT_ON_MEDIA, SCORE_FILL]) {
            for (const band of bands) expect(map[band]).not.toMatch(/accent-|emerald-|amber-|red-/);
            expect(map.low).toMatch(/attention-/);
            expect(map.mid).toMatch(/brand-/);
            expect(map.high).toMatch(/success-/);
        }
    });

    it('sets small text dark enough for AA on light ground and light enough on dark ground', () => {
        expect(SCORE_TEXT.low).toBe('text-attention-800 dark:text-attention-300');
        expect(SCORE_TEXT.mid).toBe('text-brand-700 dark:text-brand-300');
        expect(SCORE_TEXT.high).toBe('text-success-700 dark:text-success-300');
    });
});
