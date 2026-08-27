import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api', () => ({
    checkRecordingClipAvailable: vi.fn(),
    fetchRecordingClip: vi.fn(),
}));

describe('FullVisitStore', () => {
    beforeEach(() => {
        vi.resetModules();
        vi.clearAllMocks();
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it('marks a recording clip as fetched when the backend reports a persisted full visit', async () => {
        const api = await import('../api');
        vi.mocked(api.checkRecordingClipAvailable).mockResolvedValue({
            available: true,
            fetched: true,
            state: 'complete',
            durationSeconds: 30
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
            recording_state: 'complete',
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
        vi.mocked(api.checkRecordingClipAvailable).mockResolvedValue({ available: true, fetched: false, state: null, durationSeconds: null });
        vi.mocked(api.fetchRecordingClip).mockResolvedValue({
            event_id: 'evt-af',
            status: 'ready',
            clip_variant: 'recording',
            recording_state: 'complete',
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
        vi.mocked(api.checkRecordingClipAvailable).mockResolvedValue({ available: true, fetched: false, state: null, durationSeconds: null });

        const { FullVisitStore } = await import('./full-visit.svelte');
        const store = new FullVisitStore();

        await store.ensureAvailability('evt-no-af');

        expect(api.fetchRecordingClip).not.toHaveBeenCalled();
        expect(store.isFetched('evt-no-af')).toBe(false);
    });

    it('auto-fetches immediately when availability is already confirmed and autoFetch is set', async () => {
        const api = await import('../api');
        vi.mocked(api.checkRecordingClipAvailable).mockResolvedValue({ available: true, fetched: false, state: null, durationSeconds: null });
        vi.mocked(api.fetchRecordingClip).mockResolvedValue({
            event_id: 'evt-cached',
            status: 'ready',
            clip_variant: 'recording',
            recording_state: 'complete',
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
                fetched: false,
                state: null,
                durationSeconds: null
            })
            .mockResolvedValueOnce({
                available: true,
                fetched: true,
                state: 'complete',
                durationSeconds: 30
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

    it('performs at most one automatic re-probe for an available uncached clip', async () => {
        vi.useFakeTimers();
        const api = await import('../api');
        vi.mocked(api.checkRecordingClipAvailable).mockResolvedValue({ available: true, fetched: false, state: null, durationSeconds: null });

        const { FullVisitStore } = await import('./full-visit.svelte');
        const store = new FullVisitStore({ reprobeDelayMs: 8000 });

        await store.ensureAvailability('evt-once');
        expect(api.checkRecordingClipAvailable).toHaveBeenCalledTimes(1);

        await vi.advanceTimersByTimeAsync(8000);
        expect(api.checkRecordingClipAvailable).toHaveBeenCalledTimes(2);

        await vi.advanceTimersByTimeAsync(60_000);
        expect(api.checkRecordingClipAvailable).toHaveBeenCalledTimes(2);
    });

    it('bounds cached event state and clears timers for evicted events', async () => {
        vi.useFakeTimers();
        const api = await import('../api');
        vi.mocked(api.checkRecordingClipAvailable).mockResolvedValue({ available: true, fetched: false, state: null, durationSeconds: null });

        const { FullVisitStore } = await import('./full-visit.svelte');
        const store = new FullVisitStore({ maxEntries: 3 });

        for (const eventId of ['evt-1', 'evt-2', 'evt-3', 'evt-4', 'evt-5']) {
            await store.ensureAvailability(eventId);
        }

        expect(Object.keys(store.availability)).toHaveLength(3);
        expect(store.getAvailability('evt-1')).toBe('unknown');
        expect(store.getAvailability('evt-5')).toBe('available');

        await vi.advanceTimersByTimeAsync(8000);
        expect(api.checkRecordingClipAvailable).toHaveBeenCalledTimes(8);
    });

    it('contains an automatic fetch failure without leaking an unhandled rejection', async () => {
        const api = await import('../api');
        vi.mocked(api.checkRecordingClipAvailable).mockResolvedValue({ available: true, fetched: false, state: null, durationSeconds: null });
        vi.mocked(api.fetchRecordingClip).mockRejectedValue(new Error('upstream unavailable'));

        const { FullVisitStore } = await import('./full-visit.svelte');
        const store = new FullVisitStore();

        await store.ensureAvailability('evt-fail', { autoFetch: true });

        await vi.waitFor(() => expect(store.getFetchState('evt-fail')).toBe('failed'));
    });

    it('keeps a playable partial explicit instead of promoting it as a full visit', async () => {
        const api = await import('../api');
        vi.mocked(api.fetchRecordingClip).mockResolvedValue({
            event_id: 'evt-partial',
            status: 'partial',
            clip_variant: 'recording',
            recording_state: 'partial',
            cached: true
        });

        const { FullVisitStore } = await import('./full-visit.svelte');
        const store = new FullVisitStore();

        await expect(store.fetchFullVisit('evt-partial')).resolves.toBe(false);
        expect(store.getFetchState('evt-partial')).toBe('partial');
        expect(store.isAvailable('evt-partial')).toBe(true);
        expect(store.isFetched('evt-partial')).toBe(false);
    });
});
