import { describe, expect, it } from 'vitest';
import detectionSource from './DetectionSettings.svelte?raw';
import modelsSource from './ModelSettings.svelte?raw';
import providerWarningSource from '../ProviderWarning.svelte?raw';
import hardwareSource from './HardwareSettings.svelte?raw';
import namingSource from './NamingSettings.svelte?raw';
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
        expect(modelsSource).toContain('id="bird-model-region-override"');
        // Hardware and its runtime report are their own card under the section's More options, and
        // the device check's dialog belongs to the section, which both the models and Hardware use.
        expect(hardwareSource).toContain('id="inference-provider"');
        expect(hardwareSource).toContain('id="image-execution-mode"');
        expect(identificationSource).toContain('<DeviceCheckDialog check={deviceCheck} />');
        // The runtime it shows is kept current while the section holding Models is open.
        expect(settingsSource).toContain("if (activeSection !== settingsSectionOfPart('models') || !authStore.showSettings) return;");
    });

    it('leaves Detection with blocked species, the range filter and video checks, and the thresholds with naming', () => {
        expect(namingSource).toContain('id="confidence-threshold-slider"');
        expect(detectionSource).not.toContain('id="confidence-threshold-slider"');
        expect(detectionSource).toContain('<RangeFilterSettings');
        expect(detectionSource).toContain('id="blocked-species-search"');
        expect(detectionSource).toContain('setting-auto-video');
        for (const moved of ['<ModelManager', '<IdentificationStatusLine', 'inference-provider', 'image-execution-mode', 'bird-model-region-override', 'DiagnosticDialog', 'startModelEvalRun']) {
            expect(detectionSource, moved).not.toContain(moved);
        }
    });

    it('folds the old Debug tab into Models: one switch for the debug build, and the model evaluation page linked', () => {
        expect(settingsSource).not.toContain("activeTab === 'debug'");
        expect(hardwareSource).toContain('{#if debugUiEnabled}');
        expect(hardwareSource).toContain('setting-strict-non-finite-output');
        expect(modelsSource).toContain('/diagnostics/model-eval');
        // The link is the kit's secondary button, not a hand-made black one.
        expect(modelsSource).not.toContain('bg-slate-900 px-4 py-2 text-xs font-bold text-white');
    });

    it('sends the dashboard\'s provider warning to the models, whose status line leads to the runtime report', () => {
        expect(providerWarningSource).toContain("onnavigate?.('/settings/models')");
    });

    it('puts Detection under More options below Models, so it needs no link to them', () => {
        expect(detectionSource).not.toContain('onopenmodels');
        expect(identificationSource.indexOf('<ModelSettings')).toBeLessThan(identificationSource.indexOf('<DetectionSettings'));
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
