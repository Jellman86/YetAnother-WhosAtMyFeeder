import { describe, expect, it } from 'vitest';
import modalSource from './DetectionModal.svelte?raw';

describe('the weather is stated once in the event overview (#268)', () => {
    // Condition and temperature used to appear in the facts list, again in a
    // weather section header, and a third time inside a disclosure that hid
    // four numbers. One condensed facts row now carries every measured value.

    it('one row states every measured fact, unknowns omitted', () => {
        expect(modalSource).toContain('data-detection-weather-row');
        expect(modalSource).toContain('const weatherSummary');
        expect(modalSource).toContain("parts.join(' · ')");
    });

    it('the duplicating section and its disclosure are gone', () => {
        expect(modalSource).not.toContain('data-detection-weather-section');
        expect(modalSource).not.toContain('weatherDetailsOpen');
        expect(modalSource).not.toContain('detection.weather_breakdown');
    });
});
