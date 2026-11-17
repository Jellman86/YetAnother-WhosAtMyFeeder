import { describe, expect, it } from 'vitest';
import detectionSource from './DetectionSettings.svelte?raw';
import modelsSource from './ModelSettings.svelte?raw';
import settingsSource from '../../pages/Settings.svelte?raw';
import partLoadersSource from './sections/part-loaders.ts?raw';
import identificationSource from './sections/IdentificationSection.svelte?raw';
import statusSource from '../../settings/identification-models.ts?raw';
import statusLineSource from '../IdentificationStatusLine.svelte?raw';
import modelManagerSource from '../../pages/models/ModelManager.svelte?raw';

// Detection holds the rules for accepting an identification; Models holds which models run, on
// what hardware, and the checks behind them. Each setting has exactly one of the two as its home.
describe('Detection and Models', () => {
    it('gives the models, the hardware and the runtime report their own part of Identifying birds', () => {
        expect(identificationSource).toContain('data-settings-part="models"');
        expect(partLoadersSource).toContain("import('../ModelSettings.svelte')");
        expect(modelsSource).toContain('<ModelManager');
        expect(modelsSource).toContain('<IdentificationStatusLine');
        expect(modelsSource).toContain('id="inference-provider"');
        expect(modelsSource).toContain('id="image-execution-mode"');
        expect(modelsSource).toContain('id="bird-model-region-override"');
        expect(modelsSource).toContain('<DiagnosticDialog');
        // The runtime it shows is kept current while the section holding Models is open.
        expect(settingsSource).toContain("if (activeSection !== settingsSectionOfPart('models') || !authStore.showSettings) return;");
    });

    it('leaves Detection with thresholds, blocked species, the range filter and video checks only', () => {
        expect(detectionSource).toContain('id="confidence-threshold-slider"');
        expect(detectionSource).toContain('<RangeFilterSettings');
        expect(detectionSource).toContain('id="blocked-species-search"');
        expect(detectionSource).toContain('setting-auto-video');
        for (const moved of ['<ModelManager', '<IdentificationStatusLine', 'inference-provider', 'image-execution-mode', 'bird-model-region-override', 'DiagnosticDialog', 'startModelEvalRun']) {
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
        // The configured id can be a bare file name such as model.tflite; the status names the
        // model the runtime reports, by the same purpose-first name the card uses.
        expect(statusSource).toContain('status.effective_model_name');
        expect(statusSource).toContain('status.effective_model_id');
        expect(statusSource).toContain('status.active_model_installed === false');
        expect(statusLineSource).toContain("settings.models.status_missing'");
        expect(statusLineSource).toContain('identificationModelName(');
        // "In use" is said only of a model that is selected and running on the classifier's evidence;
        // a selected model that failed, is loading or was not reported states that readiness instead.
        expect(modelManagerSource).toContain('model_manager_in_use');
        expect(modelManagerSource).toContain("return isSelected(modelId) && chosenReadiness === 'running';");
        expect(modelManagerSource).toContain('{@const currentActive = isRunning(currentModel.id)}');
        expect(modelManagerSource).not.toContain('isActive(');
        // The chosen model's state and its recovery come from the shared rule and the shared activity.
        expect(modelManagerSource).toContain('classifierReadiness(classifierStatus, modelActivityStore.phase(currentModelId))');
        expect(modelManagerSource).toContain('data-model-recovery="revalidate"');
        // Work in progress is the server's to report. The page records what it starts as a hint, keeps
        // itself reconciled while it is shown, and resumes the progress of a download it did not start.
        expect(modelManagerSource).toContain('modelActivityStore.hint(model.id, activityPhase(stages));');
        expect(modelManagerSource).toContain('stopWatchingActivity = modelActivityStore.watch(() => void refreshModels());');
        expect(modelManagerSource).toContain('modelActivityStore.active()');
        expect(modelManagerSource).not.toContain('modelActivityStore.set(');
    });
});
