import { afterEach, describe, expect, it } from 'vitest';
import type { PublicSettings, Settings } from '../api';
import { publicSettingsStore, savedVisitGapMs } from './public_settings.svelte';
import { settingsStore } from './settings.svelte';

const projection = (visit_gap_seconds: number): PublicSettings => ({
    classification_threshold: 0.7,
    ebird_default_days_back: 14,
    clips_enabled: true,
    recording_clip_enabled: false,
    bird_counting_enabled: false,
    visit_gap_seconds
});

describe('savedVisitGapMs', () => {
    afterEach(() => {
        publicSettingsStore.settings = null;
        settingsStore.settings = null;
    });

    it('groups by the default minute until any setting has been read', () => {
        expect(savedVisitGapMs()).toBe(60_000);
    });

    it("gives a guest the owner's gap from the public settings (#1044)", () => {
        publicSettingsStore.settings = projection(12);
        expect(savedVisitGapMs()).toBe(12_000);
    });

    it("prefers the owner's own settings, so a saved gap applies without waiting for the projection", () => {
        publicSettingsStore.settings = projection(60);
        settingsStore.settings = { visit_gap_seconds: 20 } as Settings;
        expect(savedVisitGapMs()).toBe(20_000);
    });
});
