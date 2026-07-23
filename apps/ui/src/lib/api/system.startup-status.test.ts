import { beforeEach, describe, expect, it, vi } from 'vitest';

const { apiFetchMock } = vi.hoisted(() => ({
    apiFetchMock: vi.fn()
}));

vi.mock('./core', () => ({
    API_BASE: '/api',
    apiFetch: apiFetchMock,
    handleResponse: vi.fn()
}));

import { fetchStartupStatus, normalizeStartupStatus } from './system';

describe('startup status', () => {
    beforeEach(() => {
        apiFetchMock.mockReset();
    });

    it('accepts the bounded static startup contract and clamps progress', () => {
        expect(normalizeStartupStatus({
            status: 'starting',
            phase: 'loading_model',
            progress: 140,
            started_at: '2026-07-21T09:00:00Z',
            updated_at: '2026-07-21T09:00:05Z',
            ignored: 'private detail'
        })).toEqual({
            status: 'starting',
            phase: 'loading_model',
            progress: 100,
            started_at: '2026-07-21T09:00:00Z',
            updated_at: '2026-07-21T09:00:05Z'
        });
    });

    it('rejects malformed or unknown status values', () => {
        expect(normalizeStartupStatus({ status: 'starting', phase: '', progress: 20 })).toBeNull();
        expect(normalizeStartupStatus({ status: 'secret', phase: 'loading_model', progress: 20 })).toBeNull();
        expect(normalizeStartupStatus('starting')).toBeNull();
    });

    it('accepts the recoverable model unavailable startup phase', () => {
        expect(normalizeStartupStatus({
            status: 'starting',
            phase: 'model_unavailable',
            progress: 60,
            started_at: '2026-07-21T10:00:00Z',
            updated_at: '2026-07-21T10:00:01Z'
        })?.phase).toBe('model_unavailable');
    });

    it('returns null when a split frontend rewrites the status path to HTML', async () => {
        apiFetchMock.mockResolvedValue(new Response('<!doctype html>', {
            status: 200,
            headers: { 'content-type': 'text/html' }
        }));

        await expect(fetchStartupStatus()).resolves.toBeNull();
    });

    it('loads the no-cache startup status without surfacing secondary failures', async () => {
        apiFetchMock.mockResolvedValueOnce(new Response(JSON.stringify({
            status: 'starting',
            phase: 'database',
            progress: 70,
            started_at: '2026-07-21T09:00:00Z',
            updated_at: '2026-07-21T09:00:05Z'
        }), {
            status: 200,
            headers: { 'content-type': 'application/json' }
        }));

        await expect(fetchStartupStatus()).resolves.toMatchObject({ phase: 'database', progress: 70 });
        expect(apiFetchMock).toHaveBeenCalledWith('/startup-status.json', expect.objectContaining({
            cache: 'no-store',
            timeoutMs: 2_500
        }));

        apiFetchMock.mockRejectedValueOnce(new Error('offline'));
        await expect(fetchStartupStatus()).resolves.toBeNull();
    });
});
