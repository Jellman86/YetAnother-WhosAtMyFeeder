// @ts-nocheck — this source audit runs under Vitest's Node environment; Node types are
// intentionally absent from the browser application tsconfig.
import { describe, expect, it } from 'vitest';

import diagnosticDialogSource from '../DiagnosticDialog.svelte?raw';
import advancedSectionSource from './_primitives/AdvancedSection.svelte?raw';
import detectionSettingsSource from './DetectionSettings.svelte?raw';
import modelSettingsSource from './ModelSettings.svelte?raw';
import statusBandSource from './DetectionStatusBand.svelte?raw';
import modelManagerSource from '../../pages/models/ModelManager.svelte?raw';
import settingsPageSource from '../../pages/Settings.svelte?raw';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// vitest stubs CSS ?raw imports to an empty string, so the kit stylesheet is
// read from disk (same approach as the code-quality source audits).
const appCss = readFileSync(resolve(__dirname, '../../../app.css'), 'utf-8');

describe('Detection and Models settings, status first', () => {
    it('opens with the status band: model, runtime, workers, health', () => {
        const band = modelSettingsSource.indexOf('<DetectionStatusBand');
        const firstCard = modelSettingsSource.indexOf('<SettingsCard');
        expect(band).toBeGreaterThan(-1);
        expect(firstCard).toBeGreaterThan(band);
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
        expect(modelSettingsSource).toContain('const healthIssueCount = $derived(');
        expect(modelSettingsSource).toContain('classifierStatus?.fallback_reason ? 1 : 0');
        // A failing video check is reported beside its switch in Detection, not counted twice.
        expect(detectionSettingsSource).toContain('autoVideoClassification && videoCircuitOpen');
        // The report and its card open for a runtime problem through the page (runtime-problem.ts),
        // and the health link opens both.
        expect(modelSettingsSource).toContain('const RUNTIME_REPORT_SECTION_ID = RUNTIME_DISCLOSURES[1];');
        expect(modelSettingsSource).toMatch(/hardwareCard\.open = true;\s*runtimeReport\.open = true;/);
        expect(statusBandSource).toContain('scrollIntoView');
    });

    it('leads with what decides an identification, and keeps the models and their hardware in Models', () => {
        const order = [
            'acceptance_title',
            "settings.detection.blocked_labels'",
            '<RangeFilterSettings',
            'frigate_video_title',
        ].map((key) => detectionSettingsSource.indexOf(key));
        for (const at of order) expect(at).toBeGreaterThan(-1);
        expect([...order].sort((a, b) => a - b)).toEqual(order);
        expect(detectionSettingsSource.match(/<SettingsCard/g)).toHaveLength(3);
        expect(detectionSettingsSource).toContain('id="detection-frigate-video"');
        expect(detectionSettingsSource.match(/<SettingsCard\s+collapsible/g)).toHaveLength(1);
        // Models opens on the running model, then the catalogue, then hardware, then testing.
        const modelsOrder = ['<DetectionStatusBand', 'models_card_title', 'hardware_title', 'testing_title'].map((key) => modelSettingsSource.indexOf(key));
        for (const at of modelsOrder) expect(at).toBeGreaterThan(-1);
        expect([...modelsOrder].sort((a, b) => a - b)).toEqual(modelsOrder);
        expect(modelSettingsSource).toContain('const HARDWARE_CARD_ID = RUNTIME_DISCLOSURES[0];');
        expect(modelSettingsSource).not.toContain('tuning_column');
    });

    it('keeps everyday choices visible and puts memory and isolation behind a disclosure that opens when customised', () => {
        const memory = modelSettingsSource.indexOf('id="detection-memory-advanced"');
        const report = modelSettingsSource.indexOf('id={RUNTIME_REPORT_SECTION_ID}');
        expect(memory).toBeGreaterThan(-1);
        for (const id of [
            'id="inference-provider"',
            'id="bird-model-region-override"',
            'onclick={() => runCompatCheck()}',
        ]) {
            const at = modelSettingsSource.indexOf(id);
            expect(at, id).toBeGreaterThan(-1);
            expect(at, `${id} must sit on the default surface`).toBeLessThan(memory);
        }
        for (const id of ['id="image-execution-mode"', 'id="live-worker-count"', 'id="background-worker-count"']) {
            const at = modelSettingsSource.indexOf(id);
            expect(at, id).toBeGreaterThan(memory);
            expect(at, id).toBeLessThan(report);
        }
        expect(modelSettingsSource).toContain('openByDefault={memoryCustomised}');
        expect(modelSettingsSource).toContain("imageExecutionMode !== 'subprocess'");
    });

    it('gives models their own card, carrying the bird finder choice through the settings form', () => {
        expect(modelSettingsSource).toContain('models_card_title');
        const modelsCard = modelSettingsSource.indexOf('id={MODELS_CARD_ID}');
        const modelManager = modelSettingsSource.indexOf('<ModelManager');
        expect(modelManager).toBeGreaterThan(modelsCard);
        expect(modelSettingsSource).toContain('bind:birdFinder');
        expect(settingsPageSource).toContain('bind:birdFinder');
        expect(settingsPageSource).toContain(
            "{ field: 'bird_crop_accurate_detector', draft: birdFinder, saved: parseBirdFinder(s.bird_crop_accurate_detector) }"
        );
        expect(settingsPageSource).toContain('bird_crop_accurate_detector: birdFinder,');
    });

    it('picks the model from cards with one honest state chip, not a select', () => {
        expect(modelManagerSource).not.toContain('<select id="classifier-model-select"');
        expect(modelManagerSource).toContain('aria-pressed={cardSelected}');
        expect(modelManagerSource).toContain('modelCardState(modelOption.id)');
        for (const state of ['model_manager_state_repair', 'model_manager_state_installed', 'model_manager_state_available']) {
            expect(modelManagerSource).toContain(state);
        }
        // Only the exceptions carry a chip: every card saying "Available" distinguished nothing.
        expect(modelManagerSource).toContain("{#if cardState !== 'available'}");
        // Each card states its costs in words: the download (or that it is already here) and its
        // memory. A bar under the download size read as download progress, so there is none.
        // The one memory meter left is the labelled total under the chosen model.
        expect(modelManagerSource.match(/model-ram-meter/g)).toHaveLength(1);
        expect(modelManagerSource).toContain("t('settings.detection.bird_finder_ram', '{ram} RAM', { ram: ramShortLabel(modelOption.estimated_ram_mb) })");
        // Coverage is the other everyday question: birds only, or wider wildlife.
        expect(modelManagerSource).toContain('scopeLabel(modelOption.taxonomy_scope)');
        // The flat look marks the selected card with its border, a brand tint and
        // aria-pressed; no decorative animated gradient behind either surface.
        expect(modelManagerSource).not.toContain('card-aurora');
        expect(statusBandSource).not.toContain('card-aurora');
        expect(appCss).not.toContain('.card-aurora');
        expect(appCss).toContain('prefers-reduced-motion');
    });

    it('retains visible warnings and gold-standard interaction sizing', () => {
        expect(detectionSettingsSource).toContain('autoVideoClassification && videoCircuitOpen');
        expect(modelSettingsSource).toContain('classifierStatus?.fallback_reason');
        expect(modelSettingsSource).toContain('role="alert"');
        expect(detectionSettingsSource).toContain('role="alert"');
        expect(detectionSettingsSource).toContain('h-11');
        expect(detectionSettingsSource).not.toMatch(/text-\[(9|10|11)px\]/);
    });

    it('explains runtime image/provider mismatches without adding another card', () => {
        expect(modelSettingsSource).toContain('classifierStatus.image_flavor');
        expect(modelSettingsSource).toContain('classifierStatus.packaged_inference_providers');
        expect(modelSettingsSource).toContain("classifierStatus.image_flavor_warning === 'selected_provider_not_packaged'");
        expect(modelSettingsSource).toContain('settings.detection.image_flavor_mismatch');
        expect(modelSettingsSource).toContain('docs/setup/hardware-acceleration.md');
    });

    it('uses the live provider contract instead of advertising every runtime', () => {
        expect(modelSettingsSource).toContain('buildInferenceProviderChoices');
        expect(modelSettingsSource).toContain('getProviderPreferenceOrder');
        expect(modelSettingsSource).toContain('providerPreferenceLabel');
        expect(modelSettingsSource).toContain('configuredProviderUnavailable');
        expect(modelSettingsSource).not.toContain("{ value: 'cuda', label:");
    });

    it('keeps the saved provider, including Intel NPU, through Settings hydration, dirty checks and saves', () => {
        expect(settingsPageSource).not.toContain('function normalizeInferenceProvider');
        expect(settingsPageSource).toContain("let inferenceProvider = $state<InferenceProvider>('auto');");
        expect(settingsPageSource).toContain("inferenceProvider = parseInferenceProvider(settings.inference_provider) ?? 'auto';");
        expect(settingsPageSource).toContain(
            "{ field: 'inference_provider', draft: inferenceProvider, saved: parseInferenceProvider(s.inference_provider) ?? 'auto' }"
        );
        expect(settingsPageSource).toContain(
            'inference_provider: inferenceProviderForSave(inferenceProvider, settingsStore.settings?.inference_provider),'
        );
    });

    it('keeps shared disclosures semantic, readable, and keyboard visible', () => {
        expect(advancedSectionSource).toContain('aria-expanded={open}');
        expect(advancedSectionSource).toContain('aria-controls={contentId}');
        expect(advancedSectionSource).toContain('id={contentId}');
        expect(advancedSectionSource).toContain('min-h-11');
        expect(advancedSectionSource).toContain('focus-ring');
    });

    it('keeps device compatibility warnings and skipped checks honest', () => {
        expect(modelSettingsSource).toContain('<DiagnosticDialog');
        expect(modelSettingsSource).toContain("state: 'warning'");
        expect(modelSettingsSource).not.toContain("if (state === 'skipped') state = 'passed'");
        expect(modelSettingsSource).toContain('ok: !failed && !warned && !skipped');
        expect(modelSettingsSource).toContain('compat_results_unavailable');
        expect(modelSettingsSource.match(/cdRunId \+= 1/g)).toHaveLength(4);
        expect(diagnosticDialogSource).toContain("s.state === 'skipped'");
        expect(diagnosticDialogSource).toContain("stage.state === 'warning'");
    });

    it('offers provider validation in every runtime image rather than only on Intel hosts', () => {
        expect(modelSettingsSource).toContain('classifierStatus.host_available_providers');
        expect(modelSettingsSource).toContain('compatMatrix.providers');
    });
});
