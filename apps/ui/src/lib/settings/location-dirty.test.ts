import { describe, expect, it } from 'vitest';

import { locationChangedFields } from './location-dirty';

describe('locationChangedFields', () => {
    it('detects state changes', () => {
        expect(
            locationChangedFields({
                current: {
                    latitude: 51.5,
                    longitude: -0.12,
                    state: 'California',
                    country: 'United States',
                    automatic: false,
                    weatherUnitSystem: 'metric'
                },
                stored: {
                    location_latitude: 51.5,
                    location_longitude: -0.12,
                    location_state: 'Nevada',
                    location_country: 'United States',
                    location_automatic: false,
                    location_weather_unit_system: 'metric'
                }
            })
        ).not.toEqual([]);
    });

    it('detects country changes', () => {
        expect(
            locationChangedFields({
                current: {
                    latitude: 51.5,
                    longitude: -0.12,
                    state: 'California',
                    country: 'Canada',
                    automatic: false,
                    weatherUnitSystem: 'metric'
                },
                stored: {
                    location_latitude: 51.5,
                    location_longitude: -0.12,
                    location_state: 'California',
                    location_country: 'United States',
                    location_automatic: false,
                    location_weather_unit_system: 'metric'
                }
            })
        ).not.toEqual([]);
    });

    it('does not mark unchanged location settings as dirty', () => {
        expect(
            locationChangedFields({
                current: {
                    latitude: 51.5,
                    longitude: -0.12,
                    state: 'California',
                    country: 'United States',
                    automatic: false,
                    weatherUnitSystem: 'metric'
                },
                stored: {
                    location_latitude: 51.5,
                    location_longitude: -0.12,
                    location_state: 'California',
                    location_country: 'United States',
                    location_automatic: false,
                    location_weather_unit_system: 'metric'
                }
            })
        ).toEqual([]);
    });
});
