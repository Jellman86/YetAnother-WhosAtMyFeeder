import { describe, expect, it } from 'vitest';
import { compassPointKey, weatherConditionMessage } from './weather-condition';

describe('a stored weather condition', () => {
    it('maps every condition the backend writes to a translatable message, whatever its casing', () => {
        const written = ['Clear sky', 'Partly cloudy', 'Foggy', 'Drizzle', 'Rain', 'Snow', 'Rain showers', 'Thunderstorm', 'Cloudy', 'Hail', 'Windy', 'Exceptional'];
        for (const condition of written) {
            const message = weatherConditionMessage(condition);
            expect(message?.key, condition).toMatch(/^common\.weather_condition\.[a-z_]+$/);
            expect(message?.default).toBe(condition);
            expect(weatherConditionMessage(condition.toLowerCase())?.key).toBe(message?.key);
        }
    });

    it('prints a condition it does not know as it was stored, and nothing for none or an unknown', () => {
        expect(weatherConditionMessage('Sleet')).toEqual({ key: null, default: 'Sleet' });
        expect(weatherConditionMessage('clear')?.key).toBe('common.weather_condition.clear_sky');
        expect(weatherConditionMessage('')).toBeNull();
        expect(weatherConditionMessage(null)).toBeNull();
        expect(weatherConditionMessage('Unknown')).toBeNull();
    });
});

describe('a wind direction', () => {
    it('names the nearest of eight compass points', () => {
        expect([0, 44, 90, 135, 180, 225, 270, 315, 359].map(compassPointKey)).toEqual(['n', 'ne', 'e', 'se', 's', 'sw', 'w', 'nw', 'n']);
        expect(compassPointKey(-45)).toBe('nw');
        expect(compassPointKey(null)).toBeNull();
        expect(compassPointKey(Number.NaN)).toBeNull();
    });
});
