import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./core', () => ({ API_BASE: '/api', apiFetch: vi.fn(), handleResponse: vi.fn() }));
import { apiFetch, handleResponse } from './core';
import { subscribeSettingsUpdates, updateSettings } from './settings';

describe('local confirmed settings updates', () => {
    beforeEach(() => {
        vi.mocked(apiFetch).mockResolvedValue(new Response('{}'));
        vi.mocked(handleResponse).mockReset();
        vi.mocked(handleResponse).mockResolvedValue({ status: 'updated' });
    });

    it('notifies subscribers only after a settings write succeeds and unsubscribes cleanly', async () => {
        const listener = vi.fn();
        const unsubscribe = subscribeSettingsUpdates(listener);
        await updateSettings({ cameras: ['feeder'] });
        expect(listener).toHaveBeenCalledExactlyOnceWith({ cameras: ['feeder'] });
        unsubscribe();
        await updateSettings({ cameras: ['nestbox'] });
        expect(listener).toHaveBeenCalledTimes(1);
    });

    it('does not publish failed writes as saved configuration', async () => {
        const listener = vi.fn();
        const unsubscribe = subscribeSettingsUpdates(listener);
        vi.mocked(handleResponse).mockRejectedValueOnce(new Error('Read-only config volume'));
        await expect(updateSettings({ location_latitude: 12.5, location_longitude: -45.25 })).rejects.toThrow('Read-only config volume');
        expect(listener).not.toHaveBeenCalled();
        unsubscribe();
    });

    it('does not report a persisted write as failed when a subscriber fails', async () => {
        const log = vi.spyOn(console, 'error').mockImplementation(() => {});
        const unsubscribe = subscribeSettingsUpdates(() => { throw new Error('View failed'); });
        await expect(updateSettings({ telemetry_enabled: false })).resolves.toEqual({ status: 'updated' });
        expect(log).toHaveBeenCalledWith('Failed to reconcile saved settings');
        unsubscribe();
        log.mockRestore();
    });
});
