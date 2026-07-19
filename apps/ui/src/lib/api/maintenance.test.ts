import { afterEach, describe, expect, it, vi } from 'vitest';

import { applyTimezoneRepair, fetchAnalysisStatus, fetchTimezoneRepairPreview, purgeMissingMedia, testLlm } from './maintenance';

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

describe('media integrity maintenance api', () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('runs one combined missing-media scan', async () => {
        const fetchMock = vi.fn(async () => new Response(JSON.stringify({
            status: 'completed',
            deleted_count: 0,
            marked_missing_count: 1,
            kept_count: 0,
            cleared_missing_count: 0,
            checked: 1,
            missing: 1
        })));
        vi.stubGlobal('fetch', fetchMock);

        await purgeMissingMedia();

        const firstCall = fetchMock.mock.calls[0] as unknown as [string, RequestInit | undefined];
        expect(firstCall[0]).toContain('/maintenance/purge-missing-media');
        expect(firstCall[1]).toMatchObject({ method: 'POST' });
    });
});

describe('AI model diagnostic api', () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('preserves structured provider failures instead of throwing away the stage results', async () => {
        const fetchMock = vi.fn(async () => new Response(JSON.stringify({
            status: 'error',
            message: 'No provider is currently available.',
            provider: 'openrouter',
            model: 'nvidia/test-vision',
            frame_count: 5,
            failure_stage: 'provider',
            retryable: true,
            retry_after_seconds: 15
        }), { status: 503 }));
        vi.stubGlobal('fetch', fetchMock);

        const result = await testLlm({
            llm_enabled: true,
            llm_provider: 'openrouter',
            llm_model: 'nvidia/test-vision',
            llm_api_key: 'sk-or-test'
        });

        expect(result).toMatchObject({
            status: 'error',
            failure_stage: 'provider',
            retryable: true,
            retry_after_seconds: 15,
            http_status: 503
        });
    });
});
