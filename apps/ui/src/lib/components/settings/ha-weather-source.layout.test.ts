import { describe, expect, it } from 'vitest';
import integrationSource from './IntegrationSettings.svelte?raw';
import settingsPageSource from '../../pages/Settings.svelte?raw';

describe('weather from Home Assistant sensors (#277)', () => {
    // A sensor a few metres from the feeder beats a regional forecast. The
    // integration card carries the URL the server can reach, a token that is
    // stored as a secret, the weather entity as the general source, and one
    // override per reading behind progressive disclosure.

    it('the card offers URL, secret token, entity, and per-reading overrides', () => {
        expect(integrationSource).toContain('setting-ha-weather-enabled');
        expect(integrationSource).toContain('setting-ha-weather-url');
        expect(integrationSource).toContain('id="ha-weather-token"');
        expect(integrationSource).toContain('setting-ha-weather-entity');
        expect(integrationSource).toContain('settings.integrations.ha_weather.overrides');
        for (const override of ['temperature', 'wind-speed', 'wind-direction', 'cloud-cover', 'precipitation', 'rain', 'snowfall']) {
            expect(integrationSource).toContain(`'setting-ha-weather-' + override.id`);
            expect(integrationSource).toContain(`id: '${override}'`);
        }
    });

    it('the token behaves like every other stored secret', () => {
        expect(integrationSource).toContain('saved={haWeatherAccessTokenSaved}');
        expect(settingsPageSource).toContain("normalizeSecret(s.ha_weather_access_token)");
        expect(settingsPageSource).toContain("settings.ha_weather_access_token === '***REDACTED***'");
    });

    it('the test flow uses the shared diagnostic dialog, not a hand-rolled modal', () => {
        expect(integrationSource).toContain('runHaWeatherDiagnostic');
        expect(integrationSource).toContain('testHaWeather({');
        const dialogAt = integrationSource.indexOf('{#if hawTestOpen}');
        expect(dialogAt).toBeGreaterThan(-1);
        expect(integrationSource.slice(dialogAt)).toContain('<DiagnosticDialog');
    });

    it('the settings page saves and loads every field', () => {
        expect(settingsPageSource).toContain('ha_weather_enabled: haWeatherEnabled');
        expect(settingsPageSource).toContain('ha_weather_snowfall_entity: haWeatherSnowfallEntity || null');
        expect(settingsPageSource).toContain("haWeatherEntity = settings.ha_weather_entity ?? ''");
        expect(settingsPageSource).toContain('bind:haWeatherSnowfallEntity');
    });
});
