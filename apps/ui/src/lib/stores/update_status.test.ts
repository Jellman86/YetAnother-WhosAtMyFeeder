import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
    readUpdateStatus: vi.fn(),
}));

vi.mock('../api', () => ({
    readUpdateStatus: mocks.readUpdateStatus,
    shouldShowUpdateBanner: (status: { update_available?: boolean; latest_version?: string | null } | null, dismissed: string | null) =>
        Boolean(status?.update_available && status.latest_version && status.latest_version !== dismissed),
}));

const status = (commit: string) => ({
    current_version: '2.17.0-dev+old0000',
    channel: 'dev',
    latest_version: `2.17.0-dev+${commit}`,
    update_available: commit !== 'old0000',
    release_url: 'https://example.test/tree/dev',
    checked_at: '2026-08-13T00:00:00Z',
    enabled: true,
    error: null,
});

describe('UpdateStatusStore', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        vi.setSystemTime(new Date('2026-08-13T00:00:00Z'));
        vi.resetModules();
        mocks.readUpdateStatus.mockReset();
        Object.defineProperty(globalThis, 'localStorage', {
            configurable: true,
            value: {
                getItem: vi.fn().mockReturnValue(null),
                setItem: vi.fn(),
            },
        });
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.unstubAllGlobals();
    });

    it('deduplicates the initial check and refreshes a stale result', async () => {
        mocks.readUpdateStatus
            .mockResolvedValueOnce(status('old0000'))
            .mockResolvedValueOnce(status('new1111'));
        const { UPDATE_STATUS_MAX_AGE_MS, UpdateStatusStore } = await import('./update_status.svelte');
        const store = new UpdateStatusStore();

        await Promise.all([store.load(), store.load(), store.load()]);
        expect(mocks.readUpdateStatus).toHaveBeenCalledTimes(1);
        expect(store.updateAvailable).toBe(false);

        await vi.advanceTimersByTimeAsync(UPDATE_STATUS_MAX_AGE_MS);
        await store.refreshIfStale();

        expect(mocks.readUpdateStatus).toHaveBeenCalledTimes(2);
        expect(store.latestVersion).toBe('2.17.0-dev+new1111');
        expect(store.updateAvailable).toBe(true);
    });

    it('retries after an initial transient failure instead of staying null forever', async () => {
        mocks.readUpdateStatus
            .mockRejectedValueOnce(new Error('offline'))
            .mockResolvedValueOnce(status('new2222'));
        const { UPDATE_STATUS_MAX_AGE_MS, UpdateStatusStore } = await import('./update_status.svelte');
        const store = new UpdateStatusStore();

        await store.load();
        expect(store.status).toBeNull();

        await vi.advanceTimersByTimeAsync(UPDATE_STATUS_MAX_AGE_MS);
        await store.refreshIfStale();

        expect(mocks.readUpdateStatus).toHaveBeenCalledTimes(2);
        expect(store.updateAvailable).toBe(true);
    });
});
