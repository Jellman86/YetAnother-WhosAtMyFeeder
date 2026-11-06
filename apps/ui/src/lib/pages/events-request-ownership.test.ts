import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchEvents, fetchEventsCount } from '../api/events';
import { DETECTIONS_STORE_REQUEST_KEYS } from '../stores/detections.svelte';
import { EVENTS_PAGE_REQUEST_KEYS } from './events-request-keys';

interface PendingFetch {
    url: string;
    signal: AbortSignal | null | undefined;
    resolve: (response: Response) => void;
}

function holdEveryFetch(): PendingFetch[] {
    const pending: PendingFetch[] = [];
    vi.stubGlobal('fetch', vi.fn((url: string, options?: RequestInit) => new Promise<Response>((resolve, reject) => {
        options?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
        pending.push({ url, signal: options?.signal, resolve });
    })));
    return pending;
}

const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });

afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

describe('event request cancellation ownership', () => {
    it('gives every Explorer page key a different owner from the dashboard store', () => {
        const page = Object.values(EVENTS_PAGE_REQUEST_KEYS);
        const store = Object.values(DETECTIONS_STORE_REQUEST_KEYS);
        expect(new Set(page).size).toBe(page.length);
        expect(page.filter((key) => (store as string[]).includes(key))).toEqual([]);
    });

    it('lets a newer page read cancel the older page read without cancelling the store\'s reads', async () => {
        const pending = holdEveryFetch();
        const olderPage = fetchEvents({ offset: 0, requestKey: EVENTS_PAGE_REQUEST_KEYS.list }).catch((error: unknown) => error);
        const storeList = fetchEvents({ limit: 3, requestKey: DETECTIONS_STORE_REQUEST_KEYS.list });
        const storeCount = fetchEventsCount({ requestKey: DETECTIONS_STORE_REQUEST_KEYS.count });
        const pageCount = fetchEventsCount({ requestKey: EVENTS_PAGE_REQUEST_KEYS.count });
        const newerPage = fetchEvents({ offset: 25, requestKey: EVENTS_PAGE_REQUEST_KEYS.list });

        expect(await olderPage).toMatchObject({ name: 'AbortError' });
        expect(pending.map((request) => request.signal?.aborted)).toEqual([true, false, false, false, false]);

        pending[1].resolve(json([{ frigate_event: 'store-row' }]));
        pending[2].resolve(json({ count: 7 }));
        pending[3].resolve(json({ count: 25 }));
        pending[4].resolve(json([{ frigate_event: 'page-row' }]));
        await expect(storeList).resolves.toEqual([{ frigate_event: 'store-row' }]);
        await expect(storeCount).resolves.toMatchObject({ count: 7 });
        await expect(pageCount).resolves.toMatchObject({ count: 25 });
        await expect(newerPage).resolves.toEqual([{ frigate_event: 'page-row' }]);
    });

    it('does not let a store refresh cancel a deep-linked event the page is resolving', async () => {
        const pending = holdEveryFetch();
        const deepLink = fetchEvents({ eventId: 'far-away', limit: 1, fields: 'detail', requestKey: EVENTS_PAGE_REQUEST_KEYS.deepLink });
        void fetchEvents({ limit: 3, requestKey: DETECTIONS_STORE_REQUEST_KEYS.list }).catch(() => undefined);
        void fetchEvents({ limit: 3, requestKey: DETECTIONS_STORE_REQUEST_KEYS.list }).catch(() => undefined);
        void fetchEvents({ offset: 25, requestKey: EVENTS_PAGE_REQUEST_KEYS.list }).catch(() => undefined);

        expect(pending[0].signal?.aborted).toBe(false);
        expect(new URL(pending[0].url, 'http://ui.test').searchParams.get('event_id')).toBe('far-away');
        pending[0].resolve(json([{ frigate_event: 'far-away' }]));
        await expect(deepLink).resolves.toEqual([{ frigate_event: 'far-away' }]);
    });
});
