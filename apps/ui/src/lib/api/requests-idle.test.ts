import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiFetch, apiFetchJson, onRequestsIdle } from './core';

afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
});

/** A fetch the test answers by hand, so a request can be held in flight. */
function heldFetch(): { answer: () => void } {
    let answer: () => void = () => {};
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => {
        answer = () => resolve(new Response('{}', { status: 200 }));
    })));
    return { answer: () => answer() };
}

describe('onRequestsIdle', () => {
    it('says so at once when no request is in flight', () => {
        const idle = vi.fn();
        onRequestsIdle(idle);
        expect(idle).toHaveBeenCalledTimes(1);
    });

    it('waits for the requests in flight to finish, then says so once', async () => {
        const held = heldFetch();
        const request = apiFetch('/api/settings');
        const idle = vi.fn();
        onRequestsIdle(idle);
        expect(idle).not.toHaveBeenCalled();
        held.answer();
        await request;
        await settled();
        expect(idle).toHaveBeenCalledTimes(1);
    });

    it('stops waiting when the caller stops it', async () => {
        const held = heldFetch();
        const request = apiFetch('/api/settings');
        const idle = vi.fn();
        const stop = onRequestsIdle(idle);
        stop();
        held.answer();
        await request;
        expect(idle).not.toHaveBeenCalled();
    });

    it('a waiter that throws neither fails the request that finished nor keeps the others from being told', async () => {
        const reported = vi.spyOn(console, 'error').mockImplementation(() => {});
        const held = heldFetch();
        const request = apiFetch('/api/settings');
        const later = vi.fn();
        onRequestsIdle(() => {
            throw new Error('a waiter failed');
        });
        onRequestsIdle(later);
        held.answer();
        await expect(request).resolves.toBeInstanceOf(Response);
        await settled();
        expect(later).toHaveBeenCalledTimes(1);
        expect(reported).toHaveBeenCalled();
    });

    it('counts a request finished however it ends: refused by the network, aborted, timed out or answered with an error', async () => {
        vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))));
        await expect(apiFetch('/api/settings')).rejects.toThrow('Failed to fetch');
        await expectIdle();

        vi.stubGlobal('fetch', vi.fn((_url: string, options?: RequestInit) => new Promise<Response>((_resolve, reject) => {
            options?.signal?.addEventListener('abort', () => reject(options.signal?.reason));
        })));
        const caller = new AbortController();
        const aborted = apiFetch('/api/settings', { signal: caller.signal });
        caller.abort(new DOMException('Left the page', 'AbortError'));
        await expect(aborted).rejects.toThrow('Left the page');
        await expectIdle();

        vi.useFakeTimers();
        const timedOut = apiFetch('/api/settings', { timeoutMs: 1000 });
        const timedOutResult = expect(timedOut).rejects.toThrow('timed out');
        await vi.advanceTimersByTimeAsync(1000);
        await timedOutResult;
        vi.useRealTimers();
        await expectIdle();

        vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('<html>Server error</html>', { status: 500 }))));
        await expect(apiFetchJson('/api/settings', { timeoutMs: 1000 })).rejects.toThrow();
        await expectIdle();
    });
});

/** Lets the idle report, which runs after the request has settled, arrive. */
async function settled(): Promise<void> {
    await new Promise((done) => setTimeout(done, 0));
}

async function expectIdle(): Promise<void> {
    await settled();
    const idle = vi.fn();
    onRequestsIdle(idle);
    expect(idle).toHaveBeenCalledTimes(1);
}
