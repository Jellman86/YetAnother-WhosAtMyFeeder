import { describe, expect, it } from 'vitest';
import { gardenThresholdPercentStep, percentToThreshold, thresholdPercentText } from './garden-threshold';

describe('Garden threshold number-control precision, in percent', () => {
    it.each([0.5, 0.63, 0.95])('steps one percentage point for %s', value => {
        expect(gardenThresholdPercentStep(value)).toBe(1);
    });

    it.each([[0.625, 0.1], [0.6385722, 0.00001]])('preserves the precision of %s', (value, step) => {
        expect(gardenThresholdPercentStep(value)).toBeCloseTo(step, 12);
    });

    it.each([undefined, Number.NaN, Number.POSITIVE_INFINITY, 0.2, 1])('keeps a usable step for an invalid or empty edit: %s', value => {
        expect(gardenThresholdPercentStep(value)).toBe(1);
    });

    it('keeps a saved finer increment when stepping through a trailing zero', () => {
        expect(gardenThresholdPercentStep(0.63, 0.625)).toBe(0.1);
    });
});

describe('showing a 0 to 1 threshold as a percentage', () => {
    it.each([[0.5, '50'], [0.63, '63'], [0.625, '62.5'], [0.6385722, '63.85722'], [0.8, '80'], [0.99, '99']])('shows %s as %s', (value, text) => {
        expect(thresholdPercentText(value)).toBe(text);
    });

    it('shows nothing for a value that is not a number, so a half-typed entry is not overwritten', () => {
        expect(thresholdPercentText(Number.NaN)).toBe('');
    });

    it.each([['64', 0.64], ['62.6', 0.626], ['63.85722', 0.6385722], ['95', 0.95], ['70', 0.7]])('saves %s%% as exactly %s', (text, value) => {
        expect(percentToThreshold(text)).toBe(value);
    });

    it.each(['', '  ', 'abc'])('treats %j as no value, which the save check reports', text => {
        expect(percentToThreshold(text)).toBeNaN();
    });
});
