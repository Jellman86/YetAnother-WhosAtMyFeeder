import { describe, expect, it } from 'vitest';
import detectionSettingsSource from './DetectionSettings.svelte?raw';
import modelManagerSource from '../../pages/models/ModelManager.svelte?raw';
import settingsPageSource from '../../pages/Settings.svelte?raw';

describe('detection crop override wiring', () => {
    it('threads crop override bindings through the settings page into detection settings', () => {
        expect(settingsPageSource).toContain('cropModelOverrides');
        expect(settingsPageSource).toContain('cropSourceOverrides');
        expect(settingsPageSource).toContain('bind:cropModelOverrides');
        expect(settingsPageSource).toContain('bind:cropSourceOverrides');
        expect(settingsPageSource).toContain('buildCropOverrideSettings');
        expect(settingsPageSource).toContain('resolveCropOverridesFromSettings');
        expect(detectionSettingsSource).toContain('bind:cropModelOverrides');
        expect(detectionSettingsSource).toContain('bind:cropSourceOverrides');
    });

    it('renders crop override controls inside the model manager cards', () => {
        expect(modelManagerSource).toContain('Crop behavior');
        expect(modelManagerSource).toContain('Crop source');
        expect(modelManagerSource).toContain('getCropVariantOverrideEntries(model)');
        expect(modelManagerSource).toContain('high_quality');
    });
});
