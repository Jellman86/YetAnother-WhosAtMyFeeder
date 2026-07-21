import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/setup', () => ({
    fetchSetupState: vi.fn(async () => ({
        initial_setup_complete: false,
        sections: [
            { id: 'account', status: 'attention', detail: 'Not configured' },
            { id: 'connection', status: 'ok', detail: 'http://frigate:5000' },
            { id: 'cameras', status: 'ok', detail: 'All cameras' },
            { id: 'model', status: 'ok', detail: 'rope_vit_b14_inat21' },
            { id: 'quality', status: 'ok', detail: null },
            { id: 'integrations', status: 'optional', detail: 'None enabled' }
        ]
    }))
}));

import { setupWizardStore, WIZARD_STEPS } from './setup_wizard.svelte';

describe('setupWizardStore', () => {
    beforeEach(() => {
        setupWizardStore.close();
        setupWizardStore.setupState = null;
        setupWizardStore.goto(0);
    });

    it('first-run mode opens at the first step', () => {
        setupWizardStore.open('first_run');
        expect(setupWizardStore.index).toBe(0);
        expect(setupWizardStore.current.id).toBe('welcome');
        expect(setupWizardStore.isFirst).toBe(true);
    });

    it('re-run mode opens on the review/section-map step', () => {
        setupWizardStore.open('rerun');
        expect(setupWizardStore.current.id).toBe('review');
        expect(setupWizardStore.mode).toBe('rerun');
    });

    it('clamps navigation at both ends', () => {
        setupWizardStore.goto(0);
        setupWizardStore.back();
        expect(setupWizardStore.index).toBe(0);
        setupWizardStore.goto(WIZARD_STEPS.length - 1);
        setupWizardStore.next();
        expect(setupWizardStore.index).toBe(WIZARD_STEPS.length - 1);
        expect(setupWizardStore.isLast).toBe(true);
    });

    it('reports position and progress for the stepper', () => {
        setupWizardStore.goto(0);
        expect(setupWizardStore.position).toBe(1);
        expect(setupWizardStore.progress).toBe(0);
        setupWizardStore.goto(WIZARD_STEPS.length - 1);
        expect(setupWizardStore.progress).toBe(1);
    });

    it('jumps to a step by id (re-run section map)', () => {
        setupWizardStore.gotoStep('model');
        expect(setupWizardStore.current.id).toBe('model');
    });

    it('exposes section readiness after refresh', async () => {
        await setupWizardStore.refresh();
        expect(setupWizardStore.statusFor('cameras')).toBe('ok');
        expect(setupWizardStore.statusFor('connection')).toBe('ok');
        expect(setupWizardStore.detailFor('connection')).toBe('http://frigate:5000');
        expect(setupWizardStore.statusFor(null)).toBeNull();
    });
});
