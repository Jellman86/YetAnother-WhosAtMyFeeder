import { describe, expect, it } from 'vitest';
import appSource from './App.svelte?raw';
import authStoreSource from './lib/stores/auth.svelte.ts?raw';
import settingsPageSource from './lib/pages/Settings.svelte?raw';

/**
 * High contrast, the dyslexia font and reduced motion are applied from the
 * settings store, and `/api/settings` is owner-only. Without a public route for
 * them, a visitor who needs high contrast on a shared instance cannot have it,
 * and the owner has no way to give it to them.
 */
describe('accessibility choices reaching a public visitor', () => {
    it('falls back to the public status payload when settings are unreadable', () => {
        expect(appSource).toContain(
            'settingsStore.settings?.accessibility_high_contrast ?? authStore.highContrast'
        );
        expect(appSource).toContain(
            'settingsStore.settings?.accessibility_dyslexia_font ?? authStore.dyslexiaFont'
        );
        expect(appSource).toContain(
            'settingsStore.settings?.accessibility_reduced_motion ?? authStore.reducedMotion'
        );
    });

    it('reads both from auth status, which a guest can load', () => {
        expect(authStoreSource).toContain('this.highContrast = status.accessibility_high_contrast ?? false');
        expect(authStoreSource).toContain('this.dyslexiaFont = status.accessibility_dyslexia_font ?? false');
        expect(authStoreSource).toContain('this.reducedMotion = status.accessibility_reduced_motion ?? false');
    });

    it('derives the values rather than syncing state in an effect', () => {
        // The effect is for the DOM, which is outside Svelte. Working out what
        // should be applied is not (CLAUDE.md section 4).
        expect(appSource).toMatch(/const highContrast = \$derived\(/);
        expect(appSource).toMatch(/const dyslexiaFont = \$derived\(/);
        expect(appSource).toMatch(/const reducedMotion = \$derived\(/);
    });

    it('defaults both off, since either changes the whole interface', () => {
        expect(authStoreSource).toContain('highContrast = $state(false);');
        expect(authStoreSource).toContain('dyslexiaFont = $state(false);');
        expect(authStoreSource).toContain('reducedMotion = $state(false);');
    });

    it('applies reduced motion on every route, not only while Settings is open', () => {
        // The class was previously added by the Settings page alone, so after a
        // reload a reader who went straight to the audio history got animation
        // regardless of the setting. AudioHistory reads the class, so applying
        // it at the app root is what makes the setting mean anything.
        expect(appSource).toContain("classList.toggle('reduced-motion', reducedMotion)");
        expect(settingsPageSource).not.toContain("classList.add('reduced-motion')");
        expect(settingsPageSource).not.toContain("classList.add('high-contrast')");
        expect(settingsPageSource).not.toContain("classList.add('font-dyslexic')");
    });
});
