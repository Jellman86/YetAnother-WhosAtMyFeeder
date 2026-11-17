// @ts-nocheck — this source audit runs under Vitest's Node environment; Node types are
// intentionally absent from the browser application tsconfig.
import { describe, expect, it } from 'vitest';

import diagnosticDialogSource from '../DiagnosticDialog.svelte?raw';
import advancedSectionSource from './_primitives/AdvancedSection.svelte?raw';
import detectionSettingsSource from './DetectionSettings.svelte?raw';
import modelSettingsSource from './ModelSettings.svelte?raw';
import hardwareSource from './HardwareSettings.svelte?raw';
import namingSource from './NamingSettings.svelte?raw';
import deviceCheckDialogSource from './DeviceCheckDialog.svelte?raw';
import deviceCheckSource from '../../settings/device-check.svelte.ts?raw';
import identificationSource from './sections/IdentificationSection.svelte?raw';
import statusLineSource from '../IdentificationStatusLine.svelte?raw';
import modelManagerSource from '../../pages/models/ModelManager.svelte?raw';
import settingsPageSource from '../../pages/Settings.svelte?raw';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// vitest stubs CSS ?raw imports to an empty string, so the kit stylesheet is
// read from disk (same approach as the code-quality source audits).
const appCss = readFileSync(resolve(__dirname, '../../../app.css'), 'utf-8');

describe('Detection and Models settings, status first', () => {
    it('opens with one sentence of what names birds right now, not a strip of runtime facts', () => {
        const status = modelSettingsSource.indexOf('<IdentificationStatusLine');
        const firstCard = modelSettingsSource.indexOf('<SettingsCard');
        expect(status).toBeGreaterThan(-1);
        expect(firstCard).toBeGreaterThan(status);
        expect(statusLineSource).toContain('role="status"');
        // Its room is held while the status loads, so the page below does not jump.
        expect(modelSettingsSource).toContain('<div class="min-h-14 space-y-2" data-models-status>');
    });

    it('counts real problems for the report link and opens the report on trouble', () => {
        expect(modelSettingsSource).toContain('const healthIssueCount = $derived(');
        expect(modelSettingsSource).toContain('classifierStatus?.fallback_reason ? 1 : 0');
        // A failing video check is reported once, at the top of the section, not counted twice.
        expect(identificationSource).toContain('autoVideoClassification && videoCircuitOpen');
        // The report and its card open for a runtime problem through the page (runtime-problem.ts),
        // and the health link opens both.
        expect(modelSettingsSource).toContain('const RUNTIME_REPORT_SECTION_ID = RUNTIME_DISCLOSURES[0];');
        // The report is in Hardware, under More options: the link opens both before scrolling.
        expect(modelSettingsSource).toMatch(/more\.open = true;\s*runtimeReport\.open = true;/);
        expect(modelSettingsSource).toContain('scrollIntoView');
    });

    it('leads with what decides an identification, then the models, with the rest under More options', () => {
        // The section opens on the naming threshold, then the models; the rest is under More options.
        const sectionOrder = ['<NamingSettings', '<ModelSettings', '<SectionMore', '<DetectionSettings', '<HardwareSettings', 'data-settings-part="beta"'].map((key) => identificationSource.indexOf(key));
        for (const at of sectionOrder) expect(at).toBeGreaterThan(-1);
        expect([...sectionOrder].sort((a, b) => a - b)).toEqual(sectionOrder);
        expect(namingSource).toContain('acceptance_desc');
        const order = [
            "settings.detection.blocked_labels'",
            '<RangeFilterSettings',
            'frigate_video_title',
        ].map((key) => detectionSettingsSource.indexOf(key));
        for (const at of order) expect(at).toBeGreaterThan(-1);
        expect([...order].sort((a, b) => a - b)).toEqual(order);
        expect(detectionSettingsSource.match(/<SettingsCard/g)).toHaveLength(2);
        expect(detectionSettingsSource).toContain('id="detection-frigate-video"');
        expect(detectionSettingsSource.match(/<SettingsCard\s+collapsible/g)).toHaveLength(1);
        // Models opens on what names birds, then the models with the evaluation row; Hardware is its own card.
        const modelsOrder = ['<IdentificationStatusLine', 'models_card_title', 'setting-model-evaluation'].map((key) => modelSettingsSource.indexOf(key));
        for (const at of modelsOrder) expect(at).toBeGreaterThan(-1);
        expect([...modelsOrder].sort((a, b) => a - b)).toEqual(modelsOrder);
        expect(hardwareSource).toContain('hardware_title');
        // Hardware is a plain section: its device choice is on the surface, the rest under advanced options.
        expect(hardwareSource).not.toMatch(/<SettingsCard\s+collapsible/);
        expect(modelSettingsSource).not.toContain('tuning_column');
    });

    it('keeps everyday choices visible and puts memory and isolation behind a disclosure that opens when customised', () => {
        const memory = hardwareSource.indexOf('id="detection-memory-advanced"');
        const report = hardwareSource.indexOf('id={RUNTIME_REPORT_SECTION_ID}');
        expect(memory).toBeGreaterThan(-1);
        expect(modelSettingsSource).toContain('id="bird-model-region-override"');
        for (const id of [
            'id="inference-provider"',
            'onclick={() => deviceCheck.run()}',
        ]) {
            const at = hardwareSource.indexOf(id);
            expect(at, id).toBeGreaterThan(-1);
            expect(at, `${id} must sit on the default surface`).toBeLessThan(memory);
        }
        for (const id of ['id="image-execution-mode"', 'id="live-worker-count"', 'id="background-worker-count"']) {
            const at = hardwareSource.indexOf(id);
            expect(at, id).toBeGreaterThan(memory);
            expect(at, id).toBeLessThan(report);
        }
        expect(hardwareSource).toContain('openByDefault={memoryCustomised}');
        expect(hardwareSource).toContain("imageExecutionMode !== 'subprocess'");
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

    it('shows the model in use and one recommendation, with every other model behind one disclosure', () => {
        expect(modelManagerSource).not.toContain('<select id="classifier-model-select"');
        // One disclosure for the whole catalogue, closed until the owner opens it, even when no
        // model is in use: the current model and the recommendation already say what to do.
        expect(modelManagerSource).toContain('let catalogueOpen = $state(false);');
        expect(modelManagerSource.match(/data-model-catalogue-toggle/g)).toHaveLength(1);
        expect(modelManagerSource).not.toContain('showAdvancedModels');
        expect(modelManagerSource).toContain('data-current-model');
        expect(modelManagerSource).toContain('recommendIdentificationModel(classifierModels');
        // A catalogue row opens its own details in place, so choosing never jumps the page.
        expect(modelManagerSource).toContain('aria-expanded={expanded}');
        expect(modelManagerSource).toContain('modelCardState(modelOption.id)');
        for (const state of ['model_manager_state_repair', 'model_manager_state_installed', 'model_manager_state_available']) {
            expect(modelManagerSource).toContain(state);
        }
        // Only the exceptions carry a chip: every card saying "Available" distinguished nothing.
        expect(modelManagerSource).toContain("cardState !== 'available' ? { label: modelCardStateLabel(cardState)");
        // Costs and coverage are one sentence-case line, in words; there is no memory bar.
        expect(modelManagerSource).toContain('modelFactsLine(modelOption');
        expect(modelManagerSource).not.toContain('model-ram-meter');
        // Names lead with what the model is for; the code name is secondary.
        expect(modelManagerSource).toContain('identificationModelName(model, t)');
        expect(modelManagerSource).not.toContain('card-aurora');
        expect(statusLineSource).not.toContain('card-aurora');
        expect(appCss).not.toContain('.card-aurora');
        expect(appCss).toContain('prefers-reduced-motion');
    });

    it('retains visible warnings and gold-standard interaction sizing', () => {
        expect(identificationSource).toContain('autoVideoClassification && videoCircuitOpen');
        expect(identificationSource).toContain('role="alert"');
        expect(modelSettingsSource).toContain('classifierStatus?.fallback_reason');
        expect(hardwareSource).toContain('role="alert"');
        expect(detectionSettingsSource).toContain('role="alert"');
        expect(detectionSettingsSource).toContain('h-11');
        expect(detectionSettingsSource).not.toMatch(/text-\[(9|10|11)px\]/);
    });

    it('explains runtime image/provider mismatches without adding another card', () => {
        expect(hardwareSource).toContain('classifierStatus.image_flavor');
        expect(hardwareSource).toContain('classifierStatus.packaged_inference_providers');
        expect(hardwareSource).toContain("classifierStatus.image_flavor_warning === 'selected_provider_not_packaged'");
        expect(hardwareSource).toContain('settings.detection.image_flavor_mismatch');
        expect(hardwareSource).toContain('docs/setup/hardware-acceleration.md');
    });

    it('uses the live provider contract instead of advertising every runtime', () => {
        expect(hardwareSource).toContain('buildInferenceProviderChoices');
        expect(hardwareSource).toContain('getProviderPreferenceOrder');
        expect(hardwareSource).toContain('providerPreferenceLabel');
        expect(hardwareSource).toContain('configuredProviderUnavailable');
        expect(hardwareSource).not.toContain("{ value: 'cuda', label:");
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
        expect(deviceCheckDialogSource).toContain('<DiagnosticDialog');
        expect(deviceCheckDialogSource).toContain("state: 'warning'");
        expect(deviceCheckDialogSource).not.toContain("if (state === 'skipped') state = 'passed'");
        expect(deviceCheckDialogSource).toContain('ok: !failed && !warned && !skipped');
        expect(deviceCheckSource).toContain('compat_results_unavailable');
        // The dialog is redrawn when a check starts, when it stops, and when its result (or the
        // reason it has none) arrives.
        expect(deviceCheckSource.match(/dialogRunId \+= 1/g)).toHaveLength(3);
        expect(diagnosticDialogSource).toContain("s.state === 'skipped'");
        expect(diagnosticDialogSource).toContain("stage.state === 'warning'");
    });

    it('offers provider validation in every runtime image rather than only on Intel hosts', () => {
        expect(hardwareSource).toContain('classifierStatus.host_available_providers');
        expect(hardwareSource).toContain('deviceCheck.matrix.providers');
    });
});
