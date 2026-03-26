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
});
