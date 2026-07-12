import { describe, expect, it } from 'vitest';
import wizardShellSource from './WizardShell.svelte?raw';
import dataSettingsSource from '../settings/DataSettings.svelte?raw';
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

    it('offers a re-run entry from Settings that opens the wizard without clobbering config', () => {
        expect(dataSettingsSource).toContain("setupWizardStore.open('rerun')");
    });

    it('keeps the full-screen wizard up through first run and overlays it on re-run', () => {
        expect(appSource).toContain("setupWizardStore.mode === 'first_run'");
        expect(appSource).toContain("setupWizardStore.mode === 'rerun'");
    });
});
