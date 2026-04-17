import { describe, expect, it } from 'vitest';
import detectionSettingsSource from './DetectionSettings.svelte?raw';
import modelManagerSource from '../../pages/models/ModelManager.svelte?raw';
import settingsPageSource from '../../pages/Settings.svelte?raw';

describe('detection crop override wiring', () => {
    it('threads crop override bindings through the settings page into detection settings', () => {
        expect(settingsPageSource).toContain('birdCropDetectorTier');
        expect(settingsPageSource).toContain('bird_crop_detector_tier');
        expect(settingsPageSource).toContain('bind:birdCropDetectorTier');
        expect(settingsPageSource).toContain('cropModelOverrides');
        expect(settingsPageSource).toContain('cropSourceOverrides');
        expect(settingsPageSource).toContain('bind:cropModelOverrides');
        expect(settingsPageSource).toContain('bind:cropSourceOverrides');
        expect(settingsPageSource).toContain('buildCropOverrideSettings');
        expect(settingsPageSource).toContain('resolveCropOverridesFromSettings');
        expect(detectionSettingsSource).toContain('bird-crop-detector-tier');
        expect(detectionSettingsSource).toContain('Accurate (YOLOX-Tiny, experimental)');
        expect(detectionSettingsSource).toContain('bind:value={birdCropDetectorTier}');
        expect(detectionSettingsSource).toContain('bind:cropModelOverrides');
        expect(detectionSettingsSource).toContain('bind:cropSourceOverrides');
    });

    it('renders crop override controls inside the model manager cards', () => {
        expect(modelManagerSource).toContain('Crop behavior');
        expect(modelManagerSource).toContain('Crop source');
        expect(modelManagerSource).toContain('getCropVariantOverrideEntries(model)');
        expect(modelManagerSource).toContain('high_quality');
    });

    it('renders managed crop detector status alongside gated crop controls', () => {
        expect(modelManagerSource).toContain("artifact_kind || 'classifier') === 'crop_detector'");
        expect(modelManagerSource).toContain('cropDetectorModels');
        expect(modelManagerSource).toContain('cropDetectorStatus');
        expect(modelManagerSource).toContain('Download detector');
        expect(modelManagerSource).toContain('require at least one installed bird crop detector');
    });
});
