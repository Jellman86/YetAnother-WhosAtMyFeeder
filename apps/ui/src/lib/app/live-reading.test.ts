import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { RECONNECT_MIN_MS, startLiveReading } from './live-reading';
import type { PollDocument } from './visible-poll';

function fakeTab(): PollDocument & { show(): void; hide(): void } {
    const listeners = new Set<() => void>();
    const tab = {
        hidden: false,
        addEventListener: (_type: 'visibilitychange', listener: () => void) => { listeners.add(listener); },
        removeEventListener: (_type: 'visibilitychange', listener: () => void) => { listeners.delete(listener); },
        show(): void { tab.hidden = false; for (const listener of [...listeners]) listener(); },
        hide(): void { tab.hidden = true; for (const listener of [...listeners]) listener(); }
    };
    return tab;
}

const POLL = 15_000;
const QUIET = 300_000;

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('startLiveReading', () => {
    it('polls at the reading\'s own cadence while the live stream does not cover it', async () => {
        const read = vi.fn(async () => {});
        const reading = startLiveReading({ read, live: () => false, pollMs: () => POLL, quietMs: QUIET, tab: fakeTab() });

        expect(read).toHaveBeenCalledTimes(1);
        await vi.advanceTimersByTimeAsync(POLL * 4);
        expect(read).toHaveBeenCalledTimes(5);
        reading.stop();
    });

    it('reads nothing while the live stream covers it and nothing changes, except a slow safety read', async () => {
        const read = vi.fn(async () => {});
        const reading = startLiveReading({ read, live: () => true, pollMs: () => POLL, quietMs: QUIET, tab: fakeTab() });

        await vi.advanceTimersByTimeAsync(QUIET - 1);
        expect(read).toHaveBeenCalledTimes(1);
        await vi.advanceTimersByTimeAsync(1);
        expect(read).toHaveBeenCalledTimes(2);
        reading.stop();
    });

    it('reads an announced change at once after a quiet spell', async () => {
        const read = vi.fn(async () => {});
        const reading = startLiveReading({ read, live: () => true, pollMs: () => POLL, quietMs: QUIET, tab: fakeTab() });
        await vi.advanceTimersByTimeAsync(60_000);

        reading.changed();
        await vi.advanceTimersByTimeAsync(0);
        expect(read).toHaveBeenCalledTimes(2);
        reading.stop();
    });

    it('reads a burst of announcements no more often than the reading\'s own cadence, and never drops the last', async () => {
        const read = vi.fn(async () => {});
        const reading = startLiveReading({ read, live: () => true, pollMs: () => POLL, quietMs: QUIET, tab: fakeTab() });
        await vi.advanceTimersByTimeAsync(1_000);

        reading.changed();
        await vi.advanceTimersByTimeAsync(5_000);
        reading.changed();
        reading.changed();
        await vi.advanceTimersByTimeAsync(POLL - 1_000 - 5_000 - 1);
        expect(read).toHaveBeenCalledTimes(1);
        await vi.advanceTimersByTimeAsync(1);
        expect(read).toHaveBeenCalledTimes(2);
        await vi.advanceTimersByTimeAsync(POLL * 2);
        expect(read).toHaveBeenCalledTimes(2);
        reading.stop();
    });

    it('goes back to polling as soon as the live stream stops covering it', async () => {
        let live = true;
        const read = vi.fn(async () => {});
        const reading = startLiveReading({ read, live: () => live, pollMs: () => POLL, quietMs: QUIET, tab: fakeTab() });
        await vi.advanceTimersByTimeAsync(60_000);

        live = false;
        reading.liveChanged();
        await vi.advanceTimersByTimeAsync(0);
        // Changes may have been missed while the stream went down, so it reads straight away.
        expect(read).toHaveBeenCalledTimes(2);
        await vi.advanceTimersByTimeAsync(POLL);
        expect(read).toHaveBeenCalledTimes(3);
        reading.stop();
    });

    it('is told about the stream before it connects without counting that as a missed change', async () => {
        // A view reports the stream's state as it mounts, while the stream is still connecting.
        let live = false;
        const read = vi.fn(async () => {});
        const reading = startLiveReading({ read, live: () => live, pollMs: () => POLL, quietMs: QUIET, tab: fakeTab(), readAtStart: false });
        reading.liveChanged();
        live = true;
        reading.liveChanged();

        await vi.advanceTimersByTimeAsync(QUIET - 1);
        expect(read).not.toHaveBeenCalled();
        await vi.advanceTimersByTimeAsync(1);
        expect(read).toHaveBeenCalledTimes(1);
        reading.stop();
    });

    it('holds no timer while the tab is hidden, and reads once when it is shown', async () => {
        const tab = fakeTab();
        const read = vi.fn(async () => {});
        const reading = startLiveReading({ read, live: () => true, pollMs: () => POLL, quietMs: QUIET, tab });
        await vi.advanceTimersByTimeAsync(0);

        tab.hide();
        reading.changed();
        expect(vi.getTimerCount()).toBe(0);
        await vi.advanceTimersByTimeAsync(QUIET * 2);
        expect(read).toHaveBeenCalledTimes(1);

        tab.show();
        await vi.advanceTimersByTimeAsync(0);
        expect(read).toHaveBeenCalledTimes(2);
        reading.stop();
    });

    it('follows an announcement that lands during a read with one more read, not an overlapping one', async () => {
        let finish: () => void = () => {};
        const read = vi.fn()
            .mockImplementationOnce(() => new Promise<void>((done) => { finish = done; }))
            .mockResolvedValue(undefined);
        const reading = startLiveReading({ read, live: () => true, pollMs: () => POLL, quietMs: QUIET, tab: fakeTab() });

        reading.changed();
        expect(read).toHaveBeenCalledTimes(1);
        finish();
        await vi.advanceTimersByTimeAsync(POLL);
        expect(read).toHaveBeenCalledTimes(2);
        reading.stop();
    });

    it('keeps the shortest gap after the caller\'s own read when it has just read', async () => {
        const read = vi.fn(async () => {});
        const reading = startLiveReading({ read, live: () => true, pollMs: () => POLL, quietMs: QUIET, tab: fakeTab(), readAtStart: false });

        expect(read).not.toHaveBeenCalled();
        reading.changed();
        await vi.advanceTimersByTimeAsync(POLL - 1);
        expect(read).not.toHaveBeenCalled();
        await vi.advanceTimersByTimeAsync(1);
        expect(read).toHaveBeenCalledTimes(1);
        reading.stop();
    });

    it('reads again as soon as the stream reconnects, since a change may have gone unannounced while it was down', async () => {
        let live = true;
        const read = vi.fn(async () => true);
        const reading = startLiveReading({ read, live: () => live, pollMs: () => 60_000, quietMs: QUIET, tab: fakeTab() });
        await vi.advanceTimersByTimeAsync(30_000);

        live = false;
        reading.liveChanged();
        // Down: back to the poll, a minute after the last read.
        await vi.advanceTimersByTimeAsync(30_000);
        expect(read).toHaveBeenCalledTimes(2);
        await vi.advanceTimersByTimeAsync(1_000);
        live = true;
        reading.liveChanged();
        // The last read was a second ago, so the reconnect read waits for the 10 s minimum.
        await vi.advanceTimersByTimeAsync(RECONNECT_MIN_MS - 1_001);
        expect(read).toHaveBeenCalledTimes(2);
        await vi.advanceTimersByTimeAsync(1);
        expect(read).toHaveBeenCalledTimes(3);
        reading.stop();
    });

    it('reads at once on a reconnect when the last read is older than the minimum interval', async () => {
        let live = true;
        const read = vi.fn(async () => true);
        const reading = startLiveReading({ read, live: () => live, pollMs: () => 60_000, quietMs: QUIET, tab: fakeTab() });
        live = false;
        reading.liveChanged();
        await vi.advanceTimersByTimeAsync(30_000);
        live = true;
        reading.liveChanged();
        await vi.advanceTimersByTimeAsync(0);
        expect(read).toHaveBeenCalledTimes(2);
        reading.stop();
    });

    it.each([true, false])('keeps a flapping stream to the minimum interval (reads succeed: %s)', async (succeeds) => {
        // Five reconnects in five seconds gave six reads before.
        let live = true;
        const read = vi.fn(async () => succeeds);
        const reading = startLiveReading({ read, live: () => live, pollMs: () => 60_000, quietMs: QUIET, tab: fakeTab() });
        await vi.advanceTimersByTimeAsync(30_000);
        for (let flap = 0; flap < 5; flap += 1) {
            live = false;
            reading.liveChanged();
            await vi.advanceTimersByTimeAsync(500);
            live = true;
            reading.liveChanged();
            await vi.advanceTimersByTimeAsync(500);
        }
        // The start read, then at most one reconnect read.
        expect(read.mock.calls.length).toBeLessThanOrEqual(2);
        reading.stop();
    });

    it('backs off after reads that keep failing, and a reconnect does not get past the backoff', async () => {
        let live = true;
        const read = vi.fn(async () => false);
        const reading = startLiveReading({ read, live: () => live, pollMs: () => POLL, quietMs: QUIET, tab: fakeTab() });
        // Failed at 0, retried at 15 s (fails), then 30 s later at 45 s, then 60 s later at 105 s.
        await vi.advanceTimersByTimeAsync(15_000);
        expect(read).toHaveBeenCalledTimes(2);
        await vi.advanceTimersByTimeAsync(29_000);
        live = false;
        reading.liveChanged();
        live = true;
        reading.liveChanged();
        await vi.advanceTimersByTimeAsync(0);
        expect(read).toHaveBeenCalledTimes(2);
        await vi.advanceTimersByTimeAsync(1_000);
        expect(read).toHaveBeenCalledTimes(3);
        await vi.advanceTimersByTimeAsync(59_999);
        expect(read).toHaveBeenCalledTimes(3);
        await vi.advanceTimersByTimeAsync(1);
        expect(read).toHaveBeenCalledTimes(4);
        reading.stop();
    });

    it('counts a read the view took itself: a failure is retried at the cadence, a success restarts the quiet interval', async () => {
        const read = vi.fn(async () => true);
        const reading = startLiveReading({ read, live: () => true, pollMs: () => POLL, quietMs: QUIET, tab: fakeTab(), readAtStart: false });
        reading.report(false);
        await vi.advanceTimersByTimeAsync(POLL);
        expect(read).toHaveBeenCalledTimes(1);

        await vi.advanceTimersByTimeAsync(QUIET - 60_000);
        reading.report(true);
        await vi.advanceTimersByTimeAsync(QUIET - 1);
        expect(read).toHaveBeenCalledTimes(1);
        await vi.advanceTimersByTimeAsync(1);
        expect(read).toHaveBeenCalledTimes(2);
        reading.stop();
    });

    it('leaves a read it is taking itself to say how it went', async () => {
        let finish: (fresh: boolean) => void = () => {};
        const read = vi.fn().mockImplementationOnce(() => new Promise<boolean>((done) => { finish = done; })).mockResolvedValue(true);
        const reading = startLiveReading({ read, live: () => true, pollMs: () => POLL, quietMs: QUIET, tab: fakeTab() });
        reading.report(true);
        finish(false);
        await vi.advanceTimersByTimeAsync(POLL);
        expect(read).toHaveBeenCalledTimes(2);
        reading.stop();
    });

    it('does not count a failed read as fresh: the stream reconnecting after it does not wait for the safety read', async () => {
        // The reviewer's case: the fallback read fails at 60 s and the stream comes back at 61 s.
        let live = false;
        const read = vi.fn().mockResolvedValueOnce(true).mockResolvedValueOnce(false).mockResolvedValue(true);
        const reading = startLiveReading({ read, live: () => live, pollMs: () => 60_000, quietMs: QUIET, tab: fakeTab() });
        await vi.advanceTimersByTimeAsync(60_000);
        expect(read).toHaveBeenCalledTimes(2);

        await vi.advanceTimersByTimeAsync(1_000);
        live = true;
        reading.liveChanged();
        await vi.advanceTimersByTimeAsync(60_000);
        expect(read).toHaveBeenCalledTimes(3);
        reading.stop();
    });

    it('retries a failed read at the reading\'s own cadence while the stream is connected, not after the quiet interval', async () => {
        const read = vi.fn().mockResolvedValueOnce(false).mockResolvedValue(true);
        const reading = startLiveReading({ read, live: () => true, pollMs: () => POLL, quietMs: QUIET, tab: fakeTab() });
        await vi.advanceTimersByTimeAsync(POLL);
        expect(read).toHaveBeenCalledTimes(2);
        await vi.advanceTimersByTimeAsync(POLL * 3);
        expect(read).toHaveBeenCalledTimes(2);
        reading.stop();
    });

    it('tells the reader whether the read answers an announcement, so it can read what the announcement concerns', async () => {
        const read = vi.fn(async (_reason: { announced: boolean }) => true);
        const reading = startLiveReading({ read, live: () => true, pollMs: () => POLL, quietMs: QUIET, tab: fakeTab(), readAtStart: false });
        reading.changed();
        await vi.advanceTimersByTimeAsync(POLL);
        expect(read).toHaveBeenLastCalledWith({ announced: true });
        await vi.advanceTimersByTimeAsync(QUIET);
        expect(read).toHaveBeenLastCalledWith({ announced: false });
        reading.stop();
    });

    it('stops for good', async () => {
        const read = vi.fn(async () => {});
        const reading = startLiveReading({ read, live: () => false, pollMs: () => POLL, quietMs: QUIET, tab: fakeTab() });
        reading.stop();
        reading.changed();
        await vi.advanceTimersByTimeAsync(QUIET);
        expect(read).toHaveBeenCalledTimes(1);
        expect(vi.getTimerCount()).toBe(0);
    });
});
