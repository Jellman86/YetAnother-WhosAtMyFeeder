import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import type { Detection } from '../api';
import type { DetectionVisit, VisitOptions } from '../api/visits';
import type { GardenCapture } from '../api/garden';
import type { GardenVisit } from './garden-explorer';
import type { GardenCaptureScope } from './garden-visit-viewer.svelte';
import type { PagedCaptures } from './paged-captures.svelte';

const fetchVisitCaptures = vi.fn();
const fetchGardenVisitCaptures = vi.fn();
vi.mock('../api/visits', async (importOriginal) => ({
    ...(await importOriginal<typeof import('../api/visits')>()),
    fetchVisitCaptures: (...args: unknown[]) => fetchVisitCaptures(...args)
}));
vi.mock('../api/garden', async (importOriginal) => ({
    ...(await importOriginal<typeof import('../api/garden')>()),
    fetchGardenVisitCaptures: (...args: unknown[]) => fetchGardenVisitCaptures(...args)
}));

const { VisitCaptureList } = await import('./visit-capture-list.svelte');
const { GardenVisitCaptureList } = await import('./garden-visit-capture-list.svelte');
const { authStore } = await import('../stores/auth.svelte');
const { detectionsStore } = await import('../stores/detections.svelte');
const { gardenHistory } = await import('../stores/garden_history.svelte');

interface Deferred<T> {
    promise: Promise<T>;
    resolve: (value: T) => void;
    reject: (reason: unknown) => void;
}

function deferred<T>(): Deferred<T> {
    let resolve: (value: T) => void = () => undefined;
    let reject: (reason: unknown) => void = () => undefined;
    const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
    return { promise, resolve, reject };
}

/** One adapter, described by how its endpoint is called and answers. */
interface Adapter<T> {
    name: string;
    read: Mock;
    item: (id: string) => T;
    idOf: (item: T) => string;
    /** What the endpoint answers for one page. */
    answer: (items: T[], total: number) => unknown;
    request: (call: unknown[]) => { visitId: string; offset: number; limit: number; signal: AbortSignal };
    /** A list over a visit whose membership the test can change. */
    create: () => { list: PagedCaptures<T>; changeMembership: () => void };
    /** Another view changed the shared history this visit belongs to. */
    invalidateHistory: () => void;
}

function bird(id: string): Detection {
    return { frigate_event: id, display_name: 'Prunella modularis', camera_name: 'birdcam', detection_time: '2026-10-28T09:00:00Z', score: 0.9 } as Detection;
}

const birdAdapter: Adapter<Detection> = {
    name: 'bird VisitCaptureList',
    read: fetchVisitCaptures,
    item: bird,
    idOf: (item) => item.frigate_event,
    answer: (items, total) => ({ captures: items, total }),
    request: (call) => {
        const [visitId, options] = call as [string, VisitOptions & { limit: number; offset: number; signal: AbortSignal }];
        return { visitId, offset: options.offset, limit: options.limit, signal: options.signal };
    },
    create: () => {
        let visit = {
            visit_id: 'visit-1', start_time: '2026-10-28T09:00:00Z', end_time: '2026-10-28T09:05:00Z', capture_count: 25,
            best_score: 0.9, needs_review: false, audio_confirmed: false, representative: bird('lead'), latest: bird('lead'), peak_capture: null
        } as unknown as DetectionVisit;
        const window: VisitOptions = { startDate: '2026-10-28', endDate: '2026-10-28' };
        const list = new VisitCaptureList(() => ({ visit, window }));
        return { list, changeMembership: () => { visit = { ...visit, capture_count: visit.capture_count + 1 }; } };
    },
    invalidateHistory: () => { detectionsStore.mutationVersion += 1; }
};

function garden(id: string): GardenCapture {
    return { id, camera: 'patio', frigate_label: 'fox', observed_at: '2026-10-28T09:00:00Z', status: 'confirmed', reviewed_at: null, snapshot_url: null };
}

const gardenScope: GardenCaptureScope = { start: '2026-10-27T09:00:00Z', end: '2026-10-28T09:00:00Z', status: 'reviewable' };

const gardenAdapter: Adapter<GardenCapture> = {
    name: 'GardenVisitCaptureList',
    read: fetchGardenVisitCaptures,
    item: garden,
    idOf: (item) => item.id,
    answer: (items, total) => ({ items, total, limit: 20, offset: 0 }),
    request: (call) => {
        const [visitId, , offset, options] = call as [string, GardenCaptureScope, number, { limit: number; signal: AbortSignal }];
        return { visitId, offset, limit: options.limit, signal: options.signal };
    },
    create: () => {
        let visit: GardenVisit = { id: 'visit-1', kind: 'visit', captureCount: 25, items: [garden('lead')] };
        const list = new GardenVisitCaptureList(() => ({ visit, scope: gardenScope }));
        return { list, changeMembership: () => { visit = { ...visit, captureCount: (visit.captureCount ?? 0) + 1 }; } };
    },
    invalidateHistory: () => gardenHistory.invalidate()
};

const ids = (count: number, prefix: string) => Array.from({ length: count }, (_, index) => `${prefix}-${index}`);

let savedAuth: Pick<typeof authStore, 'authRequired' | 'isAuthenticated' | 'statusLoaded' | 'statusHealthy'>;

beforeEach(() => {
    fetchVisitCaptures.mockReset();
    fetchGardenVisitCaptures.mockReset();
    savedAuth = { authRequired: authStore.authRequired, isAuthenticated: authStore.isAuthenticated, statusLoaded: authStore.statusLoaded, statusHealthy: authStore.statusHealthy };
    Object.assign(authStore, { authRequired: true, isAuthenticated: true, statusLoaded: true, statusHealthy: true });
});

afterEach(() => {
    Object.assign(authStore, savedAuth);
});

describe.each([birdAdapter, gardenAdapter] as Adapter<unknown>[])('$name paged capture contract', (adapter) => {
    const page = (prefix: string, count: number, total: number) => adapter.answer(ids(count, prefix).map(adapter.item), total);
    const shown = (list: PagedCaptures<unknown>) => list.captures.map(adapter.idOf);

    it('reads nothing until asked, then a bounded first page', async () => {
        adapter.read.mockResolvedValue(page('p1', 20, 25));
        const { list } = adapter.create();
        expect(adapter.read).not.toHaveBeenCalled();
        expect([list.loaded, list.loading, list.failed]).toEqual([false, false, false]);

        await list.load(true);

        expect(adapter.read).toHaveBeenCalledTimes(1);
        expect(adapter.request(adapter.read.mock.calls[0])).toMatchObject({ visitId: 'visit-1', offset: 0, limit: 20 });
        expect(shown(list)).toEqual(ids(20, 'p1'));
        expect([list.total, list.loaded, list.loading, list.failed, list.hasMore]).toEqual([25, true, false, false, true]);
    });

    it('starts one read for a repeated trigger while it is pending, and none once the page is held', async () => {
        const first = deferred<unknown>();
        adapter.read.mockReturnValue(first.promise);
        const { list } = adapter.create();

        const reading = list.load(true);
        void list.load(true);
        list.ensure();
        expect(list.loading).toBe(true);
        expect(adapter.read).toHaveBeenCalledTimes(1);

        first.resolve(page('p1', 3, 3));
        await reading;
        list.ensure();
        expect(adapter.read).toHaveBeenCalledTimes(1);
        expect(shown(list)).toEqual(ids(3, 'p1'));
    });

    it('appends the next page after the captures it holds, then stops offering more', async () => {
        adapter.read.mockResolvedValueOnce(page('p1', 20, 25)).mockResolvedValueOnce(page('p2', 5, 25));
        const { list } = adapter.create();
        await list.load(true);
        await list.load();

        expect(adapter.request(adapter.read.mock.calls[1])).toMatchObject({ offset: 20, limit: 20 });
        expect(shown(list)).toEqual([...ids(20, 'p1'), ...ids(5, 'p2')]);
        expect(list.hasMore).toBe(false);
    });

    it('replaces the held pages with a fresh first page on reset', async () => {
        adapter.read.mockResolvedValueOnce(page('p1', 20, 25)).mockResolvedValueOnce(page('p2', 5, 25)).mockResolvedValueOnce(page('fresh', 20, 21));
        const { list } = adapter.create();
        await list.load(true);
        await list.load();
        await list.load(true);

        expect(adapter.request(adapter.read.mock.calls[2])).toMatchObject({ offset: 0 });
        expect(shown(list)).toEqual(ids(20, 'fresh'));
        expect(list.total).toBe(21);
    });

    it('keeps a failed read distinguishable from an empty one, and a retry recovers', async () => {
        adapter.read.mockRejectedValueOnce(new Error('offline'));
        const { list } = adapter.create();
        await list.load(true);
        expect([list.failed, list.loaded, list.loading, list.captures.length]).toEqual([true, false, false, 0]);

        adapter.read.mockResolvedValueOnce(page('none', 0, 0));
        await list.load(true);
        expect([list.failed, list.loaded, list.loading, list.captures.length, list.hasMore]).toEqual([false, true, false, 0, false]);
    });

    it('aborts its read on disposal and applies nothing that answers afterwards', async () => {
        const pending = deferred<unknown>();
        adapter.read.mockReturnValue(pending.promise);
        const { list } = adapter.create();
        const reading = list.load(true);
        const { signal } = adapter.request(adapter.read.mock.calls[0]);

        list.dispose();
        expect(signal.aborted).toBe(true);
        pending.resolve(page('late', 2, 2));
        await reading;
        expect([list.loaded, list.failed, list.captures.length]).toEqual([false, false, 0]);
    });

    it('does not report an aborted read as a failure', async () => {
        const pending = deferred<unknown>();
        adapter.read.mockReturnValue(pending.promise);
        const { list } = adapter.create();
        const reading = list.load(true);
        list.dispose();
        pending.reject(new DOMException('Aborted', 'AbortError'));
        await reading;
        expect(list.failed).toBe(false);
    });

    it('discards a page that answers after the visit\'s membership changed', async () => {
        const pending = deferred<unknown>();
        adapter.read.mockReturnValue(pending.promise);
        const { list, changeMembership } = adapter.create();
        const reading = list.load(true);

        changeMembership();
        pending.resolve(page('old', 2, 2));
        await reading;
        expect([list.loaded, list.captures.length]).toEqual([false, 0]);
    });

    it('treats a shared history change as a new list, so an edit elsewhere is never shown stale', async () => {
        adapter.read.mockResolvedValue(page('p1', 2, 2));
        const { list } = adapter.create();
        await list.load(true);
        expect(list.loaded).toBe(true);

        adapter.invalidateHistory();
        expect([list.loaded, list.captures.length]).toEqual([false, 0]);
    });

    it('does not keep a page that answered after its key moved on, even when the key comes back', async () => {
        const ownerRead = deferred<unknown>();
        adapter.read.mockReturnValueOnce(ownerRead.promise);
        const { list } = adapter.create();
        const reading = list.load(true);

        authStore.isAuthenticated = false;
        ownerRead.resolve(page('late', 2, 2));
        await reading;
        authStore.isAuthenticated = true;

        expect([list.loaded, list.captures.length]).toEqual([false, 0]);
    });

    it('hides owner pages the moment owner access ends, and a late owner read cannot land for the visitor', async () => {
        adapter.read.mockResolvedValueOnce(page('private', 2, 2));
        const { list } = adapter.create();
        await list.load(true);
        expect(shown(list)).toEqual(ids(2, 'private'));

        authStore.isAuthenticated = false;
        expect([list.loaded, list.captures.length, list.total]).toEqual([false, 0, 0]);

        // An owner read started just before the session ended answers after it.
        authStore.isAuthenticated = true;
        const ownerRead = deferred<unknown>();
        adapter.read.mockReturnValueOnce(ownerRead.promise);
        const reading = list.load(true);
        authStore.isAuthenticated = false;
        ownerRead.resolve(page('private-late', 2, 2));
        await reading;
        expect([list.loaded, list.captures.length]).toEqual([false, 0]);

        // The visitor's own read is separate and shows only what it was given.
        adapter.read.mockResolvedValueOnce(page('public', 1, 1));
        await list.load(true);
        expect(shown(list)).toEqual(ids(1, 'public'));
    });
});

describe('adapter requests', () => {
    it('reads a bird visit\'s captures inside the Explorer window', async () => {
        fetchVisitCaptures.mockResolvedValue({ captures: [], total: 0 });
        const window: VisitOptions = { startDate: '2026-10-27', endDate: '2026-10-28', startTime: '06:00', endTime: '18:00', onlyHidden: true };
        const visit = { visit_id: 'visit/1', capture_count: 2, end_time: '2026-10-28T09:05:00Z', representative: bird('lead') } as unknown as DetectionVisit;
        await new VisitCaptureList(() => ({ visit, window })).load(true);
        expect(fetchVisitCaptures).toHaveBeenCalledWith('visit/1', { ...window, limit: 20, offset: 0, signal: expect.any(AbortSignal) });
    });

    it('reads a Garden visit\'s captures in the view scope', async () => {
        fetchGardenVisitCaptures.mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
        const visit: GardenVisit = { id: 'visit-1', kind: 'visit', captureCount: 2, items: [garden('lead')] };
        await new GardenVisitCaptureList(() => ({ visit, scope: gardenScope })).load(true);
        expect(fetchGardenVisitCaptures).toHaveBeenCalledWith('visit-1', gardenScope, 0, { limit: 20, signal: expect.any(AbortSignal) });
    });
});
