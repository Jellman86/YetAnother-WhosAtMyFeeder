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

    it('answers every reader in one page load with a single request', async () => {
        let release!: (settings: Settings) => void;
        const fetchSettings = vi.fn(() => new Promise<Settings>((resolve) => { release = resolve; }));
        const store = new SettingsStore({ fetchSettings, canReadSettings: () => true });

        const shell = store.load();
        const header = store.read();
        const page = store.read(5_000);
        release(ownerSettings);
        await shell;

        expect(await header).toEqual(ownerSettings);
        expect(await page).toEqual(ownerSettings);
        expect(await store.read()).toEqual(ownerSettings);
        expect(fetchSettings).toHaveBeenCalledOnce();
    });

    it('reads again for a reader that needs a copy fresher than the one held', async () => {
        vi.useFakeTimers();
        try {
            const fetchSettings = vi.fn(async () => ownerSettings);
            const store = new SettingsStore({ fetchSettings, canReadSettings: () => true });
            await store.load();

            vi.advanceTimersByTime(5_001);
            await store.read(5_000);
            expect(fetchSettings).toHaveBeenCalledTimes(2);

            // A save hands the store the saved copy, which is as fresh as a read.
            vi.advanceTimersByTime(60_000);
            store.update(ownerSettings);
            await store.read(5_000);
            expect(fetchSettings).toHaveBeenCalledTimes(2);
        } finally {
            vi.useRealTimers();
        }
    });

    it('fails a shared read plainly when the settings cannot be read', async () => {
        const failing = new SettingsStore({ fetchSettings: vi.fn(async () => { throw new Error('backend away'); }), canReadSettings: () => true });
        vi.spyOn(console, 'error').mockImplementation(() => {});
        await expect(failing.read()).rejects.toThrow('backend away');

        const guest = new SettingsStore({ fetchSettings: vi.fn(async () => ownerSettings), canReadSettings: () => false });
        await expect(guest.read()).rejects.toThrow('not available');
        vi.restoreAllMocks();
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

it('does not restore owner settings after logout while a request is in flight', async () => {
    let ownerAccess = true;
    let release: (value: Settings) => void = () => undefined;
    const store = new SettingsStore({ fetchSettings: () => new Promise((resolve) => { release = resolve; }), canReadSettings: () => ownerAccess });
    const oldLoad = store.load(); ownerAccess = false; store.clear(); release(ownerSettings); await oldLoad;
    expect(store.settings).toBeNull(); expect(store.error).toBeNull(); expect(store.isLoading).toBe(false);
});

it('does not let the old owner request release a pending valid new owner load', async () => {
    let releaseOld: (value: Settings) => void = () => undefined;
    let releaseNew: (value: Settings) => void = () => undefined;
    const fetchSettings = vi.fn().mockImplementationOnce(() => new Promise((resolve) => { releaseOld = resolve; }))
        .mockImplementationOnce(() => new Promise((resolve) => { releaseNew = resolve; }));
    const store = new SettingsStore({ fetchSettings, canReadSettings: () => true });
    const previous = store.load(); store.clear(); const current = store.load();
    releaseOld(ownerSettings); await previous;
    expect(store.isLoading).toBe(true); expect(store.settings).toBeNull();
    const joiningCurrent = store.load(); expect(fetchSettings).toHaveBeenCalledTimes(2);
    const newSettings = { cameras: ['new-owner-camera'] } as unknown as Settings;
    releaseNew(newSettings); await Promise.all([current, joiningCurrent]);
    expect(store.settings).toEqual(newSettings); expect(store.isLoading).toBe(false);
});

it('does not apply an owner response after access is revoked even before clear runs', async () => {
    let ownerAccess = true;
    let release: (value: Settings) => void = () => undefined;
    const store = new SettingsStore({ fetchSettings: () => new Promise((resolve) => { release = resolve; }), canReadSettings: () => ownerAccess });
    const pending = store.load(); ownerAccess = false; release(ownerSettings); await pending;
    expect(store.settings).toBeNull(); expect(store.isLoading).toBe(false);
});

it('does not repopulate guest settings from a completed owner save', () => {
    const store = new SettingsStore({ canReadSettings: () => false });
    store.update(ownerSettings);
    expect(store.settings).toBeNull();
});

it('continues applying saved settings while owner access is valid', () => {
    const store = new SettingsStore({ canReadSettings: () => true });
    store.update(ownerSettings);
    expect(store.settings).toEqual(ownerSettings);
});
