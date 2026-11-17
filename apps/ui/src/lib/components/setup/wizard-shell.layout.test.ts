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
import historyStepSource from './HistoryStep.svelte?raw';
import accountStepSource from './AccountStep.svelte?raw';
import welcomeStepSource from './WelcomeStep.svelte?raw';
import { WIZARD_STEPS } from '../../stores/setup_wizard.svelte';
import enSetup from '../../i18n/locales/en/setup.json';

const en = { setup: enSetup };

const stepNames = en.setup.step_names;

describe('setup wizard wiring', () => {
    it('renders a branch for every wizard step id', () => {
        for (const step of WIZARD_STEPS) {
            expect(wizardShellSource).toContain(`step.id === '${step.id}'`);
        }
    });

    it('exposes an accessible progress indicator and step counter', () => {
        expect(wizardShellSource).toContain('role="progressbar"');
        expect(wizardShellSource).toContain('setup.step_of');
    });

    it('announces a step once: the step focuses its heading and the body is not a live region', () => {
        expect(wizardStepLayoutSource).toContain('heading?.focus()');
        expect(wizardShellSource).not.toContain('aria-live');
        // Targeted status messages inside steps keep their own regions.
        expect(wizardStepLayoutSource).toContain('role="alert"');
    });

    it('lists the steps by name, marks the current one, and names it beside the counter', () => {
        expect(wizardShellSource).toMatch(/<ol[^>]*aria-label=\{\$_\('setup\.step_list'/);
        expect(wizardShellSource).toContain("aria-current={i === index ? 'step' : undefined}");
        expect(wizardShellSource).toContain('<span class="sr-only">{stepName(s.id)}</span>');
        expect(wizardShellSource).toContain('{stepName(step.id)}');
        expect(wizardShellSource).not.toContain('title={s.id}');
        for (const step of WIZARD_STEPS) expect(stepNames).toHaveProperty(step.id);
    });

    it('gives each credential field the autocomplete it really is', () => {
        // The owner account is new, so a password manager should offer to save it.
        expect(accountStepSource).toMatch(/id="setup-username"[^>]*autocomplete="username"/);
        expect(accountStepSource).toMatch(/id="setup-password"[^>]*autocomplete="new-password"[^>]*aria-describedby="setup-password-rules"/);
        expect(accountStepSource).toMatch(/id="setup-confirm"[^>]*autocomplete="new-password"[^>]*aria-describedby="setup-password-rules"/);
        expect(accountStepSource).toContain('id="setup-password-rules"');
        expect(accountStepSource).toContain('AUTH_PASSWORD_REQUIREMENTS.key');
        expect(accountStepSource).toMatch(/<label class="[^"]*min-h-11[^"]*">\s*<input type="checkbox" bind:checked=\{skipAuth\}/);
        // The broker's account is not the owner's login, so the browser must not fill it in.
        expect(connectionStepSource).toMatch(/id="setup-mqtt-username"[^>]*autocomplete="off"/);
        expect(connectionStepSource).toMatch(/id="setup-mqtt-password"[\s\S]{0,80}autocomplete="new-password"/);
        expect(connectionStepSource).not.toContain('autocomplete="current-password"');
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
        expect(modelStepSource).toContain('selectedValidatedProviders');
        expect(modelStepSource).toContain('selectedInstalledModel?.validated_inference_providers');
        expect(modelStepSource).toContain('selectedInstalledModel?.provider_preference_order');
        expect(modelStepSource).toContain('providerTouched');
        expect(modelStepSource).toContain('providerPreferenceLabel');
        expect(modelStepSource).toContain('model_ids: [runModelId]');
        expect(modelStepSource).toContain('canContinue={canSave}');
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
            integrationsStepSource
        ]) {
            expect(source).toContain('<WizardLoadState');
            expect(source).toContain("loadState === 'ready'");
            expect(source).toContain('onRetry={load}');
        }
        expect(camerasStepSource).not.toContain('classification_threshold: threshold');
    });

    it('lets first-run be skipped honestly, without weakening the rerun exit', () => {
        // First-run shows Skip setup where rerun shows the close button.
        expect(wizardShellSource).toContain("$_('setup.skip'");
        expect(wizardShellSource).toContain('skipConfirming = true');
        // Skipping states its one consequence and asks before acting.
        expect(wizardShellSource).toContain('role="alertdialog"');
        expect(wizardShellSource).toContain('skip_confirm_body_no_account');
        // It completes initial setup with auth disabled only when still needed,
        // through the same store path the account step uses, then closes.
        expect(wizardShellSource).toContain('if (authStore.needsInitialSetup)');
        expect(wizardShellSource).toContain("completeInitialSetup({ username: 'admin', password: null, enableAuth: false })");
        expect(wizardShellSource).toContain('setupWizardStore.close()');
        // A failed skip is reported, not swallowed.
        expect(wizardShellSource).toContain('skipError =');
        // Escape stays rerun-only.
        expect(wizardShellSource).toContain('&& canExit');
    });

    it('offers a consent-based background history import during setup', () => {
        expect(historyStepSource).toContain('startBackfillJob');
        expect(historyStepSource).toContain('importHistory = $state(false)');
        expect(historyStepSource).toContain("route: '/jobs'");
        expect(historyStepSource).toContain('cannot recreate BirdNET-Go audio');
    });

    it('says why Continue is disabled, and ties the reason to the button', () => {
        expect(wizardStepLayoutSource).toContain('data-setup-continue-blocked');
        expect(wizardStepLayoutSource).toContain("aria-describedby={blocked ? 'setup-continue-blocked' : undefined}");
        for (const source of [camerasStepSource, connectionStepSource, modelStepSource, qualityStepSource, integrationsStepSource]) {
            expect(source).toMatch(/blockedReason/);
        }
    });

    it('offers an honest way past a Frigate that is not up yet', () => {
        expect(connectionStepSource).toContain("skipLabel={$_('setup.connection.later'");
        expect(connectionStepSource).toContain('data-setup-connection-later');
        // The note names what waits on the connection, rather than a vague "fix it later".
        expect(en.setup.connection.later_note).toMatch(/no visits arrive, no photos or clips can be fetched/);
    });

    it('asks the two optional closing questions on one screen', () => {
        expect(WIZARD_STEPS.map((step) => step.id)).not.toContain('telemetry');
        expect(WIZARD_STEPS).toHaveLength(9);
        expect(historyStepSource).toContain("updateSettings({ telemetry_enabled: shareUsage })");
        // A choice that never loaded is never written over the stored one.
        expect(historyStepSource).toContain("if (usageLoad === 'ready')");
    });

    it('lists what setup covers as text, not as tiles that look like buttons', () => {
        expect(welcomeStepSource).toContain('data-setup-welcome-covers');
        expect(welcomeStepSource).not.toContain('SetupStepIcon');
    });

    it('keeps Back and Continue in the card: the step scrolls above them, never with them', () => {
        expect(wizardShellSource).not.toContain('max-h-[70vh]');
        // The shell itself never scrolls; the one scrolling box in it is the skip prompt's words, held
        // to half the screen with its buttons outside it, so they and the step's actions stay put.
        expect(wizardShellSource.match(/overflow-y-auto/g) ?? []).toHaveLength(1);
        const prompt = wizardShellSource.slice(wizardShellSource.indexOf('role="alertdialog"') - 200);
        expect(prompt).toMatch(/max-h-half-screen shrink-0 flex-col[^"]*" role="alertdialog"/);
        expect(prompt.indexOf('overflow-y-auto')).toBeLessThan(prompt.indexOf('skip_confirm_action'));
        expect(wizardShellSource).toContain('flex max-h-full w-full max-w-2xl flex-col');
        const scroller = wizardStepLayoutSource.indexOf('data-setup-scroll');
        const footer = wizardStepLayoutSource.indexOf('data-setup-footer');
        expect(scroller).toBeGreaterThan(-1);
        expect(footer).toBeGreaterThan(scroller);
        expect(wizardStepLayoutSource).toMatch(/class="shrink-0[^"]*" data-setup-footer/);
        // The footer is a sibling of the scroller, so it cannot scroll out of the card.
        const scrollerEnd = wizardStepLayoutSource.lastIndexOf('</div>', footer);
        expect(wizardStepLayoutSource.slice(scroller, scrollerEnd)).not.toContain('setup.continue');
    });

    it('waits for Frigate apart from the settings, and never calls that wait loading settings', () => {
        expect(camerasStepSource).not.toContain('Promise.allSettled');
        expect(camerasStepSource).toContain('readCameraList(fetchFrigateConfig)');
        expect(camerasStepSource).toContain('data-setup-camera-reading');
        expect(camerasStepSource).toContain("$_('setup.cameras.list_timed_out'");
    });
});
