import { describe, expect, it } from 'vitest';

import diagnosticDialogSource from '../DiagnosticDialog.svelte?raw';
import advancedSectionSource from './_primitives/AdvancedSection.svelte?raw';
import detectionSettingsSource from './DetectionSettings.svelte?raw';

describe('Detection settings simplification', () => {
    it('keeps the default surface focused on active model, confidence, and exclusions', () => {
        const firstDisclosure = detectionSettingsSource.indexOf('<AdvancedSection');
        const defaultSurface = detectionSettingsSource.slice(0, firstDisclosure);

        expect(detectionSettingsSource.match(/<SettingsCard/g)).toHaveLength(2);
        expect(defaultSurface).toContain('classifierStatus.active_model_id');
        expect(defaultSurface).toContain('id="confidence-threshold-slider"');
        expect(defaultSurface).not.toContain('<ModelManager');
        expect(defaultSurface).not.toContain('id="min-confidence-slider"');
        expect(detectionSettingsSource).not.toContain('grid grid-cols-1 md:grid-cols-2');
    });

    it('progressively discloses model, fine-tuning, and hardware tasks', () => {
        expect(detectionSettingsSource).toContain('id="detection-classification-advanced"');
        expect(detectionSettingsSource).toContain('id="detection-fine-tuning-advanced"');
        expect(detectionSettingsSource).toContain('id="detection-inference-advanced"');

        const modelDisclosure = detectionSettingsSource.indexOf('id="detection-classification-advanced"');
        const modelManager = detectionSettingsSource.indexOf('<ModelManager');
        const fineTuningDisclosure = detectionSettingsSource.indexOf('id="detection-fine-tuning-advanced"');
        const minimumConfidence = detectionSettingsSource.indexOf('id="min-confidence-slider"');
        const hardwareDisclosure = detectionSettingsSource.indexOf('id="detection-inference-advanced"');
        const provider = detectionSettingsSource.indexOf('id="inference-provider"');
        const compatibilityCheck = detectionSettingsSource.indexOf('onclick={runCompatCheck}');

        expect(modelManager).toBeGreaterThan(modelDisclosure);
        expect(minimumConfidence).toBeGreaterThan(fineTuningDisclosure);
        expect(provider).toBeGreaterThan(hardwareDisclosure);
        expect(compatibilityCheck).toBeGreaterThan(hardwareDisclosure);
    });

    it('retains visible warnings and gold-standard interaction sizing', () => {
        expect(detectionSettingsSource).toContain('autoVideoClassification && videoCircuitOpen');
        expect(detectionSettingsSource).toContain('classifierStatus?.fallback_reason');
        expect(detectionSettingsSource).toContain('role="alert"');
        expect(detectionSettingsSource).toContain('h-11');
        expect(detectionSettingsSource).not.toMatch(/text-\[(9|10|11)px\]/);
        expect(detectionSettingsSource).not.toMatch(/icon="[🎯🎚️⚡🧪🚫]/u);
    });

    it('explains runtime image/provider mismatches without adding another card', () => {
        expect(detectionSettingsSource).toContain('classifierStatus.image_flavor');
        expect(detectionSettingsSource).toContain('classifierStatus.packaged_inference_providers');
        expect(detectionSettingsSource).toContain("classifierStatus.image_flavor_warning === 'selected_provider_not_packaged'");
        expect(detectionSettingsSource).toContain('settings.detection.image_flavor_mismatch');
        expect(detectionSettingsSource).toContain('docs/setup/hardware-acceleration.md');
        expect(detectionSettingsSource).toContain('role="alert"');
    });

    it('uses the live provider contract instead of advertising every runtime', () => {
        expect(detectionSettingsSource).toContain('buildInferenceProviderChoices');
        expect(detectionSettingsSource).toContain('getProviderPreferenceOrder');
        expect(detectionSettingsSource).toContain('providerPreferenceLabel');
        expect(detectionSettingsSource).toContain('configuredProviderUnavailable');
        expect(detectionSettingsSource).not.toContain("{ value: 'cuda', label:");
    });

    it('keeps shared disclosures semantic, readable, and keyboard visible', () => {
        expect(advancedSectionSource).toContain('aria-expanded={open}');
        expect(advancedSectionSource).toContain('aria-controls={contentId}');
        expect(advancedSectionSource).toContain('id={contentId}');
        expect(advancedSectionSource).toContain('min-h-11');
        expect(advancedSectionSource).toContain('focus-visible:ring-2');
        expect(advancedSectionSource).not.toContain('text-[9px]');
        expect(advancedSectionSource).not.toContain('<div class="flex items-center gap-2 min-w-0">');
    });

    it('keeps device compatibility warnings and skipped checks honest', () => {
        expect(detectionSettingsSource).toContain('<DiagnosticDialog');
        expect(detectionSettingsSource).toContain("state: 'warning'");
        expect(detectionSettingsSource).not.toContain("if (state === 'skipped') state = 'passed'");
        expect(detectionSettingsSource).toContain('ok: !failed && !warned && !skipped');
        expect(detectionSettingsSource).toContain('compat_results_unavailable');
        expect(detectionSettingsSource.match(/cdRunId \+= 1/g)).toHaveLength(3);
        expect(diagnosticDialogSource).toContain("s.state === 'skipped'");
        expect(diagnosticDialogSource).toContain("stage.state === 'warning'");
    });
});
