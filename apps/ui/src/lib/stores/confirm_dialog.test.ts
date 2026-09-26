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
});
