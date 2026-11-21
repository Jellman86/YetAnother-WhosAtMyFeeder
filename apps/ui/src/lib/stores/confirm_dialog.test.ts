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

    it('answers no, and never throws, when the alternative fails outright', async () => {
        const answer = confirmAction({
            title: 'Leave without saving?', message: 'm', confirmLabel: 'Leave without saving',
            alternative: { label: 'Save and leave', run: async () => { throw new Error('network down'); } }
        });
        await expect(confirmDialog.runAlternative()).resolves.toBeUndefined();
        expect(confirmDialog.current).toBeNull();
        await expect(answer).resolves.toBe(false);
    });
});

describe('a question that depends on a figure it has yet to read', () => {
    const counting = { title: 'Delete all history', message: 'Counting the detections…', confirmLabel: 'Delete all history permanently' };
    const unread = { message: 'Delete all detections? The number could not be read. This cannot be undone.' };

    function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void; reject: (reason: unknown) => void } {
        let resolve!: (value: T) => void;
        let reject!: (reason: unknown) => void;
        const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
        return { promise, resolve, reject };
    }

    it('opens at once saying what it is reading, and cannot be confirmed until the reading lands', async () => {
        const reading = deferred<{ message: string }>();
        let settled: boolean | 'open' = 'open';
        void confirmAction({ ...counting, reading: { read: () => reading.promise, unread } }).then((answer) => { settled = answer; });
        expect(confirmDialog.current?.message).toBe('Counting the detections…');
        expect(confirmDialog.current?.reading).toBe(true);

        confirmDialog.answer(true);
        await Promise.resolve();
        expect(settled).toBe('open');
        expect(confirmDialog.current?.reading).toBe(true);

        reading.resolve({ message: 'Delete all 931 detections? This cannot be undone.' });
        await reading.promise;
        await Promise.resolve();
        expect(confirmDialog.current?.reading).toBe(false);
        expect(confirmDialog.current?.message).toBe('Delete all 931 detections? This cannot be undone.');
        expect(confirmDialog.current?.confirmLabel).toBe('Delete all history permanently');

        confirmDialog.answer(true);
        await Promise.resolve();
        expect(settled).toBe(true);
    });

    it('asks without the figure when the reading fails', async () => {
        const answer = confirmAction({ ...counting, reading: { read: () => Promise.reject(new Error('503')), unread } });
        await Promise.resolve();
        await Promise.resolve();
        expect(confirmDialog.current?.reading).toBe(false);
        expect(confirmDialog.current?.message).toBe(unread.message);
        confirmDialog.answer(false);
        await expect(answer).resolves.toBe(false);
    });

    it('can be cancelled while it reads, and the late reading does not reopen it', async () => {
        const reading = deferred<{ message: string }>();
        const answer = confirmAction({ ...counting, reading: { read: () => reading.promise, unread } });
        confirmDialog.answer(false);
        await expect(answer).resolves.toBe(false);
        reading.resolve({ message: 'Delete all 931 detections?' });
        await reading.promise;
        await Promise.resolve();
        expect(confirmDialog.current).toBeNull();
    });

    it('does not put a late reading into a newer question', async () => {
        const reading = deferred<{ message: string }>();
        void confirmAction({ ...counting, reading: { read: () => reading.promise, unread } });
        void confirmAction(request);
        reading.resolve({ message: 'Delete all 931 detections?' });
        await reading.promise;
        await Promise.resolve();
        expect(confirmDialog.current?.message).toBe('Delete everything?');
        confirmDialog.answer(false);
    });
});
