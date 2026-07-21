import { describe, expect, it } from 'vitest';
import wizardShellSource from './WizardShell.svelte?raw';
import modelStepSource from './ModelStep.svelte?raw';
import qualityStepSource from './QualityStep.svelte?raw';
import dataSettingsSource from '../settings/DataSettings.svelte?raw';
import sidebarSource from '../Sidebar.svelte?raw';
import appSource from '../../../App.svelte?raw';
import { WIZARD_STEPS } from '../../stores/setup_wizard.svelte';

describe('setup wizard wiring', () => {
    it('renders a branch for every wizard step id', () => {
        for (const step of WIZARD_STEPS) {
            expect(wizardShellSource).toContain(`step.id === '${step.id}'`);
        }
    });

    it('exposes an accessible progress indicator and step counter', () => {
        expect(wizardShellSource).toContain('role="progressbar"');
        expect(wizardShellSource).toContain('setup.step_of');
        expect(wizardShellSource).toContain('aria-live="polite"');
    });

    it('only shows the exit control in re-run mode', () => {
        expect(wizardShellSource).toContain("setupWizardStore.mode === 'rerun'");
    });

    it('offers an owner navigation action that opens the wizard without changing route', () => {
        expect(sidebarSource).toContain("setupWizardStore.open('rerun')");
        expect(sidebarSource).toContain("kind: 'action'");
        expect(sidebarSource).toContain("action: 'setup_wizard'");
        expect(sidebarSource).toContain("label: $_('nav.setup_wizard')");
        expect(sidebarSource).toContain('requiresAuth: true');
        expect(sidebarSource).toContain("aria-haspopup={item.kind === 'action' ? 'dialog' : undefined}");
        expect(dataSettingsSource).not.toContain("setupWizardStore.open('rerun')");
    });

    it('keeps the full-screen wizard up through first run and overlays it on re-run', () => {
        expect(appSource).toContain("setupWizardStore.mode === 'first_run'");
        expect(appSource).toContain("setupWizardStore.mode === 'rerun'");
        expect(wizardShellSource).toContain('role="dialog"');
        expect(wizardShellSource).toContain('aria-modal="true"');
    });

    it('locks background page scroll while the wizard is open', () => {
        expect(wizardShellSource).toContain("document.body.style.overflow = 'hidden'");
    });

    it('keeps model setup focused on compatible model and provider choices', () => {
        expect(modelStepSource).toContain('id="setup-model-id"');
        expect(modelStepSource).toContain('id="setup-provider"');
        expect(modelStepSource).toContain('buildInferenceProviderChoices');
        expect(modelStepSource).toContain('selectedModel?.supported_inference_providers');
        expect(modelStepSource).toContain('selectedValidation?.validated_providers');
        expect(modelStepSource).toContain('providerTouched');
        expect(modelStepSource).toContain('providerPreferenceLabel');
        expect(modelStepSource).toContain('model_ids: [selectedModelId]');
        expect(modelStepSource).toContain('canContinue={selectedModelReady}');
        expect(modelStepSource).toContain('disabled={needsDownload || !selectedModelId}');
        expect(modelStepSource).not.toContain('id="setup-execution-mode"');
        expect(modelStepSource).toContain('Hardware validation completed successfully.');
    });

    it('treats best-image selection as one automatic policy', () => {
        expect(qualityStepSource).toContain('media_cache_high_quality_event_snapshots: hqSnapshots');
        expect(qualityStepSource).not.toContain('media_cache_high_quality_event_snapshot_bird_crop');
        expect(qualityStepSource).toContain('strongest reliable bird crop');
    });
});
