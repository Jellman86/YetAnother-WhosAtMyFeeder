import { describe, expect, it } from 'vitest';
import detectionSettingsSource from './DetectionSettings.svelte?raw';
import modelManagerSource from '../../pages/models/ModelManager.svelte?raw';
import settingsPageSource from '../../pages/Settings.svelte?raw';

describe('automatic model crop policy', () => {
    it('keeps compatibility fields out of the settings UI state and controls', () => {
        expect(settingsPageSource).not.toContain('birdCropDetectorTier');
        expect(settingsPageSource).not.toContain('bird_crop_detector_tier');
        expect(settingsPageSource).not.toContain('birdCropSourcePriority');
        expect(settingsPageSource).not.toContain('bird_crop_source_priority');
        expect(settingsPageSource).not.toContain('cropModelOverrides');
        expect(settingsPageSource).not.toContain('cropSourceOverrides');
        expect(settingsPageSource).not.toContain('buildCropOverrideSettings');
        expect(settingsPageSource).not.toContain('resolveCropOverridesFromSettings');
        expect(detectionSettingsSource).not.toContain('birdCropDetectorTier');
        expect(detectionSettingsSource).not.toContain('id="bird-crop-source-priority"');
        expect(detectionSettingsSource).not.toContain('cropModelOverrides');
        expect(detectionSettingsSource).not.toContain('cropSourceOverrides');
        expect(modelManagerSource).not.toContain('birdCropDetectorTier');
    });

    it('explains the automatic policy without exposing implementation switches', () => {
        expect(modelManagerSource).toContain('model_manager_crop_policy_automatic');
        expect(modelManagerSource).not.toContain('CROP_MODEL_OVERRIDE_VALUES');
        expect(modelManagerSource).not.toContain('CROP_SOURCE_OVERRIDE_VALUES');
        expect(modelManagerSource).not.toContain('getCropVariantOverrideEntries(model)');
        expect(modelManagerSource).not.toContain('Force on');
        expect(modelManagerSource).not.toContain('Force off');
    });

    it('separates classifier preparation from cropped-thumbnail generation', () => {
        expect(modelManagerSource).toContain("artifact_kind || 'classifier') === 'crop_detector'");
        expect(modelManagerSource).toContain('cropDetectorModels');
        expect(modelManagerSource).toContain('cropDetectorStatus');
        expect(modelManagerSource).toContain('model_manager_thumbnail_crop_title');
        expect(modelManagerSource).toContain('Automatic best quality');
        expect(modelManagerSource).not.toContain('id="thumbnail-crop-quality"');
        expect(modelManagerSource).not.toContain('value="fast"');
        expect(modelManagerSource).not.toContain('value="accurate"');
        expect(modelManagerSource).not.toContain('model_manager_image_preparation');
        expect(modelManagerSource).toContain('model_manager_technical_details');
    });
});
