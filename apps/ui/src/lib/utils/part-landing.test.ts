import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { holdInPlace, whenSectionReady } from './part-landing';

/** A source the test drives: `fire()` reports to whatever is listening, as a ResizeObserver or the
 *  document's input events would. */
function source(): { listen: (report: () => void) => () => void; fire: () => void; listening: () => boolean } {
    let report: (() => void) | null = null;
    return {
        listen: (onReport) => {
            report = onReport;
            return () => {
                report = null;
            };
        },
        fire: () => report?.(),
        listening: () => report !== null
    };
}

describe('holdInPlace', () => {
    beforeEach(() => vi.useFakeTimers());
    afterEach(() => vi.useRealTimers());

    it('puts the part back in place every time the content around it changes size', () => {
        const resize = source();
        const intent = source();
        const place = vi.fn();
        holdInPlace({ watch: resize.listen, listenForIntent: intent.listen, place });
        resize.fire();
        resize.fire();
        expect(place).toHaveBeenCalledTimes(2);
    });

    it('lets go when the reader acts, so their own scroll or keys are never undone', () => {
        const resize = source();
        const intent = source();
        const place = vi.fn();
        holdInPlace({ watch: resize.listen, listenForIntent: intent.listen, place });
        intent.fire();
        resize.fire();
        expect(place).not.toHaveBeenCalled();
        expect(resize.listening()).toBe(false);
        expect(intent.listening()).toBe(false);
    });

    it('lets go after the longest hold, however slowly the content arrives', async () => {
        const resize = source();
        const intent = source();
        const place = vi.fn();
        holdInPlace({ watch: resize.listen, listenForIntent: intent.listen, place, maxMs: 3000 });
        await vi.advanceTimersByTimeAsync(2999);
        resize.fire();
        expect(place).toHaveBeenCalledTimes(1);
        await vi.advanceTimersByTimeAsync(1);
        resize.fire();
        expect(place).toHaveBeenCalledTimes(1);
        expect(resize.listening()).toBe(false);
    });

    it('stops at once when the caller stops it (a newer address, leaving the page)', () => {
        const resize = source();
        const intent = source();
        const place = vi.fn();
        const stop = holdInPlace({ watch: resize.listen, listenForIntent: intent.listen, place });
        stop();
        stop();
        resize.fire();
        expect(place).not.toHaveBeenCalled();
        expect(resize.listening()).toBe(false);
        expect(intent.listening()).toBe(false);
    });
});

/** Requests the test finishes by hand: `idle` reports at once when none is in flight. */
function requests(): { idle: (onIdle: () => void) => () => void; start: () => void; finish: () => void } {
    let inFlight = 0;
    const waiters = new Set<() => void>();
    return {
        idle: (onIdle) => {
            if (inFlight === 0) {
                onIdle();
                return () => {};
            }
            waiters.add(onIdle);
            return () => waiters.delete(onIdle);
        },
        start: () => {
            inFlight += 1;
        },
        finish: () => {
            inFlight -= 1;
            if (inFlight === 0) for (const onIdle of [...waiters].splice(0)) { waiters.delete(onIdle); onIdle(); }
        }
    };
}

describe('whenSectionReady', () => {
    beforeEach(() => vi.useFakeTimers());
    afterEach(() => vi.useRealTimers());

    it('is ready once the section has held its size for the quiet time with nothing in flight', async () => {
        const resize = source();
        const reads = requests();
        let ready: boolean | null = null;
        void whenSectionReady({ watch: resize.listen, requestsIdle: reads.idle, quietMs: 150, maxMs: 4000 }).then((value) => (ready = value));
        await vi.advanceTimersByTimeAsync(149);
        expect(ready).toBeNull();
        await vi.advanceTimersByTimeAsync(1);
        expect(ready).toBe(true);
        expect(resize.listening()).toBe(false);
    });

    it('waits for a slow read however long it takes, then for the section to settle after it', async () => {
        const resize = source();
        const reads = requests();
        reads.start();
        let ready: boolean | null = null;
        void whenSectionReady({ watch: resize.listen, requestsIdle: reads.idle, quietMs: 150, maxMs: 4000 }).then((value) => (ready = value));
        await vi.advanceTimersByTimeAsync(1500);
        expect(ready).toBeNull();
        reads.finish();
        resize.fire();
        await vi.advanceTimersByTimeAsync(149);
        expect(ready).toBeNull();
        await vi.advanceTimersByTimeAsync(1);
        expect(ready).toBe(true);
    });

    it('gives up waiting at the longest wait, and is ready then', async () => {
        const resize = source();
        const reads = requests();
        reads.start();
        let ready: boolean | null = null;
        void whenSectionReady({ watch: resize.listen, requestsIdle: reads.idle, quietMs: 150, maxMs: 4000 }).then((value) => (ready = value));
        await vi.advanceTimersByTimeAsync(4000);
        expect(ready).toBe(true);
    });

    it('answers not ready when the landing is called off while it waits', async () => {
        const resize = source();
        const reads = requests();
        reads.start();
        const called = new AbortController();
        let ready: boolean | null = null;
        void whenSectionReady({ watch: resize.listen, requestsIdle: reads.idle, signal: called.signal }).then((value) => (ready = value));
        called.abort();
        await vi.advanceTimersByTimeAsync(0);
        expect(ready).toBe(false);
        expect(resize.listening()).toBe(false);
    });
});
