import { beforeEach, describe, expect, it, vi } from 'vitest';
import { init, register } from 'svelte-i18n';

const fetchFullVisit = vi.fn<(eventId: string) => Promise<boolean>>();
const toast = { success: vi.fn(), warning: vi.fn(), error: vi.fn() };
vi.mock('../stores/full-visit.svelte', () => ({ fullVisitStore: { fetchFullVisit: (eventId: string) => fetchFullVisit(eventId) } }));
vi.mock('../stores/toast.svelte', () => ({ toastStore: toast }));

const { fetchFullVisitAndReport } = await import('./full-visit-fetch');

register('en', () => Promise.resolve({}));
await init({ fallbackLocale: 'en', initialLocale: 'en' });

describe("fetching a capture's full clip says how it went", () => {
    beforeEach(() => {
        fetchFullVisit.mockReset();
        for (const say of Object.values(toast)) say.mockReset();
    });

    it('says the full clip is ready when the whole recording arrived', async () => {
        fetchFullVisit.mockResolvedValue(true);
        await fetchFullVisitAndReport('evt-1');
        expect(fetchFullVisit).toHaveBeenCalledWith('evt-1');
        expect(toast.success).toHaveBeenCalledWith('Full clip ready');
    });

    it('says only part arrived, and to retry, when the recording is still being written', async () => {
        fetchFullVisit.mockResolvedValue(false);
        await fetchFullVisitAndReport('evt-1');
        expect(toast.warning).toHaveBeenCalledWith('A partial clip is ready; retry shortly for the complete clip.');
    });

    it('states the cause when the fetch fails, and never throws', async () => {
        fetchFullVisit.mockRejectedValue(new Error('Frigate has no recording for this visit'));
        await expect(fetchFullVisitAndReport('evt-1')).resolves.toBeUndefined();
        expect(toast.error).toHaveBeenCalledWith('Frigate has no recording for this visit');
    });
});
