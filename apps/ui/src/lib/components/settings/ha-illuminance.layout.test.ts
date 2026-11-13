import { describe, expect, it } from 'vitest';
import integrationSource from './IntegrationSettings.svelte?raw';
import settingsPageSource from '../../pages/Settings.svelte?raw';
import modalSource from '../DetectionModal.svelte?raw';
import maintenanceSource from '../../api/maintenance.ts?raw';
import visitsSource from '../../api/visits.ts?raw';
import liveUpdatesSource from '../../app/live-updates.ts?raw';

describe('a Home Assistant light sensor is recorded with each detection (#945)', () => {
    // The lux sensor is its own reading, not a weather override: it sits beside
    // the weather entity, outside the overrides disclosure, and is optional.

    it('the card offers an optional illuminance entity beside the weather entity', () => {
        const field = integrationSource.indexOf('id="ha-weather-illuminance"');
        const weatherEntity = integrationSource.indexOf('id="ha-weather-entity"');
        const overrides = integrationSource.indexOf("settings.integrations.ha_weather.overrides'");
        expect(field).toBeGreaterThan(weatherEntity);
        expect(field).toBeLessThan(overrides);
        expect(integrationSource).toContain('labelId="setting-ha-weather-illuminance"');
        expect(integrationSource).toContain('settings.integrations.ha_weather.illuminance_desc');
    });

    it('a value that is not an entity id is named beside the field, not by colour alone', () => {
        expect(integrationSource).toContain('isHomeAssistantEntityId(haWeatherIlluminanceEntity)');
        expect(integrationSource).toContain('id="ha-weather-illuminance-error"');
        expect(integrationSource).toContain('settings.integrations.ha_weather.illuminance_invalid');
        expect(integrationSource).toContain('invalid={illuminanceEntityInvalid}');
    });

    it('the live test reads the field as typed, in its own stage of the shared dialog', () => {
        expect(integrationSource).toContain("id: 'illuminance'");
        expect(integrationSource).toContain("scope: 'illuminance'");
        expect(integrationSource).toContain('illuminanceEntity: haWeatherIlluminanceEntity.trim()');
        expect(integrationSource).toContain('illuminanceStepOutcome(');
        expect(integrationSource).toContain('runSequentialDiagnostic');
        expect(maintenanceSource).toContain('illuminance_entity: options.illuminanceEntity || undefined');
    });

    it('every reason a reading can be missing has its own sentence', () => {
        for (const reason of ['invalid_entity_id', 'unreachable', 'not_illuminance', 'unavailable', 'not_numeric', 'out_of_range']) {
            expect(integrationSource).toContain(`settings.integrations.ha_weather.illuminance_${reason}`);
        }
    });

    it('the settings page loads, saves and tracks the field', () => {
        expect(settingsPageSource).toContain("haWeatherIlluminanceEntity = settings.ha_weather_illuminance_entity ?? ''");
        expect(settingsPageSource).toContain('ha_weather_illuminance_entity: haWeatherIlluminanceEntity.trim() || null');
        expect(settingsPageSource).toContain("store: s.ha_weather_illuminance_entity ?? ''");
        expect(settingsPageSource).toContain('bind:haWeatherIlluminanceEntity');
    });

    it('the record states the stored light level in its one conditions row', () => {
        expect(modalSource).toContain('formatIlluminance(detection.illuminance_lux)');
        expect(modalSource).toContain("$_('detection.weather_light'");
        expect(visitsSource).toContain('illuminance_lux: data.illuminance_lux ?? undefined');
        expect(liveUpdatesSource).toContain('illuminance_lux: data.illuminance_lux');
    });
});
