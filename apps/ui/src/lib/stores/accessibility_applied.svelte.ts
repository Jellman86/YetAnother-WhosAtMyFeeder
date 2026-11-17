/**
 * The accessibility that applies on this device, in one place: the shell's classes, the announcer,
 * the Settings device card and every page that gates its own motion read it, so the order is written
 * once. This device's choice wins; then, on a device that follows the default, the defaults being
 * edited in Settings; then the saved defaults an owner reads; then the public payload a guest reads.
 */
import type { Settings } from '../api';
import { accessibilityDevice, effectiveChoice, type AccessibilityChoice } from '../settings/accessibility-device.svelte';
import { accessibilityPreview } from './accessibility_preview.svelte';
import { authStore } from './auth.svelte';
import { settingsStore } from './settings.svelte';

/** The public payload's choices, which a guest, who cannot read the settings, also receives. */
type PublicChoices = Record<AccessibilityChoice, boolean>;

const SAVED_FIELD = {
    highContrast: 'accessibility_high_contrast',
    dyslexiaFont: 'accessibility_dyslexia_font',
    reducedMotion: 'accessibility_reduced_motion',
    liveAnnouncements: 'accessibility_live_announcements'
} as const satisfies Record<AccessibilityChoice, keyof Settings>;

/** The default for everyone: the saved settings where they were read, else the public payload. */
export function accessibilityDefault(key: AccessibilityChoice, saved: Settings | null | undefined, publicChoices: PublicChoices): boolean {
    return saved?.[SAVED_FIELD[key]] ?? publicChoices[key];
}

function publicChoices(): PublicChoices {
    return {
        highContrast: authStore.highContrast,
        dyslexiaFont: authStore.dyslexiaFont,
        reducedMotion: authStore.reducedMotion,
        liveAnnouncements: authStore.liveAnnouncements
    };
}

class AccessibilityApplied {
    /** What everyone without a choice of their own follows on this install. */
    defaultFor(key: AccessibilityChoice): boolean {
        return accessibilityDefault(key, settingsStore.settings, publicChoices());
    }

    get highContrast(): boolean {
        return effectiveChoice(accessibilityDevice.get('highContrast'), accessibilityPreview.highContrast, this.defaultFor('highContrast'));
    }

    get dyslexiaFont(): boolean {
        return effectiveChoice(accessibilityDevice.get('dyslexiaFont'), accessibilityPreview.dyslexiaFont, this.defaultFor('dyslexiaFont'));
    }

    get reducedMotion(): boolean {
        return effectiveChoice(accessibilityDevice.get('reducedMotion'), accessibilityPreview.reducedMotion, this.defaultFor('reducedMotion'));
    }

    /** Spoken updates have no preview: nothing is announced while a default is edited. */
    get liveAnnouncements(): boolean {
        return effectiveChoice(accessibilityDevice.get('liveAnnouncements'), null, this.defaultFor('liveAnnouncements'));
    }
}

export const accessibilityApplied = new AccessibilityApplied();

/**
 * Whether motion should be left out here: this device's effective choice, or the system's own
 * reduce-motion setting, which is always followed as well.
 */
export function prefersReducedMotion(): boolean {
    const system = typeof window !== 'undefined' && typeof window.matchMedia === 'function'
        && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    return system || accessibilityApplied.reducedMotion;
}
