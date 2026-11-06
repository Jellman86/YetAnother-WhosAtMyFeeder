import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { GardenCapture, GardenServerVisit } from '../api/garden';

const fetchGardenVisitCaptures = vi.fn();
vi.mock('../api/garden', () => ({ fetchGardenVisitCaptures: (...args: unknown[]) => fetchGardenVisitCaptures(...args) }));

const { GardenVisitViewer } = await import('./garden-visit-viewer.svelte');
const { gardenHistory } = await import('../stores/garden_history.svelte');

function capture(id: string, overrides: Partial<GardenCapture> = {}): GardenCapture {
    return {
        id, camera: 'patio', frigate_label: 'cat', observed_at: '2026-10-27T09:00:00Z', status: 'confirmed',
        reviewed_at: null, snapshot_url: null, ...overrides
    };
}

function visit(count: number): GardenServerVisit {
    return { id: 'visit-1', kind: 'visit', start_time: '2026-10-27T09:00:00Z', end_time: '2026-10-27T09:01:00Z', capture_count: count, representative: capture('b') };
}

const scope = { start: '2026-10-26T09:00:00Z', end: '2026-10-27T09:00:00Z', status: 'reviewable' as const };

describe('GardenVisitViewer', () => {
    beforeEach(() => fetchGardenVisitCaptures.mockReset());

    it('opens a single capture without reading the visit', () => {
        const viewer = new GardenVisitViewer(() => scope, () => 'failed');
        viewer.open(visit(1));
        expect(viewer.capture?.id).toBe('b');
        expect(viewer.group?.items.map((item) => item.id)).toEqual(['b']);
        expect(fetchGardenVisitCaptures).not.toHaveBeenCalled();
    });

    it('reads every photo of a grouped visit in the log window and keeps the opened photo selected', async () => {
        fetchGardenVisitCaptures.mockResolvedValue({ items: [capture('a'), capture('b'), capture('c')], total: 3, limit: 128, offset: 0 });
        const viewer = new GardenVisitViewer(() => scope, () => 'failed');
        viewer.open(visit(3));
        await vi.waitFor(() => expect(viewer.loading).toBe(false));
        expect(fetchGardenVisitCaptures).toHaveBeenCalledWith('visit-1', scope, 0);
        expect(viewer.group?.items.map((item) => item.id)).toEqual(['a', 'b', 'c']);
        expect(viewer.capture?.id).toBe('b');
    });

    it('opens the selected capture beyond the first record page without jumping to the visit photo', async () => {
        const chosen = capture('capture-149');
        const items = Array.from({ length: 22 }, (_, index) => capture(`capture-${128 + index}`));
        fetchGardenVisitCaptures.mockResolvedValue({ items, total: 150, limit: 128, offset: 128 });
        const viewer = new GardenVisitViewer(() => scope, () => 'failed');
        viewer.open(visit(150), { capture: chosen, index: 149 });
        expect(viewer.capture?.id).toBe(chosen.id);
        await vi.waitFor(() => expect(viewer.loading).toBe(false));
        expect(fetchGardenVisitCaptures).toHaveBeenCalledWith('visit-1', scope, 128);
        expect(viewer.capture?.id).toBe(chosen.id);
        expect(viewer.offset).toBe(128);
    });

    it('drops a read that finishes after the record was closed', async () => {
        let resolve: (value: unknown) => void = () => undefined;
        fetchGardenVisitCaptures.mockReturnValue(new Promise((done) => (resolve = done)));
        const viewer = new GardenVisitViewer(() => scope, () => 'failed');
        viewer.open(visit(3));
        viewer.close();
        resolve({ items: [capture('a')], total: 1, limit: 128, offset: 0 });
        await Promise.resolve();
        expect(viewer.capture).toBeNull();
        expect(viewer.group).toBeNull();
    });

    it('states a failed read in words and keeps the opened photo', async () => {
        fetchGardenVisitCaptures.mockResolvedValueOnce({ items: [capture('b')], total: 3, limit: 128, offset: 0 });
        const viewer = new GardenVisitViewer(() => scope, () => 'Could not load the photos.');
        viewer.open(visit(3));
        await vi.waitFor(() => expect(viewer.loading).toBe(false));
        fetchGardenVisitCaptures.mockRejectedValueOnce('offline');
        await viewer.page(0, false);
        expect(viewer.error).toBe('Could not load the photos.');
        expect(viewer.capture?.id).toBe('b');
    });

    it('moves to the next photo when a review takes a capture out of the log', async () => {
        fetchGardenVisitCaptures.mockResolvedValue({ items: [capture('a'), capture('b'), capture('c')], total: 3, limit: 128, offset: 0 });
        const viewer = new GardenVisitViewer(() => scope, () => 'failed');
        viewer.open(visit(3));
        await vi.waitFor(() => expect(viewer.loading).toBe(false));
        const historyVersion = gardenHistory.version;
        viewer.changed(capture('b', { status: 'dismissed' }));
        expect(gardenHistory.version).toBe(historyVersion + 1);
        expect(viewer.capture?.id).toBe('c');
        expect(viewer.group?.items.map((item) => item.id)).toEqual(['a', 'c']);
        expect(viewer.group?.captureCount).toBe(2);
    });

    it('keeps a capture that still belongs, on its own once its state changed', async () => {
        fetchGardenVisitCaptures.mockResolvedValue({ items: [capture('a', { status: 'pending' }), capture('b')], total: 2, limit: 128, offset: 0 });
        const viewer = new GardenVisitViewer(() => scope, () => 'failed');
        viewer.open({ ...visit(2), representative: capture('a', { status: 'pending' }) });
        await vi.waitFor(() => expect(viewer.loading).toBe(false));
        viewer.changed(capture('a', { status: 'confirmed' }));
        expect(viewer.capture?.status).toBe('confirmed');
        expect(viewer.group).toEqual({ id: 'a', kind: 'visit', captureCount: 1, items: [capture('a', { status: 'confirmed' })] });
    });
});

it('detaches a corrected capture when canonical species changes even if its common name is unchanged', async () => {
    const owner = { species_id: 1, name: 'Fox', scientific_name: 'Vulpes vulpes', changed_at: '2026-10-29T00:00:00Z' };
    const first = capture('a', { owner_identification: owner });
    fetchGardenVisitCaptures.mockResolvedValue({ items: [first, capture('b', { owner_identification: owner })], total: 2, limit: 128, offset: 0 });
    const viewer = new GardenVisitViewer(() => scope, () => 'failed');
    viewer.open({ ...visit(2), representative: first });
    await vi.waitFor(() => expect(viewer.loading).toBe(false));
    viewer.changed({ ...first, owner_identification: { ...owner, species_id: 2, scientific_name: 'Vulpes lagopus' } });
    expect(viewer.group?.captureCount).toBe(1);
    expect(viewer.capture?.owner_identification?.species_id).toBe(2);
});
