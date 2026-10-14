import { describe, expect, it } from 'vitest';
import { gardenThresholdStep } from './garden-threshold';

describe('Garden threshold number-control precision', () => {
    it.each([0.5, 0.63, 0.95])('uses one percentage point for %s', value => {
        expect(gardenThresholdStep(value)).toBe(0.01);
    });

    it.each([[0.625, 0.001], [0.6385722, 0.0000001]])('preserves the precision of %s', (value, step) => {
        expect(gardenThresholdStep(value)).toBeCloseTo(step, 12);
    });

    it.each([undefined, Number.NaN, Number.POSITIVE_INFINITY, 0.2, 1])('keeps a usable step for an invalid or empty edit: %s', value => {
        expect(gardenThresholdStep(value)).toBe(0.01);
    });
});

it('keeps a saved finer increment when stepping through a trailing zero', () => {
    expect(gardenThresholdStep(0.63, 0.625)).toBe(0.001);
});
