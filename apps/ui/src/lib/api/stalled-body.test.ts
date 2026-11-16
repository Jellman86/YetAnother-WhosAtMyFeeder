import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { analyzeDetection, fetchClassifierStatus } from './classifier';
import { apiFetchJson, fetchWithAbort } from './core';
import { fetchDiagnosticsWorkspace } from './diagnostics';
import { checkHealth, fetchSystemTelemetry, fetchSystemTelemetryHistory } from './system';
import { fetchVisitCaptures, fetchVisits } from './visits';

/**
 * Every read that feeds a retrying reader, against a network that sends headers and then stalls
 * the body, as a proxy holding a response does. Aborting the request errors its body, as fetch
 * does, so a read whose timeout or cancel stops at the headers stays pending here for ever.
 */
let requests: AbortSignal[] = [];

function stalledBodyFetch(): typeof fetch {
    return ((_url: RequestInfo | URL, init?: RequestInit) => {
        const signal = init?.signal ?? new AbortController().signal;
        requests.push(signal);
        const body = new ReadableStream<Uint8Array>({
            start(controller) {
                controller.enqueue(new TextEncoder().encode('{"partial": '));
                signal.addEventListener('abort', () => controller.error(new DOMException('The operation was aborted.', 'AbortError')));
            }
        });
        return Promise.resolve(new Response(body, { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }) as typeof fetch;
}

beforeEach(() => {
    requests = [];
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-11-16T12:00:00Z'));
    vi.stubGlobal('fetch', stalledBodyFetch());
});

afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
});

/** Headers for a gateway's HTML error page, then a body that never ends; records when it is cancelled. */
let cancelledBodies = 0;

function stalledErrorPageFetch(): typeof fetch {
    return ((_url: RequestInfo | URL, init?: RequestInit) => {
        requests.push(init?.signal ?? new AbortController().signal);
        const body = new ReadableStream<Uint8Array>({
            start(controller) {
                controller.enqueue(new TextEncoder().encode('<html><body>Service Unavailable'));
            },
            cancel() {
                cancelledBodies += 1;
            }
        });
        return Promise.resolve(new Response(body, { status: 503, headers: { 'Content-Type': 'text/html' } }));
    }) as typeof fetch;
}

const SIX_READS = [
    ['the incident workspace', () => fetchDiagnosticsWorkspace(), 15_000],
    ["Health's visits", () => fetchVisits({ startTime: '2026-11-16T00:00:00Z', endTime: '2026-11-16T12:00:00Z', requestKey: 'health:visits', timeoutMs: 15_000 }), 15_000],
    ['the classifier status', () => fetchClassifierStatus(), 10_000],
    ['the backend health', () => checkHealth(), 10_000],
    ['the telemetry history', () => fetchSystemTelemetryHistory(), 5_000],
    ['the telemetry sample', () => fetchSystemTelemetry(), 2_500]
] as const;

async function expectTimedOut(read: Promise<unknown>, timeoutMs: number): Promise<void> {
    const outcome = read.then(() => 'resolved', () => 'rejected');
    await vi.advanceTimersByTimeAsync(timeoutMs + 1);
    expect(requests[0]?.aborted).toBe(true);
    await expect(outcome).resolves.toBe('rejected');
}

describe('a read whose body stalls after its headers is still timed out', () => {
    it.each(SIX_READS)('%s', async (_name, read, timeoutMs) => {
        await expectTimedOut(read(), timeoutMs);
    });
});

describe('a read whose body stalls after its headers is still cancellable', () => {
    it('the telemetry history, when its page is closed', async () => {
        const controller = new AbortController();
        const outcome = fetchSystemTelemetryHistory(controller.signal).then(() => 'resolved', () => 'rejected');
        await vi.advanceTimersByTimeAsync(0);
        controller.abort();
        await vi.advanceTimersByTimeAsync(0);
        expect(requests[0]?.aborted).toBe(true);
        await expect(outcome).resolves.toBe('rejected');
    });

    it("Health's visits, when a newer read with the same request key replaces it", async () => {
        const window = { startTime: '2026-11-16T00:00:00Z', endTime: '2026-11-16T12:00:00Z', requestKey: 'health:visits', timeoutMs: 15_000 };
        const first = fetchVisits(window).then(() => 'resolved', () => 'rejected');
        await vi.advanceTimersByTimeAsync(0);
        void fetchVisits(window).catch(() => undefined);
        await vi.advanceTimersByTimeAsync(0);
        expect(requests[0]?.aborted).toBe(true);
        await expect(first).resolves.toBe('rejected');
    });
});

describe("a reader's cancel reaches the request it is waiting on", () => {
    const window = { startTime: '2026-11-16T00:00:00Z', endTime: '2026-11-16T12:00:00Z', requestKey: 'health:visits', timeoutMs: 15_000 };

    it("Health's visits, while keeping its request key", async () => {
        const controller = new AbortController();
        const first = fetchVisits({ ...window, signal: controller.signal }).then(() => 'resolved', () => 'rejected');
        await vi.advanceTimersByTimeAsync(0);
        controller.abort();
        await vi.advanceTimersByTimeAsync(0);
        expect(requests[0]?.aborted).toBe(true);
        await expect(first).resolves.toBe('rejected');

        // The key still holds: a newer read with it replaces an older one made with a signal.
        const older = fetchVisits({ ...window, signal: new AbortController().signal }).then(() => 'resolved', () => 'rejected');
        await vi.advanceTimersByTimeAsync(0);
        void fetchVisits(window).catch(() => undefined);
        await vi.advanceTimersByTimeAsync(0);
        expect(requests[1]?.aborted).toBe(true);
        await expect(older).resolves.toBe('rejected');
    });

    it('the classifier status, when the Models tab closes', async () => {
        const controller = new AbortController();
        const outcome = fetchClassifierStatus(controller.signal).then(() => 'resolved', () => 'rejected');
        await vi.advanceTimersByTimeAsync(0);
        controller.abort();
        await vi.advanceTimersByTimeAsync(0);
        expect(requests[0]?.aborted).toBe(true);
        await expect(outcome).resolves.toBe('rejected');
    });

    it('a keyed read made with a signal answers to both', async () => {
        const controller = new AbortController();
        const outcome = fetchWithAbort('both', '/api/x', { signal: controller.signal, timeoutMs: 60_000 }).then(() => 'resolved', () => 'rejected');
        await vi.advanceTimersByTimeAsync(0);
        controller.abort();
        await vi.advanceTimersByTimeAsync(0);
        expect(requests[0]?.aborted).toBe(true);
        await expect(outcome).resolves.toBe('rejected');
    });
});

describe('an error page whose body stalls is cancelled, not left open', () => {
    beforeEach(() => {
        cancelledBodies = 0;
        vi.stubGlobal('fetch', stalledErrorPageFetch());
    });

    it.each(SIX_READS)('%s', async (_name, read) => {
        const outcome = read().then(() => 'resolved', () => 'rejected');
        await vi.advanceTimersByTimeAsync(0);
        await expect(outcome).resolves.toBe('rejected');
        expect(cancelledBodies).toBe(1);
    });
});

describe('every guarded read has a deadline', () => {
    it.each([0, -1, Number.NaN, Number.POSITIVE_INFINITY])('a timeout of %s is replaced by the default', async (timeoutMs) => {
        const outcome = apiFetchJson('/api/x', { timeoutMs }).then(() => 'resolved', () => 'rejected');
        await vi.advanceTimersByTimeAsync(10 * 60_000);
        expect(requests[0]?.aborted).toBe(true);
        await expect(outcome).resolves.toBe('rejected');
    });

    it('a keyed read too', async () => {
        const outcome = fetchWithAbort('untimed', '/api/x', { timeoutMs: 0 }).then(() => 'resolved', () => 'rejected');
        await vi.advanceTimersByTimeAsync(10 * 60_000);
        expect(requests[0]?.aborted).toBe(true);
        await expect(outcome).resolves.toBe('rejected');
    });
});

/** Ends exactly at its deadline: still open a millisecond before, aborted at it. */
async function expectDeadline(read: Promise<unknown>, deadlineMs: number): Promise<void> {
    const outcome = read.then(() => 'resolved', () => 'rejected');
    await vi.advanceTimersByTimeAsync(deadlineMs - 1);
    expect(requests[0]?.aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    expect(requests[0]?.aborted).toBe(true);
    await expect(outcome).resolves.toBe('rejected');
}

describe('each untimed read has the deadline it was given', () => {
    it.each([
        ['a guarded read given no usable timeout', () => apiFetchJson('/api/x', { timeoutMs: 0 }), 30_000],
        ['the visits list', () => fetchVisits({ requestKey: 'deadline:visits' }), 30_000],
        ['a visit\'s captures', () => fetchVisitCaptures('visit-1'), 30_000],
        ['a bird analysis', () => analyzeDetection('event-1'), 180_000]
    ] as const)('%s', async (_name, read, deadlineMs) => {
        await expectDeadline(read(), deadlineMs);
    });
});
