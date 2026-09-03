import { afterEach, describe, expect, it, vi } from 'vitest';

/**
 * A page that renders many rows must not fan out one request per row at once.
 * The bound lives in the API client so every caller, present and future, gets it.
 */
vi.mock('./core', async () => {
    const actual = await vi.importActual<typeof import('./core')>('./core');
    return { ...actual, apiFetch: vi.fn(), handleResponse: vi.fn(async () => ({})) };
});

function neverResolving() {
    let release!: () => void;
    const promise = new Promise<Response>((resolve) => {
        release = () => resolve(new Response(null, { status: 200, headers: {} }));
    });
    return { promise, release };
}

afterEach(() => vi.clearAllMocks());

describe('page-load fan-out is bounded at the API client', () => {
    it('species info: at most three requests in flight, the rest queued', async () => {
        const core = await import('./core');
        const holds = Array.from({ length: 8 }, () => neverResolving());
        let n = 0;
        vi.mocked(core.apiFetch).mockImplementation(() => holds[n++].promise);
        const { fetchSpeciesInfo } = await import('./species');

        const calls = Array.from({ length: 8 }, (_, i) => fetchSpeciesInfo(`Species ${i}`));
        await Promise.resolve(); await Promise.resolve();
        expect(vi.mocked(core.apiFetch)).toHaveBeenCalledTimes(3);

        holds.forEach((h) => h.release());
        await Promise.all(calls);
        expect(vi.mocked(core.apiFetch)).toHaveBeenCalledTimes(8);
    });

    it('clip probes: at most three in flight, the rest queued', async () => {
        const core = await import('./core');
        const holds = Array.from({ length: 8 }, () => neverResolving());
        let n = 0;
        vi.mocked(core.apiFetch).mockImplementation(() => holds[n++].promise);
        const { checkRecordingClipAvailable } = await import('./media');

        const calls = Array.from({ length: 8 }, (_, i) => checkRecordingClipAvailable(`evt-${i}`));
        await Promise.resolve(); await Promise.resolve();
        expect(vi.mocked(core.apiFetch)).toHaveBeenCalledTimes(3);

        holds.forEach((h) => h.release());
        await Promise.all(calls);
        expect(vi.mocked(core.apiFetch)).toHaveBeenCalledTimes(8);
    });
});
