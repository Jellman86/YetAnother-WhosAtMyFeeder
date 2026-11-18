import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { layoutSettled, type SizeWatcher } from './layout-settled';

/** A size watcher the test drives: `resize()` reports a change, as a ResizeObserver would. */
function fakeWatcher(): { watch: SizeWatcher; resize: () => void; stopped: () => boolean } {
    let report: (() => void) | null = null;
    let stopped = false;
    return {
        watch: (onResize) => {
            report = onResize;
            return () => {
                stopped = true;
                report = null;
            };
        },
        resize: () => report?.(),
        stopped: () => stopped
    };
}

describe('layoutSettled', () => {
    beforeEach(() => vi.useFakeTimers());
    afterEach(() => vi.useRealTimers());

    it('resolves once the size has held for the quiet time', async () => {
        const watcher = fakeWatcher();
        let settled = false;
        void layoutSettled(watcher.watch, { quietMs: 200, maxMs: 2000 }).then(() => (settled = true));
        await vi.advanceTimersByTimeAsync(199);
        expect(settled).toBe(false);
        await vi.advanceTimersByTimeAsync(1);
        expect(settled).toBe(true);
        expect(watcher.stopped()).toBe(true);
    });

    it('waits again after every change, so a part that grows late is waited for', async () => {
        const watcher = fakeWatcher();
        let settled = false;
        void layoutSettled(watcher.watch, { quietMs: 200, maxMs: 2000 }).then(() => (settled = true));
        await vi.advanceTimersByTimeAsync(150);
        watcher.resize();
        await vi.advanceTimersByTimeAsync(150);
        watcher.resize();
        await vi.advanceTimersByTimeAsync(199);
        expect(settled).toBe(false);
        await vi.advanceTimersByTimeAsync(1);
        expect(settled).toBe(true);
    });

    it('gives up waiting at the longest wait, so a page that never stops changing still lands', async () => {
        const watcher = fakeWatcher();
        let settled = false;
        void layoutSettled(watcher.watch, { quietMs: 200, maxMs: 1000 }).then(() => (settled = true));
        for (let elapsed = 0; elapsed < 900; elapsed += 100) {
            await vi.advanceTimersByTimeAsync(100);
            watcher.resize();
        }
        expect(settled).toBe(false);
        await vi.advanceTimersByTimeAsync(100);
        expect(settled).toBe(true);
        expect(watcher.stopped()).toBe(true);
    });
});
