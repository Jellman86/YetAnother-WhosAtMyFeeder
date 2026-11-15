import { describe, expect, it } from 'vitest';
import { confirmDialog, confirmAction } from './confirm_dialog.svelte';

const request = { title: 'Reset database', message: 'Delete everything?', confirmLabel: 'Reset database' };

describe('in-app confirmation', () => {
    it('shows the question and resolves with the answer', async () => {
        const answer = confirmAction(request);
        expect(confirmDialog.current?.message).toBe('Delete everything?');
        confirmDialog.answer(true);
        await expect(answer).resolves.toBe(true);
        expect(confirmDialog.current).toBeNull();
    });

    it('treats dismissing as cancel', async () => {
        const answer = confirmAction(request);
        confirmDialog.answer(false);
        await expect(answer).resolves.toBe(false);
    });

    it('never stacks questions: a newer request cancels the one still open', async () => {
        const first = confirmAction(request);
        const second = confirmAction({ ...request, message: 'Something else?' });
        await expect(first).resolves.toBe(false);
        expect(confirmDialog.current?.message).toBe('Something else?');
        confirmDialog.answer(true);
        await expect(second).resolves.toBe(true);
    });

    it('defaults to the destructive tone, since that is what it guards', () => {
        void confirmAction(request);
        expect(confirmDialog.current?.tone).toBe('danger');
        confirmDialog.answer(false);
    });

    it('lets a prompt name its safe answer, and says Cancel when it does not', () => {
        void confirmAction({ ...request, cancelLabel: 'Stay' });
        expect(confirmDialog.current?.cancelLabel).toBe('Stay');
        confirmDialog.answer(false);
        void confirmAction(request);
        // Empty means the dialog falls back to its translated Cancel.
        expect(confirmDialog.current?.cancelLabel).toBe('');
        confirmDialog.answer(false);
    });
});

describe('a question with a second way forward', () => {
    it('closes the question, runs the alternative and answers with its outcome', async () => {
        let ran = 0;
        const answer = confirmAction({
            title: 'Leave without saving?', message: '2 changes will be lost.', confirmLabel: 'Leave without saving',
            alternative: { label: 'Save and leave', run: async () => { ran += 1; return true; } }
        });
        expect(confirmDialog.current?.alternative?.label).toBe('Save and leave');
        await confirmDialog.runAlternative();
        expect(ran).toBe(1);
        expect(confirmDialog.current).toBeNull();
        await expect(answer).resolves.toBe(true);
    });

    it('answers no when the alternative did not work out, so the page stays', async () => {
        const answer = confirmAction({
            title: 'Leave without saving?', message: 'm', confirmLabel: 'Leave without saving',
            alternative: { label: 'Save and leave', run: async () => false }
        });
        await confirmDialog.runAlternative();
        await expect(answer).resolves.toBe(false);
    });
});
