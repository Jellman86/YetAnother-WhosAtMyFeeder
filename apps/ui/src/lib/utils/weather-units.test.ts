import { describe, expect, it } from 'vitest';

import {
    formatPrecipitation,
    formatWindSpeed,
    getTemperatureUnitForSystem,
    type WeatherUnitSystem
} from './weather-units';

describe('weather units helpers', () => {
    it('formats wind speed in metric units from stored km/h values', () => {
        expect(formatWindSpeed(12.4, 'metric')).toBe('12 km/h');
    });

    it('formats wind speed in imperial units from stored km/h values', () => {
        expect(formatWindSpeed(16.09344, 'imperial')).toBe('10 mph');
    });

    it('formats wind speed in british units from stored km/h values', () => {
        expect(formatWindSpeed(16.09344, 'british')).toBe('10 mph');
    });

    it('formats precipitation in metric units from stored millimetres', () => {
        expect(formatPrecipitation(0.45, 'metric')).toBe('0.5mm');
    });

    it('formats precipitation in imperial units from stored millimetres', () => {
        expect(formatPrecipitation(25.4, 'imperial')).toBe('1.0in');
    });

    it('formats precipitation in british units from stored millimetres', () => {
        expect(formatPrecipitation(25.4, 'british')).toBe('25mm');
    });

    it.each([
        ['metric', 'celsius'],
        ['imperial', 'fahrenheit'],
        ['british', 'celsius']
    ] as const satisfies ReadonlyArray<readonly [WeatherUnitSystem, 'celsius' | 'fahrenheit']>)(
        'maps %s to the correct temperature unit',
        (system, expected) => {
            expect(getTemperatureUnitForSystem(system)).toBe(expected);
        }
    );
});
