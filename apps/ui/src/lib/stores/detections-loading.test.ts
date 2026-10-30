import { buildReviewQueue } from '../utils/review-queue';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const fetchEvents = vi.fn();
const fetchEventsCount = vi.fn();

vi.mock('../api', () => ({
    fetchEvents,
    fetchEventsCount
}));

beforeEach(() => vi.resetAllMocks());

it('keeps an accepted species choice while an older list waits for its count', async () => {
    const { DetectionsStore } = await import('./detections.svelte');
    const store = new DetectionsStore();
    const before = { frigate_event: 'older-choice', manual_tagged: false, display_name: 'Dunnock', classification_input: { source: 'full_frame', is_cropped: false } };
    const after = { ...before, manual_tagged: true, classification_input: { source: 'owner_species_choice' } };
    let releaseCount: (value: { count: number }) => void = () => undefined;
    fetchEvents.mockResolvedValueOnce([before]).mockResolvedValueOnce([after]);
    fetchEventsCount.mockImplementationOnce(() => new Promise(resolve => { releaseCount = resolve; })).mockResolvedValueOnce({ count: 1 });
    store.historyStatus = 'ready';
    store.detections = [before as never];
    const olderRead = store.loadInitial();
    await Promise.resolve();
    store.recordOwnerSpeciesChoice(after as never);
    releaseCount({ count: 1 });
    await olderRead;
    expect(store.detections[0].manual_tagged).toBe(true);
    await vi.waitFor(() => expect(fetchEvents).toHaveBeenCalledTimes(2));
    await vi.waitFor(() => expect(store.isLoading).toBe(false));
    expect(store.detections[0].manual_tagged).toBe(true);
});

it('retains accepted owner evidence when fresh recent history omits that visit', async () => {
    const { DetectionsStore } = await import('./detections.svelte');
    const store = new DetectionsStore();
    fetchEvents.mockResolvedValue([]);
    fetchEventsCount.mockResolvedValue({ count: 0 });
    store.recordOwnerSpeciesChoice({ frigate_event: 'outside-recent-page', manual_tagged: true, classification_input: { source: 'owner_species_choice' } } as never);
    await vi.waitFor(() => expect(fetchEvents).toHaveBeenCalledTimes(1));
    await vi.waitFor(() => expect(store.isLoading).toBe(false));
    expect(store.detections).toEqual([]);
    expect(store.getDetectionPatch('outside-recent-page')).toMatchObject({ manual_tagged: true, classification_input: { source: 'owner_species_choice' } });
});

it('allows a later authoritative reanalysis to reopen a saved choice even after it leaves the page', async () => {
    const { DetectionsStore } = await import('./detections.svelte');
    const store = new DetectionsStore();
    const chosen = { frigate_event: 'reopened', manual_tagged: true, classification_input: { source: 'owner_species_choice' } };
    const reanalysed = { ...chosen, manual_tagged: false, classification_input: { source: 'full_frame', is_cropped: false } };
    fetchEvents.mockResolvedValueOnce([chosen]).mockResolvedValueOnce([reanalysed]).mockResolvedValueOnce([]);
    fetchEventsCount.mockResolvedValue({ count: 1 });
    store.recordOwnerSpeciesChoice(chosen as never);
    await vi.waitFor(() => expect(fetchEvents).toHaveBeenCalledTimes(1));
    await vi.waitFor(() => expect(store.isLoading).toBe(false));
    const queue = () => buildReviewQueue([], { reviewThreshold: 0.6, knownDetections: store.detections, localChoices: store.patchMap, newSpecies: [{ detection: reanalysed as never, sightings: 1 }] });
    expect(queue().total).toBe(0);
    await store.loadInitial();
    expect(queue().total).toBe(1);
    await store.loadInitial();
    expect(queue().total).toBe(1);
});

it('keeps a successfully saved species choice when its follow-up history request fails', async () => {
    const { DetectionsStore } = await import('./detections.svelte');
    const store = new DetectionsStore();
    store.historyStatus = 'ready';
    store.detections = [{ frigate_event: 'saved', manual_tagged: false } as never];
    fetchEvents.mockRejectedValue(new Error('503'));
    fetchEventsCount.mockResolvedValue({ count: 1 });
    store.recordOwnerSpeciesChoice({ frigate_event: 'saved', manual_tagged: true, classification_input: { source: 'owner_species_choice' } } as never);
    await vi.waitFor(() => expect(fetchEvents).toHaveBeenCalledTimes(1));
    await vi.waitFor(() => expect(store.isLoading).toBe(false));
    expect(store.historyStatus).toBe('ready');
    expect(store.detections[0].manual_tagged).toBe(true);
});

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

    it('says the history is unknown until it has been read, and keeps it known after a later failure', async () => {
        fetchEvents.mockResolvedValueOnce([]).mockRejectedValueOnce(new Error('offline'));
        fetchEventsCount.mockResolvedValue({ count: 0 });
        const { DetectionsStore } = await import('./detections.svelte');
        const store = new DetectionsStore();
        expect(store.historyStatus).toBe('pending');
        await store.loadInitial();
        expect(store.historyStatus).toBe('ready');
        await store.loadInitial();
        expect(store.historyStatus).toBe('ready');
        store.resetForAccessChange();
        expect(store.historyStatus).toBe('pending');
    });

    it('treats the first read as loaded history, not as an edit pages must reload after', async () => {
        const row = { frigate_event: 'first', display_name: 'Dunnock' };
        fetchEvents.mockResolvedValue([row]);
        fetchEventsCount.mockResolvedValue({ count: 1 });
        const { DetectionsStore } = await import('./detections.svelte');
        const store = new DetectionsStore();
        store.resetForAccessChange();
        await store.loadInitial();
        expect(store.historyStatus).toBe('ready');
        expect(store.detections).toEqual([row]);
        expect(store.mutationVersion).toBe(0);
    });

    it('counts a later read as a change only when it brings different history', async () => {
        const row = { frigate_event: 'first', display_name: 'Dunnock' };
        fetchEvents.mockResolvedValueOnce([row]).mockResolvedValueOnce([row]).mockResolvedValueOnce([row, { frigate_event: 'second' }]);
        fetchEventsCount.mockResolvedValue({ count: 1 });
        const { DetectionsStore } = await import('./detections.svelte');
        const store = new DetectionsStore();
        await store.loadInitial();
        await store.loadInitial();
        expect(store.mutationVersion).toBe(0);
        await store.loadInitial();
        expect(store.mutationVersion).toBe(1);
    });

    it('leaves the first read of an access to the app instead of starting a second one when asked to refresh', async () => {
        fetchEvents.mockResolvedValue([]);
        fetchEventsCount.mockResolvedValue({ count: 0 });
        const { DetectionsStore } = await import('./detections.svelte');
        const store = new DetectionsStore();
        await store.refreshIfStale();
        expect(fetchEvents).not.toHaveBeenCalled();
        await store.loadInitial();
        await store.refreshIfStale();
        expect(fetchEvents).toHaveBeenCalledTimes(1);
    });

    it('reports a first read that failed rather than an empty history', async () => {
        fetchEvents.mockRejectedValueOnce(new Error('offline'));
        fetchEventsCount.mockResolvedValue({ count: 0 });
        const { DetectionsStore } = await import('./detections.svelte');
        const store = new DetectionsStore();
        await store.loadInitial();
        expect(store.historyStatus).toBe('failed');
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

it('does not replay an owner summary read before a bird edit, and coalesces the follow-up load', async () => {
    const { DetectionsStore } = await import('./detections.svelte');
    const store = new DetectionsStore();
    let releaseOld: (value: unknown[]) => void = () => undefined;
    const before = { frigate_event: 'flock', bird_summary: { counted: 2, unknown: 0, excluded: 0, species: [], hint_only: false } };
    const after = { frigate_event: 'flock', bird_summary: { counted: 1, unknown: 0, excluded: 1, species: [], hint_only: false } };
    fetchEvents.mockImplementationOnce(() => new Promise((resolve) => { releaseOld = resolve; }))
        .mockResolvedValueOnce([after]);
    fetchEventsCount.mockResolvedValue({ count: 1 });

    const oldLoad = store.loadInitial();
    const refreshes = [store.refreshAfterOwnerEdit(), store.refreshAfterOwnerEdit(), store.refreshAfterOwnerEdit()];
    releaseOld([before]);
    await oldLoad;
    expect(store.detections).toEqual([]);
    await Promise.all(refreshes);

    expect(fetchEvents).toHaveBeenCalledTimes(2);
    expect(store.detections).toEqual([after]);
});

it('drops a queued owner refresh when access changes before it starts', async () => {
    const { DetectionsStore } = await import('./detections.svelte');
    const store = new DetectionsStore();
    let releaseOld: (value: unknown[]) => void = () => undefined;
    fetchEvents.mockImplementationOnce(() => new Promise((resolve) => { releaseOld = resolve; }));
    fetchEventsCount.mockResolvedValue({ count: 0 });

    const oldLoad = store.loadInitial();
    const refresh = store.refreshAfterOwnerEdit();
    store.resetForAccessChange();
    releaseOld([{ frigate_event: 'owner-event', bird_summary: { counted: 3 } }]);
    await Promise.all([oldLoad, refresh]);

    expect(fetchEvents).toHaveBeenCalledTimes(1);
    expect(store.detections).toEqual([]);
});

it('keeps authoritative bird summaries out of unrelated detection patches', async () => {
    const { DetectionsStore } = await import('./detections.svelte');
    const store = new DetectionsStore();
    const summary = { counted: 2, unknown: 1, excluded: 0, species: [], hint_only: false };
    fetchEvents.mockResolvedValue([{ frigate_event: 'flock', bird_summary: summary }]);
    fetchEventsCount.mockResolvedValue({ count: 1 });
    await store.loadInitial();

    // A manual parent tag can copy an older full Detection. A stats/SSE projection
    // can instead carry null because that endpoint does not read bird evidence.
    store.updateDetection({ frigate_event: 'flock', display_name: 'Blue Jay', bird_summary: { ...summary, counted: 99 } } as never);
    store.updateDetection({ frigate_event: 'flock', score: 0.8, bird_summary: null } as never);

    expect(store.detections[0].bird_summary).toEqual(summary);
    expect(store.getDetectionPatch('flock')).not.toHaveProperty('bird_summary');
    expect(store.getDetectionPatch('flock')).toMatchObject({ display_name: 'Blue Jay', score: 0.8 });
});
