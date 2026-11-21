import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import { holdInPlace, watchElementSizes, whenSectionReady } from './part-landing';

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

    /** A part whose top the test moves, and the scrolls the hold asks for. */
    function part(top = 0): { position: () => number; move: (to: number) => void; scrollBy: Mock<(by: number) => void> } {
        let current = top;
        const scrollBy = vi.fn<(by: number) => void>((by) => {
            current -= by;
        });
        return { position: () => current, move: (to) => (current = to), scrollBy };
    }

    it('puts the part back where it landed by however far something has moved it', () => {
        const change = source();
        const intent = source();
        const landed = part();
        holdInPlace({ watch: change.listen, listenForIntent: intent.listen, position: landed.position, scrollBy: landed.scrollBy });
        // The shell's jobs strip appears above the section, 103px tall.
        landed.move(103);
        change.fire();
        expect(landed.scrollBy).toHaveBeenCalledWith(103);
        expect(landed.position()).toBe(0);
    });

    it('scrolls nothing when a change has not moved the part', () => {
        const change = source();
        const intent = source();
        const landed = part();
        holdInPlace({ watch: change.listen, listenForIntent: intent.listen, position: landed.position, scrollBy: landed.scrollBy });
        change.fire();
        landed.move(0.4);
        change.fire();
        expect(landed.scrollBy).not.toHaveBeenCalled();
    });

    it('lets go when the reader acts, so their own scroll or keys are never undone', () => {
        const change = source();
        const intent = source();
        const landed = part();
        holdInPlace({ watch: change.listen, listenForIntent: intent.listen, position: landed.position, scrollBy: landed.scrollBy });
        intent.fire();
        landed.move(103);
        change.fire();
        expect(landed.scrollBy).not.toHaveBeenCalled();
        expect(change.listening()).toBe(false);
        expect(intent.listening()).toBe(false);
    });

    it('lets go after the longest hold, however slowly the content arrives', async () => {
        const change = source();
        const intent = source();
        const landed = part();
        holdInPlace({ watch: change.listen, listenForIntent: intent.listen, position: landed.position, scrollBy: landed.scrollBy, maxMs: 3000 });
        await vi.advanceTimersByTimeAsync(2999);
        landed.move(50);
        change.fire();
        expect(landed.scrollBy).toHaveBeenCalledTimes(1);
        await vi.advanceTimersByTimeAsync(1);
        landed.move(50);
        change.fire();
        expect(landed.scrollBy).toHaveBeenCalledTimes(1);
        expect(change.listening()).toBe(false);
    });

    it('stops at once when the caller stops it (a newer address, leaving the page)', () => {
        const change = source();
        const intent = source();
        const landed = part();
        const stop = holdInPlace({ watch: change.listen, listenForIntent: intent.listen, position: landed.position, scrollBy: landed.scrollBy });
        stop();
        stop();
        landed.move(103);
        change.fire();
        expect(landed.scrollBy).not.toHaveBeenCalled();
        expect(change.listening()).toBe(false);
        expect(intent.listening()).toBe(false);
    });

    it('stops when the part is gone', () => {
        const change = source();
        const intent = source();
        let gone = false;
        const scrollBy = vi.fn<(by: number) => void>();
        holdInPlace({ watch: change.listen, listenForIntent: intent.listen, position: () => (gone ? null : 0), scrollBy });
        gone = true;
        change.fire();
        expect(scrollBy).not.toHaveBeenCalled();
        expect(change.listening()).toBe(false);
    });
});

describe('watchElementSizes', () => {
    it('reports a change of any of the elements, and stops watching them all', () => {
        const observed: Element[] = [];
        let report: () => void = () => {};
        let disconnected = false;
        class FakeResizeObserver {
            constructor(callback: () => void) {
                report = callback;
            }
            observe(element: Element): void {
                observed.push(element);
            }
            disconnect(): void {
                disconnected = true;
            }
        }
        vi.stubGlobal('ResizeObserver', FakeResizeObserver);
        const section = {} as Element;
        const page = {} as Element;
        const onChange = vi.fn();
        const stop = watchElementSizes(section, page)(onChange);
        expect(observed).toEqual([section, page]);
        report();
        expect(onChange).toHaveBeenCalledTimes(1);
        stop();
        expect(disconnected).toBe(true);
        vi.unstubAllGlobals();
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
