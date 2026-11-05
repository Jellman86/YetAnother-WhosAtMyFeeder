import { afterEach, describe, expect, it } from 'vitest';
import type { Settings } from '../api';
import { authStore } from '../stores/auth.svelte';
import { settingsStore } from '../stores/settings.svelte';
import { displayDistance } from './display-distance.svelte';

const translate = (_id: string, options: { default: string }): string => options.default;

describe('display distance', () => {
    afterEach(() => {
        settingsStore.settings = null;
        authStore.locationWeatherUnitSystem = 'metric';
    });

    it('keeps kilometres for metric owners', () => {
        settingsStore.settings = { location_weather_unit_system: 'metric' } as Settings;
        expect(displayDistance(50, translate)).toBe('50 km');
    });

    it('shows miles when the owner chose Imperial (#911)', () => {
        settingsStore.settings = { location_weather_unit_system: 'imperial' } as Settings;
        expect(displayDistance(50, translate)).toBe('31 mi');
    });

    it('shows miles for British units, which measure distance in miles', () => {
        settingsStore.settings = { location_weather_unit_system: 'british' } as Settings;
        expect(displayDistance(25, translate)).toBe('16 mi');
    });

    it('follows the public unit choice when no owner settings are loaded', () => {
        authStore.locationWeatherUnitSystem = 'imperial';
        expect(displayDistance(5, translate)).toBe('3.1 mi');
    });
});
