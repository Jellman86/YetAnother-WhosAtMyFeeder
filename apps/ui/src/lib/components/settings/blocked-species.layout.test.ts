import { describe, expect, it } from 'vitest';
import detectionSettingsSource from './DetectionSettings.svelte?raw';
import settingsPageSource from '../../pages/Settings.svelte?raw';

describe('blocked species picker wiring', () => {
    it('threads blocked species state through the settings page into detection settings', () => {
        expect(settingsPageSource).toContain('blockedSpecies');
        expect(settingsPageSource).toContain('bind:blockedSpecies');
        expect(settingsPageSource).toContain('migrateLegacyBlockedLabels');
        expect(detectionSettingsSource).toContain('blockedSpecies = $bindable<');
    });

    it('always offers the typed text as a raw label, since search cannot name everything', () => {
        // Some model labels carry no name the search can resolve, and a result
        // without canonical identity used to no-op silently when clicked. The
        // species on a detection card must always be blockable (#311): the
        // typed text is offered exactly as written, and an unresolvable result
        // falls back to a raw label instead of doing nothing.
        expect(detectionSettingsSource).toContain('data-blocked-label-escape-hatch');
        expect(detectionSettingsSource).toContain('settings.detection.block_exact_label');
        expect(detectionSettingsSource).toContain('addBlockedLabelText(result.display_name || result.id)');
    });
});
