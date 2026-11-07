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
        const stored = new Map<string, string>();
        vi.stubGlobal('localStorage', {
            getItem: (key: string) => stored.get(key) ?? null,
            setItem: (key: string, value: string) => void stored.set(key, value),
            removeItem: (key: string) => void stored.delete(key)
        });
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

    it('returns to review after completing, skipping, or backing out of a re-run section', () => {
        setupWizardStore.open('rerun');

        setupWizardStore.gotoStep('model');
        setupWizardStore.completeStep();
        expect(setupWizardStore.current.id).toBe('review');

        setupWizardStore.gotoStep('quality');
        setupWizardStore.skipStep();
        expect(setupWizardStore.current.id).toBe('review');

        setupWizardStore.gotoStep('integrations');
        setupWizardStore.leaveStep();
        expect(setupWizardStore.current.id).toBe('review');
    });

    it('keeps first-run completion, skip, and back navigation linear', () => {
        setupWizardStore.open('first_run');
        setupWizardStore.completeStep();
        expect(setupWizardStore.current.id).toBe('account');
        setupWizardStore.skipStep();
        expect(setupWizardStore.current.id).toBe('connection');
        setupWizardStore.leaveStep();
        expect(setupWizardStore.current.id).toBe('account');
    });

    it('exposes section readiness after refresh', async () => {
        await setupWizardStore.refresh();
        expect(setupWizardStore.statusFor('cameras')).toBe('ok');
        expect(setupWizardStore.statusFor('connection')).toBe('ok');
        expect(setupWizardStore.detailFor('connection')).toBe('http://frigate:5000');
        expect(setupWizardStore.statusFor(null)).toBeNull();
    });

    it('a section opened from Review in first run goes back to Review, on finishing or leaving it', () => {
        setupWizardStore.open('first_run');
        setupWizardStore.gotoStep('review');
        setupWizardStore.openFromReview('connection');
        expect(setupWizardStore.current.id).toBe('connection');
        setupWizardStore.completeStep();
        expect(setupWizardStore.current.id).toBe('review');

        setupWizardStore.openFromReview('cameras');
        setupWizardStore.leaveStep();
        expect(setupWizardStore.current.id).toBe('review');
    });

    it('walking through first run without Review still moves on step by step', () => {
        setupWizardStore.open('first_run');
        setupWizardStore.gotoStep('connection');
        setupWizardStore.completeStep();
        expect(setupWizardStore.current.id).toBe('cameras');
        setupWizardStore.leaveStep();
        expect(setupWizardStore.current.id).toBe('connection');
    });

    it('resumes an interrupted first run at the step it reached', () => {
        setupWizardStore.open('first_run');
        setupWizardStore.gotoStep('model');
        setupWizardStore.active = false;

        setupWizardStore.resumeInterrupted();

        expect(setupWizardStore.active).toBe(true);
        expect(setupWizardStore.mode).toBe('first_run');
        expect(setupWizardStore.current.id).toBe('model');
    });

    it('does not reopen once setup was finished or skipped', () => {
        setupWizardStore.open('first_run');
        setupWizardStore.gotoStep('model');
        setupWizardStore.close();

        setupWizardStore.resumeInterrupted();

        expect(setupWizardStore.active).toBe(false);
    });

    it('a re-run never leaves anything to resume', () => {
        setupWizardStore.open('rerun');
        setupWizardStore.gotoStep('model');
        setupWizardStore.close();

        setupWizardStore.resumeInterrupted();

        expect(setupWizardStore.active).toBe(false);
    });
});
