import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));

vi.mock('./core', () => ({
    API_BASE: '/api',
    apiFetch: apiFetchMock,
    handleResponse: vi.fn(),
    requestScope: () => 'owner|en'
}));

const { readVersion } = await import('./system');

describe('readVersion', () => {
    // Each case starts after the last one's reading has stopped being shared.
    let clock = Date.parse('2026-11-16T12:00:00Z');
    beforeEach(() => {
        apiFetchMock.mockReset();
        clock += 60_000;
        vi.useFakeTimers({ toFake: ['Date'], now: clock });
    });
    afterEach(() => vi.useRealTimers());

    it('shows the build\'s own version when the server cannot be read, and asks the server again next time', async () => {
        apiFetchMock
            .mockRejectedValueOnce(new Error('offline'))
            .mockResolvedValueOnce({ ok: true, json: async () => ({ version: '9.9.9-dev+abc', base_version: '9.9.9' }) });

        const fallback = await readVersion();
        expect(fallback.version).not.toBe('9.9.9-dev+abc');

        const read = await readVersion();
        expect(read.version).toBe('9.9.9-dev+abc');
        expect(apiFetchMock).toHaveBeenCalledTimes(2);
    });

    it('does not keep an HTTP failure as the reading either', async () => {
        apiFetchMock
            .mockResolvedValueOnce({ ok: false, status: 502, json: async () => ({}) })
            .mockResolvedValueOnce({ ok: true, json: async () => ({ version: '9.9.9-dev+abc', base_version: '9.9.9' }) });

        await readVersion();
        expect((await readVersion()).version).toBe('9.9.9-dev+abc');
        expect(apiFetchMock).toHaveBeenCalledTimes(2);
    });
});
