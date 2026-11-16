import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SystemStatusStore } from './system_status.svelte';
import type { PollDocument } from '../app/visible-poll';

/**
 * A response whose headers arrive and whose body then never finishes, through the real API client
 * and a stand-in for the network that behaves as fetch does: aborting the request errors its body.
 */
const visibleTab: PollDocument = { hidden: false, addEventListener: () => undefined, removeEventListener: () => undefined };

interface NetworkRequest { signal: AbortSignal }
let requests: NetworkRequest[] = [];

function stalledBodyFetch(): typeof fetch {
    return ((_url: RequestInfo | URL, init?: RequestInit) => {
        const signal = init?.signal ?? new AbortController().signal;
        requests.push({ signal });
        const body = new ReadableStream<Uint8Array>({
            start(controller) {
                controller.enqueue(new TextEncoder().encode('{"revision": 1'));
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

describe('a status read whose body stalls after the headers', () => {
    it('is aborted by its timeout, and the next read is a new request', async () => {
        const store = new SystemStatusStore({ tab: visibleTab });
        store.start();
        await vi.advanceTimersByTimeAsync(0);
        expect(requests).toHaveLength(1);

        await vi.advanceTimersByTimeAsync(10_001);
        expect(requests[0].signal.aborted).toBe(true);

        // The aborted read has released the store, so asking again sends a new request.
        void store.load();
        await vi.advanceTimersByTimeAsync(0);
        expect(requests).toHaveLength(2);
        store.clear();
    });

    it('is aborted by clear, rather than left running beside the next session', async () => {
        const store = new SystemStatusStore({ tab: visibleTab });
        store.start();
        await vi.advanceTimersByTimeAsync(0);
        expect(requests).toHaveLength(1);

        store.clear();
        await vi.advanceTimersByTimeAsync(0);
        expect(requests[0].signal.aborted).toBe(true);
    });
});
