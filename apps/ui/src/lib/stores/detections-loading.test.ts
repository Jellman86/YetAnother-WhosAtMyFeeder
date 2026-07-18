import { beforeEach, describe, expect, it, vi } from 'vitest';

const fetchEvents = vi.fn();
const fetchEventsCount = vi.fn();

vi.mock('../api', () => ({
    fetchEvents,
    fetchEventsCount
}));

describe('DetectionsStore loading', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('shares one initial load across concurrent application consumers', async () => {
        fetchEvents.mockResolvedValue([]);
        fetchEventsCount.mockResolvedValue({ count: 0 });
        const { DetectionsStore } = await import('./detections.svelte');
        const store = new DetectionsStore();

        await Promise.all([store.loadInitial(), store.loadInitial(), store.loadInitial()]);

        expect(fetchEvents).toHaveBeenCalledTimes(1);
        expect(fetchEventsCount).toHaveBeenCalledTimes(1);
    });
});
