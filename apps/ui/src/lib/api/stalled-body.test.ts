import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchClassifierStatus } from './classifier';
import { fetchDiagnosticsWorkspace } from './diagnostics';
import { checkHealth, fetchSystemTelemetry, fetchSystemTelemetryHistory } from './system';
import { fetchVisits } from './visits';

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

async function expectTimedOut(read: Promise<unknown>, timeoutMs: number): Promise<void> {
    const outcome = read.then(() => 'resolved', () => 'rejected');
    await vi.advanceTimersByTimeAsync(timeoutMs + 1);
    expect(requests[0]?.aborted).toBe(true);
    await expect(outcome).resolves.toBe('rejected');
}

describe('a read whose body stalls after its headers is still timed out', () => {
    it.each([
        ['the incident workspace', () => fetchDiagnosticsWorkspace(), 15_000],
        ["Health's visits", () => fetchVisits({ startTime: '2026-11-16T00:00:00Z', endTime: '2026-11-16T12:00:00Z', requestKey: 'health:visits', timeoutMs: 15_000 }), 15_000],
        ['the classifier status', () => fetchClassifierStatus(), 10_000],
        ['the backend health', () => checkHealth(), 10_000],
        ['the telemetry history', () => fetchSystemTelemetryHistory(), 5_000],
        ['the telemetry sample', () => fetchSystemTelemetry(), 2_500]
    ] as const)('%s', async (_name, read, timeoutMs) => {
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
