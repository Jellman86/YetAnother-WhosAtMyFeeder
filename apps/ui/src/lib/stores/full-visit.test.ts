import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api', () => ({
    checkRecordingClipAvailable: vi.fn(),
    fetchRecordingClip: vi.fn(),
}));

describe('FullVisitStore', () => {
    const createStorage = () => {
        const values = new Map<string, string>();
        return {
            getItem(key: string) {
                return values.has(key) ? values.get(key)! : null;
            },
            setItem(key: string, value: string) {
                values.set(key, value);
            },
            removeItem(key: string) {
                values.delete(key);
            },
            clear() {
                values.clear();
            }
        };
    };

    beforeEach(() => {
        vi.resetModules();
        vi.clearAllMocks();
    });

    it('marks a recording clip as fetched when the backend reports a persisted full visit', async () => {
        const api = await import('../api');
        vi.mocked(api.checkRecordingClipAvailable).mockResolvedValue({
            available: true,
            fetched: true
        });

        const { FullVisitStore } = await import('./full-visit.svelte');
        const store = new FullVisitStore(createStorage());

        await store.ensureAvailability('evt-1');

        expect(store.isAvailable('evt-1')).toBe(true);
        expect(store.isFetched('evt-1')).toBe(true);
        expect(store.getPreferredClipVariant('evt-1')).toBe('recording');
    });

    it('restores fetched full-visit preference from local storage on a new store instance', async () => {
        const api = await import('../api');
        vi.mocked(api.fetchRecordingClip).mockResolvedValue({
            event_id: 'evt-2',
            status: 'ready',
            clip_variant: 'recording',
            cached: false
        });

        const { FullVisitStore } = await import('./full-visit.svelte');
        const storage = createStorage();
        const firstStore = new FullVisitStore(storage);
        await firstStore.fetchFullVisit('evt-2');

        const secondStore = new FullVisitStore(storage);
        expect(secondStore.isFetched('evt-2')).toBe(true);
        expect(secondStore.getPreferredClipVariant('evt-2')).toBe('recording');
    });
});
