import { describe, expect, it } from 'vitest';

import modelManagerSource from './ModelManager.svelte?raw';

describe('Model Manager post-install selection gate', () => {
    it('gates the activate button on validation', () => {
        // "Use this model" is only offered once the model is validated on this host.
        expect(modelManagerSource).toContain('ready && !active && validated');
        // The unvalidated branch offers validation instead of activation.
        expect(modelManagerSource).toContain('ready && !active && !validated');
        expect(modelManagerSource).toContain('model_manager_validate_to_enable');
        expect(modelManagerSource).toContain('onclick={() => handleValidate(model)}');
    });

    it('explains why an unvalidated model is not yet selectable', () => {
        expect(modelManagerSource).toContain('model_manager_validation_needed');
    });

    it('runs the guided flow through the shared DiagnosticDialog with two real stages', () => {
        expect(modelManagerSource).toContain("import DiagnosticDialog from '../../components/DiagnosticDialog.svelte'");
        expect(modelManagerSource).toContain('<DiagnosticDialog');
        expect(modelManagerSource).toContain('runSequentialDiagnostic');
        // Two ordered checks: it must run on this hardware, then it is enabled.
        expect(modelManagerSource).toContain("id: 'validate'");
        expect(modelManagerSource).toContain("id: 'enable'");
        // The validate stage calls the backend validate probe, the enable stage activates.
        expect(modelManagerSource).toContain('await validateModel(model.id)');
        expect(modelManagerSource).toContain('await activateModel(model.id)');
    });

    it('restores state honestly: the dialog cannot be dismissed mid-run', () => {
        expect(modelManagerSource).toContain('if (validationBusy) return;');
    });
});
