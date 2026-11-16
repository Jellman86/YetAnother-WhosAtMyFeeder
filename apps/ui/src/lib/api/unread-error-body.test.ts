import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// The error reader stands in for any step that fails without reading the body: the guarded
// client itself must cancel what it leaves unread, not rely on that step to.
vi.mock('./error-message', async (importOriginal) => ({
    ...(await importOriginal<typeof import('./error-message')>()),
    readApiErrorMessage: async (_response: Response, fallback: string) => fallback
}));

const { apiFetchJson } = await import('./core');

let cancelledBodies = 0;

beforeEach(() => {
    cancelledBodies = 0;
    vi.stubGlobal('fetch', (() => {
        const body = new ReadableStream<Uint8Array>({
            start(controller) {
                controller.enqueue(new TextEncoder().encode('{"detail": '));
            },
            cancel() {
                cancelledBodies += 1;
            }
        });
        return Promise.resolve(new Response(body, { status: 503, headers: { 'Content-Type': 'application/json' } }));
    }) as typeof fetch);
});

afterEach(() => vi.unstubAllGlobals());

describe('a guarded read that fails without reading its body', () => {
    it('cancels the body before it lets the request go', async () => {
        await expect(apiFetchJson('/api/x', { timeoutMs: 10_000 })).rejects.toThrow();
        expect(cancelledBodies).toBe(1);
    });
});
