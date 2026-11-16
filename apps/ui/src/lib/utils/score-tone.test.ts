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

    it('takes amber for a person, the brand for normal and green for confirmed, never the theme accent', () => {
        expect(SCORE_TEXT).toEqual({ low: 'text-status-attention', mid: 'text-status-info', high: 'text-status-ok' });
        expect(SCORE_FILL).toEqual({ low: 'bg-status-attention-line', mid: 'bg-status-info-line', high: 'bg-status-ok-line' });
        // Over a photograph the ground is always dark, so the light steps are fixed there.
        expect(SCORE_TEXT_ON_MEDIA.low).toMatch(/attention-/);
        expect(SCORE_TEXT_ON_MEDIA.mid).toMatch(/brand-/);
        expect(SCORE_TEXT_ON_MEDIA.high).toMatch(/success-/);
        for (const map of [SCORE_TEXT, SCORE_TEXT_ON_MEDIA, SCORE_FILL]) {
            for (const band of bands) expect(map[band]).not.toMatch(/emerald-|amber-|red-|dark:/);
        }
    });

    it('sets small text at AA in every mode, through the status inks the contrast proof covers', () => {
        // design-tokens.contrast.test.ts holds each status ink to 4.5:1 on every ground (7:1 in high contrast).
        for (const band of bands) expect(SCORE_TEXT[band]).toMatch(/^text-status-(?:attention|info|ok)$/);
    });
});
