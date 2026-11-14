import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { REFRESH_CADENCE_MS, SHELL_READINGS } from './refresh-cadence';
import { startVisiblePoll, type PollDocument } from './visible-poll';

/** A tab whose visibility the test controls, with the listeners the poll attaches to it. */
function fakeTab(): PollDocument & { show(): void; hide(): void; listeners(): number } {
    const listeners = new Set<() => void>();
    const tab = {
        hidden: false,
        addEventListener: (_type: 'visibilitychange', listener: () => void) => { listeners.add(listener); },
        removeEventListener: (_type: 'visibilitychange', listener: () => void) => { listeners.delete(listener); },
        show(): void { tab.hidden = false; for (const listener of [...listeners]) listener(); },
        hide(): void { tab.hidden = true; for (const listener of [...listeners]) listener(); },
        listeners: () => listeners.size
    };
    return tab;
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('startVisiblePoll', () => {
    it('reads at once, then once per cadence', async () => {
        const read = vi.fn(async () => {});
        const stop = startVisiblePoll({ read, delayMs: () => 15_000, tab: fakeTab() });

        expect(read).toHaveBeenCalledTimes(1);
        await vi.advanceTimersByTimeAsync(14_999);
        expect(read).toHaveBeenCalledTimes(1);
        await vi.advanceTimersByTimeAsync(1);
        expect(read).toHaveBeenCalledTimes(2);
        await vi.advanceTimersByTimeAsync(45_000);
        expect(read).toHaveBeenCalledTimes(5);
        stop();
    });

    it('waits a full cadence before the first read when the caller has already read', async () => {
        const read = vi.fn(async () => {});
        const stop = startVisiblePoll({ read, delayMs: () => 15_000, tab: fakeTab(), readAtStart: false });

        expect(read).not.toHaveBeenCalled();
        await vi.advanceTimersByTimeAsync(15_000);
        expect(read).toHaveBeenCalledTimes(1);
        stop();
    });

    it('stops reading while the tab is hidden and holds no timer', async () => {
        const tab = fakeTab();
        const read = vi.fn(async () => {});
        const stop = startVisiblePoll({ read, delayMs: () => 15_000, tab });
        await vi.advanceTimersByTimeAsync(0);

        tab.hide();
        expect(vi.getTimerCount()).toBe(0);
        await vi.advanceTimersByTimeAsync(10 * 60_000);
        expect(read).toHaveBeenCalledTimes(1);
        stop();
    });

    it('reads once as soon as the tab is shown again, then resumes its cadence', async () => {
        const tab = fakeTab();
        const read = vi.fn(async () => {});
        const stop = startVisiblePoll({ read, delayMs: () => 15_000, tab });
        await vi.advanceTimersByTimeAsync(0);
        tab.hide();
        await vi.advanceTimersByTimeAsync(60_000);

        tab.show();
        expect(read).toHaveBeenCalledTimes(2);
        await vi.advanceTimersByTimeAsync(15_000);
        expect(read).toHaveBeenCalledTimes(3);
        stop();
    });

    it('does not start while the tab is hidden, and starts when it is shown', async () => {
        const tab = fakeTab();
        tab.hide();
        const read = vi.fn(async () => {});
        const stop = startVisiblePoll({ read, delayMs: () => 15_000, tab });

        await vi.advanceTimersByTimeAsync(60_000);
        expect(read).not.toHaveBeenCalled();
        tab.show();
        expect(read).toHaveBeenCalledTimes(1);
        stop();
    });

    it('keeps its cadence after a read fails', async () => {
        const read = vi.fn<() => Promise<void>>()
            .mockRejectedValueOnce(new Error('backend away'))
            .mockResolvedValue(undefined);
        const stop = startVisiblePoll({ read, delayMs: () => 15_000, tab: fakeTab() });

        await vi.advanceTimersByTimeAsync(15_000);
        expect(read).toHaveBeenCalledTimes(2);
        await vi.advanceTimersByTimeAsync(15_000);
        expect(read).toHaveBeenCalledTimes(3);
        stop();
    });

    it('keeps its cadence after a read throws before it returns a promise', async () => {
        const read = vi.fn<() => void>().mockImplementationOnce(() => { throw new Error('not ready'); });
        const stop = startVisiblePoll({ read, delayMs: () => 15_000, tab: fakeTab() });

        await vi.advanceTimersByTimeAsync(15_000);
        expect(read).toHaveBeenCalledTimes(2);
        stop();
    });

    it('never overlaps a read that is still in flight, and counts the cadence from when it ends', async () => {
        let finish!: () => void;
        const tab = fakeTab();
        const read = vi.fn(() => new Promise<void>((resolve) => { finish = resolve; }));
        const stop = startVisiblePoll({ read, delayMs: () => 15_000, tab });

        await vi.advanceTimersByTimeAsync(60_000);
        tab.hide();
        tab.show();
        expect(read).toHaveBeenCalledTimes(1);

        finish();
        await vi.advanceTimersByTimeAsync(14_999);
        expect(read).toHaveBeenCalledTimes(1);
        await vi.advanceTimersByTimeAsync(1);
        expect(read).toHaveBeenCalledTimes(2);
        stop();
    });

    it('asks for the delay after every read, so a reader can follow active work more closely', async () => {
        let active = true;
        const read = vi.fn(async () => {});
        const stop = startVisiblePoll({ read, delayMs: () => (active ? 5_000 : 60_000), tab: fakeTab() });

        await vi.advanceTimersByTimeAsync(10_000);
        expect(read).toHaveBeenCalledTimes(3);
        active = false;
        await vi.advanceTimersByTimeAsync(5_000);
        expect(read).toHaveBeenCalledTimes(4);
        await vi.advanceTimersByTimeAsync(59_999);
        expect(read).toHaveBeenCalledTimes(4);
        await vi.advanceTimersByTimeAsync(1);
        expect(read).toHaveBeenCalledTimes(5);
        stop();
    });

    it('stops for good when stopped: no timer, no listener, and nothing after a read in flight lands', async () => {
        let finish!: () => void;
        const tab = fakeTab();
        const read = vi.fn(() => new Promise<void>((resolve) => { finish = resolve; }));
        const stop = startVisiblePoll({ read, delayMs: () => 15_000, tab });
        expect(tab.listeners()).toBe(1);

        stop();
        expect(tab.listeners()).toBe(0);
        finish();
        await vi.advanceTimersByTimeAsync(10 * 60_000);
        tab.show();
        expect(read).toHaveBeenCalledTimes(1);
        expect(vi.getTimerCount()).toBe(0);
    });

    it('stops cleanly when stopped between reads', async () => {
        const tab = fakeTab();
        const read = vi.fn(async () => {});
        const stop = startVisiblePoll({ read, delayMs: () => 15_000, tab });
        await vi.advanceTimersByTimeAsync(20_000);

        stop();
        stop();
        expect(vi.getTimerCount()).toBe(0);
        expect(tab.listeners()).toBe(0);
        await vi.advanceTimersByTimeAsync(10 * 60_000);
        expect(read).toHaveBeenCalledTimes(2);
    });
});

describe('the idle request budget, counted from running polls', () => {
    it('an idle owner page makes at most a dozen shell requests in a minute', async () => {
        let requests = 0;
        const stops = SHELL_READINGS.map(({ reading, requests: perRead }) =>
            startVisiblePoll({
                read: async () => { requests += perRead; },
                delayMs: () => REFRESH_CADENCE_MS[reading],
                tab: fakeTab(),
                readAtStart: false
            })
        );

        await vi.advanceTimersByTimeAsync(60_000);
        expect(requests).toBeLessThanOrEqual(12);
        // Over ten minutes every reading has fired, and the rate holds.
        await vi.advanceTimersByTimeAsync(9 * 60_000);
        expect(requests / 10).toBeLessThanOrEqual(12);
        expect(requests).toBeGreaterThan(0);
        for (const stop of stops) stop();
    });
});
