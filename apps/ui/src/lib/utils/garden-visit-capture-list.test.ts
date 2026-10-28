import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { GardenCapture } from '../api/garden';

const fetchGardenVisitCaptures = vi.fn();
vi.mock('../api/garden', () => ({ fetchGardenVisitCaptures: (...args: unknown[]) => fetchGardenVisitCaptures(...args) }));

const { GardenVisitCaptureList } = await import('./garden-visit-capture-list.svelte');
const { gardenHistory } = await import('../stores/garden_history.svelte');

function capture(id: string): GardenCapture {
    return { id, camera: 'patio', frigate_label: 'fox', observed_at: '2026-10-28T09:00:00Z', status: 'confirmed', reviewed_at: null, snapshot_url: null };
}

const scope = { start: '2026-10-27T09:00:00Z', end: '2026-10-28T09:00:00Z', status: 'reviewable' as const };
const visit = { id: 'visit-1', kind: 'visit' as const, captureCount: 25, items: [capture('a')] };

describe('GardenVisitCaptureList', () => {
    beforeEach(() => fetchGardenVisitCaptures.mockReset());

    it('reads a bounded first page in the view scope, then appends the next', async () => {
        fetchGardenVisitCaptures
            .mockResolvedValueOnce({ items: Array.from({ length: 20 }, (_, i) => capture(`p1-${i}`)), total: 25, limit: 20, offset: 0 })
            .mockResolvedValueOnce({ items: Array.from({ length: 5 }, (_, i) => capture(`p2-${i}`)), total: 25, limit: 20, offset: 20 });
        const list = new GardenVisitCaptureList(() => ({ visit, scope }));
        await list.load(true);
        expect(fetchGardenVisitCaptures).toHaveBeenLastCalledWith('visit-1', scope, 0, expect.objectContaining({ limit: 20 }));
        expect(list.captures).toHaveLength(20);
        expect(list.hasMore).toBe(true);
        await list.load();
        expect(fetchGardenVisitCaptures).toHaveBeenLastCalledWith('visit-1', scope, 20, expect.objectContaining({ limit: 20 }));
        expect(list.captures).toHaveLength(25);
        expect(list.hasMore).toBe(false);
    });

    it('treats a Garden history change as a new list, so a review elsewhere is never shown stale', async () => {
        fetchGardenVisitCaptures.mockResolvedValue({ items: [capture('a')], total: 1, limit: 20, offset: 0 });
        const list = new GardenVisitCaptureList(() => ({ visit, scope }));
        await list.load(true);
        expect(list.loaded).toBe(true);
        gardenHistory.invalidate();
        expect(list.loaded).toBe(false);
        expect(list.captures).toEqual([]);
    });

    it('says a failed read failed, and a retry recovers it', async () => {
        fetchGardenVisitCaptures.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ items: [capture('a')], total: 1, limit: 20, offset: 0 });
        const list = new GardenVisitCaptureList(() => ({ visit, scope }));
        await list.load(true);
        expect(list.failed).toBe(true);
        await list.load(true);
        expect(list.failed).toBe(false);
        expect(list.captures).toHaveLength(1);
    });
});


it('discards a page that resolves after the view scope changes', async () => {
    let resolve: (value: unknown) => void = () => undefined;
    fetchGardenVisitCaptures.mockReturnValue(new Promise(done => { resolve = done; }));
    let activeScope: import('./garden-visit-viewer.svelte').GardenCaptureScope = scope;
    const list = new GardenVisitCaptureList(() => ({ visit, scope: activeScope }));
    const reading = list.load(true);
    activeScope = { ...scope, status: 'confirmed' };
    resolve({ items: [capture('old')], total: 1, limit: 20, offset: 0 });
    await reading;
    expect(list.loaded).toBe(false);
    expect(list.captures).toEqual([]);
});


it('forgets private pages when owner access is lost', async () => {
    const { authStore } = await import('../stores/auth.svelte');
    const previous = { authRequired: authStore.authRequired, isAuthenticated: authStore.isAuthenticated,
        statusLoaded: authStore.statusLoaded, statusHealthy: authStore.statusHealthy };
    try {
        Object.assign(authStore, { authRequired: true, isAuthenticated: true, statusLoaded: true, statusHealthy: true });
        fetchGardenVisitCaptures.mockResolvedValue({ items: [capture('private')], total: 1, limit: 20, offset: 0 });
        const list = new GardenVisitCaptureList(() => ({ visit, scope }));
        await list.load(true);
        expect(list.captures).toHaveLength(1);
        authStore.isAuthenticated = false;
        expect(list.loaded).toBe(false);
        expect(list.captures).toEqual([]);
    } finally {
        Object.assign(authStore, previous);
    }
});
