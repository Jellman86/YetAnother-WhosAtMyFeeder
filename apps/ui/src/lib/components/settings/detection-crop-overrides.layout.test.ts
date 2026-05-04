import { describe, expect, it } from 'vitest';
import detectionSettingsSource from './DetectionSettings.svelte?raw';
import modelManagerSource from '../../pages/models/ModelManager.svelte?raw';
import settingsPageSource from '../../pages/Settings.svelte?raw';

describe('detection crop override wiring', () => {
    it('threads crop override bindings through the settings page into detection settings', () => {
        expect(settingsPageSource).toContain('birdCropDetectorTier');
        expect(settingsPageSource).toContain('bird_crop_detector_tier');
        expect(settingsPageSource).toContain('bind:birdCropDetectorTier');
        expect(settingsPageSource).toContain('birdCropSourcePriority');
        expect(settingsPageSource).toContain('bird_crop_source_priority');
        expect(settingsPageSource).toContain('bind:birdCropSourcePriority');
        expect(settingsPageSource).toContain('cropModelOverrides');
        expect(settingsPageSource).toContain('cropSourceOverrides');
        expect(settingsPageSource).toContain('bind:cropModelOverrides');
        expect(settingsPageSource).toContain('bind:cropSourceOverrides');
        expect(settingsPageSource).toContain('buildCropOverrideSettings');
        expect(settingsPageSource).toContain('resolveCropOverridesFromSettings');
        // The crop-detector tier picker now lives inside ModelManager rendered
        // as the same prominent dropdown used for the main classifier model
        // lineup, so DetectionSettings only forwards the binding. The crop
        // source-priority control still lives in DetectionSettings' Advanced
        // overflow.
        expect(detectionSettingsSource).toContain('bind:birdCropDetectorTier');
        expect(detectionSettingsSource).toContain('id="bird-crop-source-priority"');
        expect(detectionSettingsSource).toContain('value={birdCropSourcePriority}');
        expect(detectionSettingsSource).toContain('birdCropSourcePriority = v');
        expect(detectionSettingsSource).toContain('Frigate hints first');
        expect(detectionSettingsSource).toContain('bind:cropModelOverrides');
        expect(detectionSettingsSource).toContain('bind:cropSourceOverrides');
        // ModelManager owns the tier picker now.
        expect(modelManagerSource).toContain('birdCropDetectorTier');
        expect(modelManagerSource).toContain('Accurate');
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
