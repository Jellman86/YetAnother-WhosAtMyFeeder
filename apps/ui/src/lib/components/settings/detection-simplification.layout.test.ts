import { describe, expect, it } from 'vitest';

import diagnosticDialogSource from '../DiagnosticDialog.svelte?raw';
import advancedSectionSource from './_primitives/AdvancedSection.svelte?raw';
import detectionSettingsSource from './DetectionSettings.svelte?raw';
import statusBandSource from './DetectionStatusBand.svelte?raw';
import modelManagerSource from '../../pages/models/ModelManager.svelte?raw';

describe('Detection settings, status first', () => {
    it('opens with the status band: model, runtime, workers, health', () => {
        const band = detectionSettingsSource.indexOf('<DetectionStatusBand');
        const grid = detectionSettingsSource.indexOf('grid grid-cols-1 gap-6 lg:grid-cols-2');
        expect(band).toBeGreaterThan(-1);
        expect(grid).toBeGreaterThan(band);
        expect(statusBandSource).toContain('band_model');
        expect(statusBandSource).toContain('band_runtime');
        expect(statusBandSource).toContain('band_workers');
        expect(statusBandSource).toContain('band_health');
        // Healthy is calm facts; only trouble grows words.
        expect(statusBandSource).toContain('band_all_good');
        expect(statusBandSource).toContain('band_needs_attention');
        expect(statusBandSource).toContain('role="status"');
    });

    it('counts real problems into the health cell and opens the report on trouble', () => {
        expect(detectionSettingsSource).toContain('const healthIssueCount = $derived(');
        expect(detectionSettingsSource).toContain('classifierStatus?.fallback_reason ? 1 : 0');
        expect(detectionSettingsSource).toContain('autoVideoClassification && videoCircuitOpen ? 1 : 0');
        expect(detectionSettingsSource).toContain('openByDefault={healthIssueCount > 0}');
        expect(statusBandSource).toContain('scrollIntoView');
    });

    it('surfaces both thresholds and the runtime choices without a disclosure', () => {
        const report = detectionSettingsSource.indexOf('id="detection-inference-advanced"');
        for (const id of [
            'id="confidence-threshold-slider"',
            'id="min-confidence-slider"',
            'id="inference-provider"',
            'id="image-execution-mode"',
            'id="bird-model-region-override"',
            'onclick={runCompatCheck}',
        ]) {
            const at = detectionSettingsSource.indexOf(id);
            expect(at, id).toBeGreaterThan(-1);
            expect(at, `${id} must sit on the default surface, before the runtime report`).toBeLessThan(report);
        }
        expect(detectionSettingsSource).not.toContain('id="detection-fine-tuning-advanced"');
        expect(detectionSettingsSource).not.toContain('id="detection-classification-advanced"');
    });

    it('gives models their own card instead of a disclosure', () => {
        expect(detectionSettingsSource.match(/<SettingsCard/g)).toHaveLength(3);
        expect(detectionSettingsSource).toContain('models_card_title');
        const modelsCard = detectionSettingsSource.indexOf('id={MODELS_CARD_ID}');
        const modelManager = detectionSettingsSource.indexOf('<ModelManager');
        expect(modelManager).toBeGreaterThan(modelsCard);
    });

    it('picks the model from cards with one honest state chip, not a select', () => {
        expect(modelManagerSource).not.toContain('<select id="classifier-model-select"');
        expect(modelManagerSource).toContain('aria-pressed={cardSelected}');
        expect(modelManagerSource).toContain('modelCardState(modelOption.id)');
        for (const state of ['model_manager_state_repair', 'model_manager_state_installed', 'model_manager_state_available']) {
            expect(modelManagerSource).toContain(state);
        }
        // Each card carries the honest costs: download size and a RAM meter
        // drawn against the heaviest model in the lineup.
        expect(modelManagerSource).toContain('model-ram-meter');
        expect(modelManagerSource).toContain('ramShortLabel(modelOption.estimated_ram_mb)');
        expect(modelManagerSource).toContain('lineupMaxRam(classifierModels)');
        // The selected card's aurora is decorative, GPU-composited, and stilled
        // for reduced motion.
        expect(modelManagerSource).toContain('model-card-aurora');
        expect(modelManagerSource).toContain('prefers-reduced-motion');
    });

    it('retains visible warnings and gold-standard interaction sizing', () => {
        expect(detectionSettingsSource).toContain('autoVideoClassification && videoCircuitOpen');
        expect(detectionSettingsSource).toContain('classifierStatus?.fallback_reason');
        expect(detectionSettingsSource).toContain('role="alert"');
        expect(detectionSettingsSource).toContain('h-11');
        expect(detectionSettingsSource).not.toMatch(/text-\[(9|10|11)px\]/);
    });

    it('explains runtime image/provider mismatches without adding another card', () => {
        expect(detectionSettingsSource).toContain('classifierStatus.image_flavor');
        expect(detectionSettingsSource).toContain('classifierStatus.packaged_inference_providers');
        expect(detectionSettingsSource).toContain("classifierStatus.image_flavor_warning === 'selected_provider_not_packaged'");
        expect(detectionSettingsSource).toContain('settings.detection.image_flavor_mismatch');
        expect(detectionSettingsSource).toContain('docs/setup/hardware-acceleration.md');
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
    });

    it('keeps device compatibility warnings and skipped checks honest', () => {
        expect(detectionSettingsSource).toContain('<DiagnosticDialog');
        expect(detectionSettingsSource).toContain("state: 'warning'");
        expect(detectionSettingsSource).not.toContain("if (state === 'skipped') state = 'passed'");
        expect(detectionSettingsSource).toContain('ok: !failed && !warned && !skipped');
        expect(detectionSettingsSource).toContain('compat_results_unavailable');
        expect(detectionSettingsSource.match(/cdRunId \+= 1/g)).toHaveLength(4);
        expect(diagnosticDialogSource).toContain("s.state === 'skipped'");
        expect(diagnosticDialogSource).toContain("stage.state === 'warning'");
    });

    it('offers provider validation in every runtime image rather than only on Intel hosts', () => {
        expect(detectionSettingsSource).toContain('classifierStatus.host_available_providers');
        expect(detectionSettingsSource).toContain('compatMatrix.providers');
    });
});
