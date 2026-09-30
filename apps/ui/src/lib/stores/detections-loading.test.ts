import { beforeEach, describe, expect, it, vi } from 'vitest';

const fetchEvents = vi.fn();
const fetchEventsCount = vi.fn();

vi.mock('../api', () => ({
    fetchEvents,
    fetchEventsCount
}));

beforeEach(() => vi.resetAllMocks());

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

    it('refetches after an older in-flight response when guest history is invalidated', async () => {
        let release: (value: []) => void = () => undefined;
        fetchEvents.mockImplementationOnce(() => new Promise<[]>((resolve) => { release = resolve; }))
            .mockResolvedValueOnce([]);
        fetchEventsCount.mockResolvedValue({ count: 0 });
        const { DetectionsStore } = await import('./detections.svelte');
        const store = new DetectionsStore();
        const initial = store.loadInitial();
        const refresh = store.refreshPublicHistory();
        release([]);
        await Promise.all([initial, refresh]);
        expect(fetchEvents).toHaveBeenCalledTimes(2);
        expect(fetchEventsCount).toHaveBeenCalledTimes(2);
        expect(store.publicHistoryVersion).toBe(1);
    });
});

it('withdraws invalidated public rows when list/count refresh fails and signals consumers', async () => {
    const { DetectionsStore } = await import('./detections.svelte');
    const store = new DetectionsStore();
    store.addDetection({ frigate_event: 'now-private', detection_time: new Date().toISOString(), camera_name: 'Owner camera' } as never);
    fetchEvents.mockRejectedValueOnce(new Error('503'));
    fetchEventsCount.mockResolvedValueOnce({ count: 1 });
    await expect(store.refreshPublicHistory()).rejects.toThrow();
    expect(store.detections).toEqual([]);
    expect(store.totalToday).toBe(0);
    expect(store.patchMap.size).toBe(0);
    expect(store.publicHistoryVersion).toBe(1);
});

it('clears owner patches and rejects an old owner response after an access change', async () => {
    const { DetectionsStore } = await import('./detections.svelte');
    const store = new DetectionsStore();
    store.addDetection({ frigate_event: 'owner-event', camera_name: 'Private camera', detection_time: new Date().toISOString() } as never);
    store.progressMap.set('owner-event', {} as never);
    let releaseOwner: (value: unknown[]) => void = () => undefined;
    fetchEvents.mockImplementationOnce(() => new Promise((resolve) => { releaseOwner = resolve; }))
        .mockResolvedValueOnce([{ frigate_event: 'public-event', camera_name: 'Hidden' }]);
    fetchEventsCount.mockResolvedValue({ count: 1 });
    const oldLoad = store.loadInitial();
    store.resetForAccessChange();
    expect(store.detections).toEqual([]);
    expect(store.patchMap.size).toBe(0);
    expect(store.progressMap.size).toBe(0);
    const guestLoad = store.loadInitial();
    await guestLoad;
    releaseOwner([{ frigate_event: 'owner-event', camera_name: 'Private camera' }]);
    await oldLoad;
    expect(store.detections.map((item) => item.frigate_event)).toEqual(['public-event']);
    expect(store.isLoading).toBe(false);
});


it('does not release a pending guest request when a superseded owner request finishes', async () => {
    const { DetectionsStore } = await import('./detections.svelte');
    const store = new DetectionsStore();
    let releaseOwner: (value: unknown[]) => void = () => undefined;
    let releaseGuest: (value: unknown[]) => void = () => undefined;
    fetchEvents.mockImplementationOnce(() => new Promise((resolve) => { releaseOwner = resolve; }))
        .mockImplementationOnce(() => new Promise((resolve) => { releaseGuest = resolve; }));
    fetchEventsCount.mockResolvedValue({ count: 1 });
    const oldLoad = store.loadInitial();
    const oldInvalidation = store.refreshPublicHistory();
    store.resetForAccessChange();
    const guestLoad = store.loadInitial();
    releaseOwner([{ frigate_event: 'owner-event', camera_name: 'Private camera' }]);
    await Promise.all([oldLoad, oldInvalidation]);
    expect(store.isLoading).toBe(true);
    expect(store.detections).toEqual([]);
    const joiningGuest = store.loadInitial();
    expect(fetchEvents).toHaveBeenCalledTimes(2);
    releaseGuest([{ frigate_event: 'guest-event', camera_name: 'Hidden' }]);
    await Promise.all([guestLoad, joiningGuest]);
    expect(store.detections.map((item) => item.frigate_event)).toEqual(['guest-event']);
    expect(store.publicHistoryVersion).toBe(0);
});

it('withdraws invalidated rows even if only the count request fails', async () => {
    const { DetectionsStore } = await import('./detections.svelte');
    const store = new DetectionsStore();
    store.addDetection({ frigate_event: 'now-private', detection_time: new Date().toISOString() } as never);
    fetchEvents.mockResolvedValue([]);
    fetchEventsCount.mockRejectedValueOnce(new Error('503'));
    await expect(store.refreshPublicHistory()).rejects.toThrow();
    expect(store.detections).toEqual([]);
    expect(store.totalToday).toBe(0);
});
