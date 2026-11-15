import { describe, expect, it } from 'vitest';
import { thresholdPercentText } from './garden-threshold';

describe('showing a 0 to 1 threshold as a percentage', () => {
    it.each([[0.5, '50'], [0.63, '63'], [0.625, '62.5'], [0.6385722, '63.85722'], [0.8, '80'], [0.99, '99']])('shows %s as %s', (value, text) => {
        expect(thresholdPercentText(value)).toBe(text);
    });

    it('shows nothing for a value that is not a number, so a half-typed entry is not overwritten', () => {
        expect(thresholdPercentText(Number.NaN)).toBe('');
    });
});
