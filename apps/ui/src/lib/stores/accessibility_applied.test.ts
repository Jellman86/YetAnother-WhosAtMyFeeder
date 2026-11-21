import { afterEach, describe, expect, it } from 'vitest';
import type { Settings } from '../api';
import { accessibilityApplied, accessibilityDefault } from './accessibility_applied.svelte';
import { accessibilityDevice } from '../settings/accessibility-device.svelte';
import { accessibilityPreview, previewedValue } from './accessibility_preview.svelte';
import { authStore } from './auth.svelte';
import { settingsStore } from './settings.svelte';

const PUBLIC_OFF = { highContrast: false, dyslexiaFont: false, reducedMotion: false, liveAnnouncements: true };

describe('the default for everyone', () => {
    it('is the saved settings an owner reads, else the public payload a guest reads', () => {
        const saved = { accessibility_high_contrast: true, accessibility_live_announcements: false } as Settings;
        expect(accessibilityDefault('highContrast', saved, PUBLIC_OFF)).toBe(true);
        expect(accessibilityDefault('liveAnnouncements', saved, PUBLIC_OFF)).toBe(false);
        // A guest is refused the settings, so the public payload is the default.
        expect(accessibilityDefault('highContrast', null, { ...PUBLIC_OFF, highContrast: true })).toBe(true);
        // Saved settings read before the field existed fall back to the payload too.
        expect(accessibilityDefault('reducedMotion', {} as Settings, { ...PUBLIC_OFF, reducedMotion: true })).toBe(true);
    });
});

describe('the unsaved default shown while Settings is open', () => {
    const saved = { highContrast: false, dyslexiaFont: true, reducedMotion: false };
    it('is the draft only where it differs from what is saved, and nothing before the saved copy is read', () => {
        expect(previewedValue(null, 'highContrast')).toBeNull();
        expect(previewedValue({ draft: { ...saved, highContrast: true }, saved: null }, 'highContrast')).toBeNull();
        expect(previewedValue({ draft: { ...saved, highContrast: true }, saved }, 'highContrast')).toBe(true);
        expect(previewedValue({ draft: saved, saved }, 'dyslexiaFont')).toBeNull();
    });
});

describe('what applies on this device', () => {
    afterEach(() => {
        for (const key of ['highContrast', 'dyslexiaFont', 'reducedMotion', 'liveAnnouncements'] as const) accessibilityDevice.set(key, null);
        settingsStore.settings = null;
        authStore.highContrast = false;
        authStore.liveAnnouncements = true;
    });

    it('is this device\'s choice, then the default being edited, then the saved default, for a guest too', () => {
        // A guest: no settings, the public payload asks for high contrast.
        authStore.highContrast = true;
        expect(accessibilityApplied.highContrast).toBe(true);
        accessibilityDevice.set('highContrast', false);
        expect(accessibilityApplied.highContrast).toBe(false);

        // An owner editing the default: the preview shows only where the device follows the default.
        accessibilityDevice.set('highContrast', null);
        settingsStore.settings = { accessibility_high_contrast: false, accessibility_reduced_motion: false } as Settings;
        const disconnect = accessibilityPreview.connect(() => ({
            draft: { highContrast: true, dyslexiaFont: false, reducedMotion: true },
            saved: { highContrast: false, dyslexiaFont: false, reducedMotion: false }
        }));
        expect(accessibilityApplied.highContrast).toBe(true);
        accessibilityDevice.set('reducedMotion', false);
        expect(accessibilityApplied.reducedMotion).toBe(false);
        disconnect();
        expect(accessibilityApplied.highContrast).toBe(false);
    });

    it('speaks new visits by this device\'s choice, whatever the default', () => {
        settingsStore.settings = { accessibility_live_announcements: true } as Settings;
        expect(accessibilityApplied.liveAnnouncements).toBe(true);
        accessibilityDevice.set('liveAnnouncements', false);
        expect(accessibilityApplied.liveAnnouncements).toBe(false);
    });
});
