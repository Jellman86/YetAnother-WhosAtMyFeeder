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
