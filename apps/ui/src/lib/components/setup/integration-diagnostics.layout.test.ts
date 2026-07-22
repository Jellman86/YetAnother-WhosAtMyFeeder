import { describe, expect, it } from 'vitest';
import setupIntegrationSource from './IntegrationsStep.svelte?raw';
import integrationSettingsSource from '../settings/IntegrationSettings.svelte?raw';
import connectionSettingsSource from '../settings/ConnectionSettings.svelte?raw';

describe('setup and settings diagnostics use current values honestly', () => {
    it('uses the shared staged dialog for the setup BirdNET-Go diagnostic', () => {
        expect(setupIntegrationSource).toContain('<DiagnosticDialog');
        expect(setupIntegrationSource).toContain('runSequentialDiagnostic');
        expect(setupIntegrationSource).toContain('checkBirdNetReachability(birdnetUrl.trim())');
        expect(setupIntegrationSource).toContain('testMQTTPublish');
        expect(setupIntegrationSource).toContain('testBirdNET');
    });

    it('allows a saved BirdWeather token to be tested without re-entering it', () => {
        expect(integrationSettingsSource).toContain('!birdweatherStationToken && !birdweatherStationTokenSaved');
        expect(integrationSettingsSource).toContain('testBirdWeather(birdweatherStationToken || undefined)');
    });

    it('tests edited BirdNET-Go and connection values instead of stale saved values', () => {
        expect(integrationSettingsSource).toContain('checkBirdNetReachability(birdnetUrl.trim())');
        expect(connectionSettingsSource).toContain('testFrigateConnection(frigateUrl.trim())');
        expect(connectionSettingsSource).toContain('testMQTTPublish({');
    });

    it('saves iNaturalist credentials before starting OAuth and opens the popup synchronously', () => {
        expect(integrationSettingsSource).toContain('prepareInaturalistOAuth');
        expect(integrationSettingsSource).toContain("window.open('', 'yawamf-inaturalist-oauth'");
        expect(integrationSettingsSource.indexOf("window.open('', 'yawamf-inaturalist-oauth'")).toBeLessThan(
            integrationSettingsSource.indexOf('await prepareInaturalistOAuth()')
        );
    });
});
