import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchAnalysisStatus } from './maintenance';

describe('fetchAnalysisStatus', () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('requests fresh queue status without using the browser cache', async () => {
        const fetchMock = vi.fn(async () => new Response(JSON.stringify({
            pending: 0,
            active: 0,
            circuit_open: false
        })));
        vi.stubGlobal('fetch', fetchMock);

        await fetchAnalysisStatus();

        expect(fetchMock).toHaveBeenCalledTimes(1);
        const firstCall = fetchMock.mock.calls[0] as unknown as [string, RequestInit | undefined];
        const requestInit = firstCall[1];
        expect(requestInit).toMatchObject({ cache: 'no-store' });
    });
});
