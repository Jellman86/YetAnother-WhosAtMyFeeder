import { describe, expect, it } from 'vitest';
import appSource from './App.svelte?raw';
import authStoreSource from './lib/stores/auth.svelte.ts?raw';

/**
 * High contrast and the dyslexia font are applied from the settings store, and
 * `/api/settings` is owner-only. Without a public route for them, a visitor who
 * needs high contrast on a shared instance cannot have it, and the owner has no
 * way to give it to them.
 */
describe('accessibility choices reaching a public visitor', () => {
    it('falls back to the public status payload when settings are unreadable', () => {
        expect(appSource).toContain(
            'settingsStore.settings?.accessibility_high_contrast ?? authStore.highContrast'
        );
        expect(appSource).toContain(
            'settingsStore.settings?.accessibility_dyslexia_font ?? authStore.dyslexiaFont'
        );
    });

    it('reads both from auth status, which a guest can load', () => {
        expect(authStoreSource).toContain('this.highContrast = status.accessibility_high_contrast ?? false');
        expect(authStoreSource).toContain('this.dyslexiaFont = status.accessibility_dyslexia_font ?? false');
    });

    it('derives the values rather than syncing state in an effect', () => {
        // The effect is for the DOM, which is outside Svelte. Working out what
        // should be applied is not (CLAUDE.md section 4).
        expect(appSource).toMatch(/const highContrast = \$derived\(/);
        expect(appSource).toMatch(/const dyslexiaFont = \$derived\(/);
    });

    it('defaults both off, since either changes the whole interface', () => {
        expect(authStoreSource).toContain('highContrast = $state(false);');
        expect(authStoreSource).toContain('dyslexiaFont = $state(false);');
    });
});
