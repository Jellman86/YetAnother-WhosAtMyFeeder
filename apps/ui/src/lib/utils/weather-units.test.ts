import { describe, expect, it } from 'vitest';

import {
    formatDistance,
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

describe('distance helpers', () => {
    it('keeps metric distances in kilometres', () => {
        expect(formatDistance(25, 'metric')).toBe('25 km');
    });

    it.each(['imperial', 'british'] as const satisfies ReadonlyArray<WeatherUnitSystem>)(
        'converts distances to miles for %s',
        system => {
            expect(formatDistance(25, system)).toBe('16 mi');
        }
    );

    it('keeps one decimal below ten so short radii stay honest', () => {
        expect(formatDistance(1, 'imperial')).toBe('0.6 mi');
        expect(formatDistance(1, 'metric')).toBe('1 km');
    });

    it('drops the decimal from ten upwards', () => {
        expect(formatDistance(16.09344, 'imperial')).toBe('10 mi');
    });

    it('returns an empty string for absent or unusable values', () => {
        expect(formatDistance(null, 'imperial')).toBe('');
        expect(formatDistance(undefined, 'metric')).toBe('');
        expect(formatDistance(Number.NaN, 'metric')).toBe('');
    });

    it('accepts caller-supplied unit labels for i18n', () => {
        expect(formatDistance(25, 'imperial', { metric: 'km', imperial: 'milles' })).toBe('16 milles');
    });
});
