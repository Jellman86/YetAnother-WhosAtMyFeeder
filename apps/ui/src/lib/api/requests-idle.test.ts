import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiFetch, onRequestsIdle } from './core';

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
});
