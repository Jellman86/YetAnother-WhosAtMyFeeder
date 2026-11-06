import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { toastStore } from './toast.svelte';

function ids(): string[] {
    return toastStore.toasts.map((toast) => toast.id);
}

describe('toastStore', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        // The duplicate guard compares against the previous toast's time.
        vi.setSystemTime(new Date('2026-10-30T12:00:00Z'));
        toastStore.clear();
    });

    afterEach(() => {
        toastStore.clear();
        vi.useRealTimers();
    });

    it('removes a success toast after its duration', () => {
        const id = toastStore.success('Saved');
        vi.advanceTimersByTime(4_999);
        expect(ids()).toContain(id);
        vi.advanceTimersByTime(1);
        expect(ids()).not.toContain(id);
    });

    it('keeps an error until it is dismissed, whatever duration was asked for', () => {
        const id = toastStore.error('Could not save', 3_000);
        vi.advanceTimersByTime(60_000);
        expect(ids()).toContain(id);
        toastStore.remove(id);
        expect(ids()).not.toContain(id);
    });

    it('marks errors as persistent so the view can say so', () => {
        const errorId = toastStore.error('Failed');
        const infoId = toastStore.info('Heads up');
        const byId = new Map(toastStore.toasts.map((toast) => [toast.id, toast]));
        expect(byId.get(errorId)?.persistent).toBe(true);
        expect(byId.get(infoId)?.persistent).toBe(false);
    });

    it('holds a toast while it is paused and gives back the time that was left', () => {
        const id = toastStore.warning('Check this', 5_000);
        vi.advanceTimersByTime(3_000);
        toastStore.pause(id);
        vi.advanceTimersByTime(30_000);
        expect(ids()).toContain(id);
        toastStore.resume(id);
        vi.advanceTimersByTime(1_999);
        expect(ids()).toContain(id);
        vi.advanceTimersByTime(1);
        expect(ids()).not.toContain(id);
    });

    it('ignores a second pause and a resume without a pause', () => {
        const id = toastStore.info('Note', 5_000);
        toastStore.resume(id);
        vi.advanceTimersByTime(2_000);
        toastStore.pause(id);
        vi.advanceTimersByTime(1_000);
        toastStore.pause(id);
        toastStore.resume(id);
        vi.advanceTimersByTime(2_999);
        expect(ids()).toContain(id);
        vi.advanceTimersByTime(1);
        expect(ids()).not.toContain(id);
    });

    it('never schedules removal of a paused error when it is resumed', () => {
        const id = toastStore.error('Failed');
        toastStore.pause(id);
        toastStore.resume(id);
        vi.advanceTimersByTime(60_000);
        expect(ids()).toContain(id);
    });

    it('does not stack a repeat of an error that is still on screen', () => {
        const first = toastStore.error('Backend unreachable');
        vi.advanceTimersByTime(10_000);
        expect(toastStore.error('Backend unreachable')).toBe(first);
        expect(ids()).toEqual([first]);
    });

    it('does not resurrect a removed toast when its timer would have fired', () => {
        const id = toastStore.success('Saved', 1_000);
        toastStore.remove(id);
        const next = toastStore.success('Saved again', 5_000);
        vi.advanceTimersByTime(1_000);
        expect(ids()).toEqual([next]);
    });

    it('offers an undo for ten seconds, and running it removes the toast', () => {
        const undo = vi.fn();
        const id = toastStore.undoable('Cleared 3 notifications.', 'Undo', undo);
        const toast = toastStore.toasts.find((entry) => entry.id === id);
        expect(toast?.action?.label).toBe('Undo');
        expect(toast?.persistent).toBe(false);

        vi.advanceTimersByTime(9_999);
        expect(ids()).toContain(id);
        toastStore.runAction(id);
        expect(undo).toHaveBeenCalledTimes(1);
        expect(ids()).not.toContain(id);
    });

    it('lets an undo lapse once its ten seconds are up', () => {
        const undo = vi.fn();
        const id = toastStore.undoable('Cleared 1 notification.', 'Undo', undo);
        vi.advanceTimersByTime(10_000);
        expect(ids()).not.toContain(id);
        toastStore.runAction(id);
        expect(undo).not.toHaveBeenCalled();
    });
});
