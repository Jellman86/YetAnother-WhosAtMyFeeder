import { afterEach, describe, expect, it, vi } from 'vitest';

import { applyTimezoneRepair, fetchAnalysisStatus, fetchTimezoneRepairPreview } from './maintenance';

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

describe('timezone repair maintenance api', () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('requests timezone repair preview without using the browser cache', async () => {
        const fetchMock = vi.fn(async () => new Response(JSON.stringify({
            summary: {
                scanned_count: 1,
                repair_candidate_count: 1,
                ok_count: 0,
                missing_frigate_event_count: 0,
                lookup_error_count: 0,
                unsupported_delta_count: 0
            },
            candidates: []
        })));
        vi.stubGlobal('fetch', fetchMock);

        await fetchTimezoneRepairPreview();

        const firstCall = fetchMock.mock.calls[0] as unknown as [string, RequestInit | undefined];
        expect(firstCall[0]).toContain('/maintenance/timezone-repair/preview');
        expect(firstCall[1]).toMatchObject({ cache: 'no-store' });
    });

    it('posts explicit confirmation when applying timezone repair', async () => {
        const fetchMock = vi.fn(async () => new Response(JSON.stringify({
            status: 'ok',
            repaired_count: 1,
            skipped_count: 0,
            preview: {
                summary: {
                    scanned_count: 1,
                    repair_candidate_count: 1,
                    ok_count: 0,
                    missing_frigate_event_count: 0,
                    lookup_error_count: 0,
                    unsupported_delta_count: 0
                },
                candidates: []
            }
        })));
        vi.stubGlobal('fetch', fetchMock);

        await applyTimezoneRepair();

        const firstCall = fetchMock.mock.calls[0] as unknown as [string, RequestInit | undefined];
        expect(firstCall[0]).toContain('/maintenance/timezone-repair/apply');
        expect(firstCall[1]).toMatchObject({ method: 'POST' });
        expect(firstCall[1]?.body).toBe(JSON.stringify({ confirm: true }));
    });
});
