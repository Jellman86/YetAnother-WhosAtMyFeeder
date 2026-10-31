import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchRangeFilterPreview, fetchRangeFilterSkips, fetchRangeFilterStatus } from './range-filter';

function respond(body: unknown): void {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })));
}

afterEach(() => vi.unstubAllGlobals());

describe('range filter client', () => {
    it('refuses a status that cannot say what the filter is doing', async () => {
        respond({});
        await expect(fetchRangeFilterStatus()).rejects.toThrow('incomplete range filter status');
    });

    it('reads a malformed preview or skip list as empty rather than failing the card', async () => {
        respond({});
        await expect(fetchRangeFilterPreview()).resolves.toMatchObject({ available: false, recently_seen: [], examples: [] });
        await expect(fetchRangeFilterSkips()).resolves.toEqual([]);
    });
});
