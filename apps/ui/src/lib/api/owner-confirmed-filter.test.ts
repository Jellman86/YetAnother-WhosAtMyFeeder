import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchEvents, fetchEventsCount } from './events';
import { fetchVisits } from './visits';

function captureRequests(body: unknown): URL[] {
    const seen: URL[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
        seen.push(new URL(String(input instanceof Request ? input.url : input), 'http://test'));
        return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }));
    return seen;
}

afterEach(() => vi.unstubAllGlobals());

describe('the Owner confirmed filter reaches every Explorer read', () => {
    it('asks the visits, the captures and their count for owner-confirmed records', async () => {
        const seen = captureRequests([]);
        await fetchEvents({ ownerConfirmedOnly: true, requestKey: null });
        const counted = captureRequests({ count: 0, filtered: true });
        await fetchEventsCount({ ownerConfirmedOnly: true, requestKey: null });
        const visited = captureRequests({ visits: [], total: 0, gap_seconds: 120 });
        await fetchVisits({ ownerConfirmedOnly: true, requestKey: null }).catch(() => undefined);
        for (const url of [seen[0], counted[0], visited[0]]) {
            expect(url.searchParams.get('owner_confirmed_only')).toBe('true');
        }
    });

    it('leaves the parameter out while the filter is off', async () => {
        const seen = captureRequests([]);
        await fetchEvents({ requestKey: null });
        const counted = captureRequests({ count: 0, filtered: false });
        await fetchEventsCount({ requestKey: null });
        const visited = captureRequests({ visits: [], total: 0, gap_seconds: 120 });
        await fetchVisits({ ownerConfirmedOnly: false, requestKey: null }).catch(() => undefined);
        for (const url of [seen[0], counted[0], visited[0]]) {
            expect(url.searchParams.has('owner_confirmed_only')).toBe(false);
        }
    });
});
