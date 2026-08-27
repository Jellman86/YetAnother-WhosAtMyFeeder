import { describe, expect, it, vi } from 'vitest';

import type { Settings } from '../api';
import { SettingsStore } from './settings.svelte';

const ownerSettings = { cameras: ['birdcam'] } as unknown as Settings;

describe('SettingsStore', () => {
    it('loads settings when the session may read them', async () => {
        const fetchSettings = vi.fn(async () => ownerSettings);
        const store = new SettingsStore({ fetchSettings, canReadSettings: () => true });

        await store.load();

        expect(fetchSettings).toHaveBeenCalledOnce();
        expect(store.settings).toEqual(ownerSettings);
        expect(store.error).toBeNull();
    });

    it('does not request settings for a guest session', async () => {
        const fetchSettings = vi.fn(async () => ownerSettings);
        const store = new SettingsStore({ fetchSettings, canReadSettings: () => false });

        await store.load();

        expect(fetchSettings).not.toHaveBeenCalled();
        expect(store.settings).toBeNull();
        expect(store.error).toBeNull();
    });

    it('keeps the stale refresh from polling owner settings as a guest', async () => {
        const fetchSettings = vi.fn(async () => ownerSettings);
        const store = new SettingsStore({ fetchSettings, canReadSettings: () => false });

        await store.refreshIfStale();
        await store.refreshIfStale();

        expect(fetchSettings).not.toHaveBeenCalled();
    });

    it('starts reading again once the session gains owner access', async () => {
        const fetchSettings = vi.fn(async () => ownerSettings);
        let ownerAccess = false;
        const store = new SettingsStore({ fetchSettings, canReadSettings: () => ownerAccess });

        await store.load();
        expect(store.settings).toBeNull();

        ownerAccess = true;
        await store.load();

        expect(fetchSettings).toHaveBeenCalledOnce();
        expect(store.settings).toEqual(ownerSettings);
    });
});
