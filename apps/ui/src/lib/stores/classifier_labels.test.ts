import { describe, expect, it, vi } from 'vitest';

import { ClassifierLabelsStore } from './classifier_labels.svelte';

describe('ClassifierLabelsStore', () => {
    it('reads nothing until a consumer asks for the labels', () => {
        const fetchLabels = vi.fn(async () => ({ labels: ['Dunnock'] }));
        const store = new ClassifierLabelsStore({ fetchLabels, canReadLabels: () => true });

        expect(fetchLabels).not.toHaveBeenCalled();
        expect(store.labels).toEqual([]);
    });

    it('shares one read between concurrent consumers and keeps the result', async () => {
        const fetchLabels = vi.fn(async () => ({ labels: ['Dunnock', 'European Robin'] }));
        const store = new ClassifierLabelsStore({ fetchLabels, canReadLabels: () => true });

        const [first, second] = await Promise.all([store.load(), store.load()]);
        const later = await store.load();

        expect(fetchLabels).toHaveBeenCalledOnce();
        expect(first).toEqual(['Dunnock', 'European Robin']);
        expect(second).toBe(first);
        expect(later).toBe(first);
        expect(store.labels).toBe(first);
    });

    it('never reads the labels for a visitor, who has no species search to fall back from', async () => {
        const fetchLabels = vi.fn(async () => ({ labels: ['Dunnock'] }));
        const store = new ClassifierLabelsStore({ fetchLabels, canReadLabels: () => false });

        await expect(store.load()).resolves.toEqual([]);
        expect(fetchLabels).not.toHaveBeenCalled();
    });

    it('answers a failed read with no labels and reads again on the next need', async () => {
        const fetchLabels = vi.fn()
            .mockRejectedValueOnce(new Error('offline'))
            .mockResolvedValueOnce({ labels: ['Dunnock'] });
        const store = new ClassifierLabelsStore({ fetchLabels, canReadLabels: () => true });

        await expect(store.load()).resolves.toEqual([]);
        await expect(store.load()).resolves.toEqual(['Dunnock']);
        expect(fetchLabels).toHaveBeenCalledTimes(2);
    });

    it('offers matching labels as species picker results when the catalogue search fails', async () => {
        const fetchLabels = vi.fn(async () => ({ labels: ['Dunnock', 'European Robin', 'American Robin'] }));
        const store = new ClassifierLabelsStore({ fetchLabels, canReadLabels: () => true });

        await expect(store.searchFallback(' robin ')).resolves.toEqual([
            { id: 'European Robin', display_name: 'European Robin', common_name: null, scientific_name: null },
            { id: 'American Robin', display_name: 'American Robin', common_name: null, scientific_name: null }
        ]);
        await expect(store.searchFallback('', 1)).resolves.toHaveLength(1);
    });
});
