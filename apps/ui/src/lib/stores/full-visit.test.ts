import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api', () => ({
    checkRecordingClipAvailable: vi.fn(),
    fetchRecordingClip: vi.fn(),
}));

describe('FullVisitStore', () => {
    beforeEach(() => {
        vi.resetModules();
        vi.clearAllMocks();
    });

    it('marks a recording clip as fetched when the backend reports a persisted full visit', async () => {
        const api = await import('../api');
        vi.mocked(api.checkRecordingClipAvailable).mockResolvedValue({
            available: true,
            fetched: true
        });

        const { FullVisitStore } = await import('./full-visit.svelte');
        const store = new FullVisitStore();

        await store.ensureAvailability('evt-1');

        expect(store.isAvailable('evt-1')).toBe(true);
        expect(store.isFetched('evt-1')).toBe(true);
    });

    it('does not restore promoted full-visit state from local storage without a fresh probe', async () => {
        const api = await import('../api');
        vi.mocked(api.fetchRecordingClip).mockResolvedValue({
            event_id: 'evt-2',
            status: 'ready',
            clip_variant: 'recording',
            cached: false
        });

        const { FullVisitStore } = await import('./full-visit.svelte');
        const firstStore = new FullVisitStore();
        await firstStore.fetchFullVisit('evt-2');

        const secondStore = new FullVisitStore();
        expect(secondStore.isFetched('evt-2')).toBe(false);
        expect(secondStore.getAvailability('evt-2')).toBe('unknown');
    });

    it('auto-fetches the clip when available=true, fetched=false and autoFetch option is set', async () => {
        const api = await import('../api');
        vi.mocked(api.checkRecordingClipAvailable).mockResolvedValue({ available: true, fetched: false });
        vi.mocked(api.fetchRecordingClip).mockResolvedValue({
            event_id: 'evt-af',
            status: 'ready',
            clip_variant: 'recording',
            cached: true
        });

        const { FullVisitStore } = await import('./full-visit.svelte');
        const store = new FullVisitStore();

        await store.ensureAvailability('evt-af', { autoFetch: true });

        expect(api.fetchRecordingClip).toHaveBeenCalledWith('evt-af');
        expect(store.isFetched('evt-af')).toBe(true);
    });

    it('does not auto-fetch when autoFetch option is not set', async () => {
        const api = await import('../api');
        vi.mocked(api.checkRecordingClipAvailable).mockResolvedValue({ available: true, fetched: false });

        const { FullVisitStore } = await import('./full-visit.svelte');
        const store = new FullVisitStore();

        await store.ensureAvailability('evt-no-af');

        expect(api.fetchRecordingClip).not.toHaveBeenCalled();
        expect(store.isFetched('evt-no-af')).toBe(false);
    });

    it('auto-fetches immediately when availability is already confirmed and autoFetch is set', async () => {
        const api = await import('../api');
        vi.mocked(api.checkRecordingClipAvailable).mockResolvedValue({ available: true, fetched: false });
        vi.mocked(api.fetchRecordingClip).mockResolvedValue({
            event_id: 'evt-cached',
            status: 'ready',
            clip_variant: 'recording',
            cached: true
        });

        const { FullVisitStore } = await import('./full-visit.svelte');
        const store = new FullVisitStore();

        // First probe without autoFetch — establishes 'available' in cache
        await store.ensureAvailability('evt-cached');
        expect(store.isFetched('evt-cached')).toBe(false);

        // Second call with autoFetch — should trigger fetch without re-probing
        await store.ensureAvailability('evt-cached', { autoFetch: true });
        expect(api.checkRecordingClipAvailable).toHaveBeenCalledTimes(1);
        expect(api.fetchRecordingClip).toHaveBeenCalledWith('evt-cached');
    });

    it('refreshes a stale event probe and promotes the same event to fetched when a persisted full visit later appears', async () => {
        const api = await import('../api');
        vi.mocked(api.checkRecordingClipAvailable)
            .mockResolvedValueOnce({
                available: true,
                fetched: false
            })
            .mockResolvedValueOnce({
                available: true,
                fetched: true
            });

        const { FullVisitStore } = await import('./full-visit.svelte');
        const store = new FullVisitStore();

        await store.ensureAvailability('evt-3');
        expect(store.isAvailable('evt-3')).toBe(true);
        expect(store.isFetched('evt-3')).toBe(false);

        await store.ensureAvailability('evt-3', { refresh: true });

        expect(api.checkRecordingClipAvailable).toHaveBeenCalledTimes(2);
        expect(store.isFetched('evt-3')).toBe(true);
    });
});
