import { describe, expect, it } from 'vitest';
import detectionSource from './DetectionSettings.svelte?raw';
import modelsSource from './ModelSettings.svelte?raw';
import settingsSource from '../../pages/Settings.svelte?raw';
import bandSource from './DetectionStatusBand.svelte?raw';
import modelManagerSource from '../../pages/models/ModelManager.svelte?raw';

// Detection holds the rules for accepting an identification; Models holds which models run, on
// what hardware, and the checks behind them. Each setting has exactly one of the two as its home.
describe('Detection and Models', () => {
    it('gives the models, the hardware and the runtime report their own tab', () => {
        expect(settingsSource).toContain("activeTab === 'models'");
        expect(settingsSource).toContain("import('../components/settings/ModelSettings.svelte')");
        expect(modelsSource).toContain('<ModelManager');
        expect(modelsSource).toContain('<DetectionStatusBand');
        expect(modelsSource).toContain('id="inference-provider"');
        expect(modelsSource).toContain('id="image-execution-mode"');
        expect(modelsSource).toContain('id="bird-model-region-override"');
        expect(modelsSource).toContain('<DiagnosticDialog');
        // The runtime it shows is kept current while Models, not Detection, is open.
        expect(settingsSource).toContain("if (activeTab !== 'models' || !authStore.showSettings) return;");
    });

    it('leaves Detection with thresholds, blocked species, the range filter and video checks only', () => {
        expect(detectionSource).toContain('id="confidence-threshold-slider"');
        expect(detectionSource).toContain('<RangeFilterSettings');
        expect(detectionSource).toContain('id="blocked-species-search"');
        expect(detectionSource).toContain('setting-auto-video');
        for (const moved of ['<ModelManager', '<DetectionStatusBand', 'inference-provider', 'image-execution-mode', 'bird-model-region-override', 'DiagnosticDialog', 'startModelEvalRun']) {
            expect(detectionSource, moved).not.toContain(moved);
        }
    });

    it('folds the old Debug tab into Models: one switch for the debug build, and the model evaluation page linked', () => {
        expect(settingsSource).not.toContain("activeTab === 'debug'");
        expect(modelsSource).toContain('{#if debugUiEnabled}');
        expect(modelsSource).toContain('setting-strict-non-finite-output');
        expect(modelsSource).toContain('/diagnostics/model-eval');
        // The link is the kit's secondary button, not a hand-made black one.
        expect(modelsSource).not.toContain('bg-slate-900 px-4 py-2 text-xs font-bold text-white');
    });

    it('links Detection to Models instead of repeating the model choice', () => {
        expect(detectionSource).toContain('onopenmodels');
    });

    it('names the running model as its card does, and never calls a missing model in use', () => {
        // The configured id can be a bare file name such as model.tflite; the card's name comes
        // from the model list, so the band uses the same name.
        expect(bandSource).toContain('classifierStatus?.effective_model_name');
        expect(bandSource).toContain('classifierStatus?.effective_model_id');
        expect(bandSource).toContain('classifierStatus?.active_model_installed === false');
        expect(bandSource).toContain('band_model_missing');
        // A missing model is a problem the owner can act on, so it is counted.
        expect(modelsSource).toContain("classifierStatus?.active_model_installed === false ? 1 : 0");
        // The model in use says so; it is never offered for download as if it were not here.
        expect(modelManagerSource).toContain('model_manager_in_use');
    });
});
