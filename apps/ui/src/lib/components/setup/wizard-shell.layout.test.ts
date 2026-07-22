import { describe, expect, it } from 'vitest';
import wizardShellSource from './WizardShell.svelte?raw';
import wizardStepLayoutSource from './WizardStepLayout.svelte?raw';
import modelStepSource from './ModelStep.svelte?raw';
import qualityStepSource from './QualityStep.svelte?raw';
import dataSettingsSource from '../settings/DataSettings.svelte?raw';
import settingsTabsSource from '../settings/SettingsTabs.svelte?raw';
import sidebarSource from '../Sidebar.svelte?raw';
import appSource from '../../../App.svelte?raw';
import camerasStepSource from './CamerasStep.svelte?raw';
import connectionStepSource from './ConnectionStep.svelte?raw';
import integrationsStepSource from './IntegrationsStep.svelte?raw';
import telemetryStepSource from './TelemetryStep.svelte?raw';
import historyStepSource from './HistoryStep.svelte?raw';
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

    it('offers the wizard from Settings navigation instead of the application sidebar', () => {
        expect(settingsTabsSource).toContain("setupWizardStore.open('rerun')");
        expect(settingsTabsSource).toContain("$_('nav.setup_wizard')");
        expect(settingsTabsSource).toContain('aria-haspopup="dialog"');
        expect(settingsTabsSource).toContain('data-setup-wizard-action');
        expect(sidebarSource).not.toContain("setupWizardStore.open('rerun')");
        expect(sidebarSource).not.toContain("action: 'setup_wizard'");
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

    it('portals, traps focus, restores focus, and supports Escape in re-run mode', () => {
        expect(wizardShellSource).toContain('use:portal');
        expect(wizardShellSource).toContain('trapFocus');
        expect(wizardShellSource).toContain("event.key === 'Escape'");
        expect(wizardShellSource).toContain('previouslyFocused');
        expect(wizardShellSource).toContain('tabindex="-1"');
    });

    it('shows actionable failures raised by step save handlers', () => {
        expect(wizardStepLayoutSource).toContain('role="alert"');
        expect(wizardStepLayoutSource).toContain('actionError');
        expect(wizardStepLayoutSource).toContain('catch (error)');
        expect(modelStepSource).toContain('validationDeadline');
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
        expect(modelStepSource).toContain("canContinue={loadState === 'ready' && selectedModelReady}");
        expect(modelStepSource).toContain('selectSetupModelId');
        expect(modelStepSource).toContain('downloadModel');
        expect(modelStepSource).toContain('fetchDownloadStatus');
        expect(modelStepSource).toContain('role="progressbar"');
        expect(modelStepSource).toContain('downloadPct');
        expect(modelStepSource).not.toContain('id="setup-execution-mode"');
        expect(modelStepSource).toContain('Hardware validation completed successfully.');
        expect(modelStepSource).toContain('getVisibleTieredModelLineup');
    });

    it('treats best-image selection as one automatic policy', () => {
        expect(qualityStepSource).toContain('media_cache_high_quality_event_snapshots: hqSnapshots');
        expect(qualityStepSource).not.toContain('media_cache_high_quality_event_snapshot_bird_crop');
        expect(qualityStepSource).toContain('strongest reliable bird crop');
    });

    it('blocks writes until each settings-backed step has loaded the saved configuration', () => {
        for (const source of [
            camerasStepSource,
            connectionStepSource,
            modelStepSource,
            qualityStepSource,
            integrationsStepSource,
            telemetryStepSource
        ]) {
            expect(source).toContain('<WizardLoadState');
            expect(source).toContain("loadState === 'ready'");
            expect(source).toContain('onRetry={load}');
        }
        expect(camerasStepSource).not.toContain('classification_threshold: threshold');
    });

    it('offers a consent-based background history import during setup', () => {
        expect(historyStepSource).toContain('startBackfillJob');
        expect(historyStepSource).toContain('importHistory = $state(false)');
        expect(historyStepSource).toContain("route: '/jobs'");
        expect(historyStepSource).toContain('cannot recreate BirdNET-Go audio');
    });
});
