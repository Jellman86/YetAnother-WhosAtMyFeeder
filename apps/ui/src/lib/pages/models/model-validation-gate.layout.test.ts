import { describe, expect, it } from 'vitest';

import modelManagerSource from './ModelManager.svelte?raw';

describe('Model Manager guided install + selection gate', () => {
    it('the download button opens the guided wizard (not a bare download)', () => {
        expect(modelManagerSource).toContain('onclick={() => handleInstall(model)}');
        expect(modelManagerSource).toContain('model_manager_download_setup');
        expect(modelManagerSource).toContain("runInstallWizard(model, { download: true })");
    });

    it('gates activation on validation for an already-downloaded model', () => {
        // "Use this model" is only offered once the model is validated on this host.
        expect(modelManagerSource).toContain('ready && !active && validated');
        // The unvalidated branch runs the wizard from the validate stage (no re-download).
        expect(modelManagerSource).toContain('ready && !active && !validated');
        expect(modelManagerSource).toContain('model_manager_validate_to_enable');
        expect(modelManagerSource).toContain("runInstallWizard(model, { download: false })");
    });

    it('explains why an unvalidated model is not yet selectable', () => {
        expect(modelManagerSource).toContain('model_manager_validation_needed');
    });

    it('runs four real stages through the shared DiagnosticDialog with live download progress', () => {
        expect(modelManagerSource).toContain("import DiagnosticDialog from '../../components/DiagnosticDialog.svelte'");
        expect(modelManagerSource).toContain('<DiagnosticDialog');
        // Ordered checks: download → run on hardware → find fastest device → enable.
        expect(modelManagerSource).toContain("id: 'download'");
        expect(modelManagerSource).toContain("id: 'validate'");
        expect(modelManagerSource).toContain("id: 'optimize'");
        expect(modelManagerSource).toContain("id: 'enable'");
        // The download stage streams percent into the dialog.
        expect(modelManagerSource).toContain('model_manager_installing_pct');
        expect(modelManagerSource).toContain('pollWizardDownload');
        // Each stage calls its real backend action.
        expect(modelManagerSource).toContain('await downloadModel(model.id)');
        expect(modelManagerSource).toContain('await validateModel(model.id)');
        expect(modelManagerSource).toContain('await activateModel(model.id)');
    });

    it('sweeps the host devices and auto-sets the fastest inference provider', () => {
        expect(modelManagerSource).toContain('runWizardDeviceSweep');
        expect(modelManagerSource).toContain('pickFastestProvider');
        expect(modelManagerSource).toContain("updateSettings({ inference_provider: best.provider })");
        // Non-fatal: a failed sweep must not fail the install.
        expect(modelManagerSource).toContain('model_manager_device_skip');
    });

    it('cannot be dismissed mid-run', () => {
        expect(modelManagerSource).toContain('if (wizardBusy) return;');
    });
});
