import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchEvents, fetchEventsCount } from './events';

function captureRequests(body: unknown): URL[] {
    const seen: URL[] = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
        seen.push(new URL(String(input instanceof Request ? input.url : input), 'http://test'));
        return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }));
    return seen;
}

afterEach(() => vi.unstubAllGlobals());

const WINDOW = { startTime: '2026-11-24T10:15:30.250Z', endTime: '2026-11-25T10:15:30.250Z' };

describe('the capture list and its count read an exact window', () => {
    it('sends exact instants to the capture list and leaves the days out', async () => {
        const seen = captureRequests([]);
        await fetchEvents({ ...WINDOW, requestKey: null });
        expect(seen[0].pathname).toMatch(/\/events$/);
        expect(seen[0].searchParams.get('start_time')).toBe(WINDOW.startTime);
        expect(seen[0].searchParams.get('end_time')).toBe(WINDOW.endTime);
        expect(seen[0].searchParams.has('start_date')).toBe(false);
    });

    it('sends the same instants to the count', async () => {
        const seen = captureRequests({ count: 0, filtered: true });
        await fetchEventsCount({ ...WINDOW, requestKey: null });
        expect(seen[0].pathname).toMatch(/\/events\/count$/);
        expect(seen[0].searchParams.get('start_time')).toBe(WINDOW.startTime);
        expect(seen[0].searchParams.get('end_time')).toBe(WINDOW.endTime);
    });
});
