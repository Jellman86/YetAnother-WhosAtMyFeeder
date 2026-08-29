// Node types are intentionally absent from the browser tsconfig (see
// code-quality-no-any.test.ts); this stylesheet audit runs under Vitest's
// Node environment.
// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import appSource from './App.svelte?raw';
import authStoreSource from './lib/stores/auth.svelte.ts?raw';
import settingsPageSource from './lib/pages/Settings.svelte?raw';
import accessibilityEditorSource from './lib/components/settings/AccessibilitySettings.svelte?raw';
import footerSource from './lib/components/Footer.svelte?raw';
import collageSource from './lib/components/TopSpeciesCollage.svelte?raw';

// Vitest stubs CSS imports, so the stylesheet is read straight from disk.
const appCss = readFileSync(new URL('./app.css', import.meta.url), 'utf-8');

/**
 * High contrast, the dyslexia font and reduced motion are applied from the
 * settings store, and `/api/settings` is owner-only. Without a public route for
 * them, a visitor who needs high contrast on a shared instance cannot have it,
 * and the owner has no way to give it to them.
 */
describe('accessibility choices reaching a public visitor', () => {
    it('falls back through preview, saved value, then the public payload', () => {
        expect(appSource).toContain('accessibilityPreview.highContrast ??');
        expect(appSource).toContain('settingsStore.settings?.accessibility_high_contrast ??');
        expect(appSource).toContain('authStore.highContrast');
        expect(appSource).toContain('accessibilityPreview.dyslexiaFont ??');
        expect(appSource).toContain('accessibilityPreview.reducedMotion ??');
    });

    it('gives the document root exactly one owner', () => {
        // The Settings editor previously toggled the same classes from its
        // unsaved props with no teardown, so an abandoned preview stuck to
        // the whole app until a reload. The editor now publishes a preview
        // value, only on a change, and clears it on unmount; App alone
        // touches the DOM.
        expect(accessibilityEditorSource).not.toContain('documentElement');
        expect(accessibilityEditorSource).toContain('accessibilityPreview.clear()');
    });

    it('backs the reduced-motion class with stylesheet rules', () => {
        // The class had no CSS at all: a control labelled as disabling
        // animations changed one sparkline. The class now mirrors the
        // prefers-reduced-motion media block, since the in-app setting must
        // work for a reader whose OS preference it cannot see.
        expect(appCss).toContain('.reduced-motion *');
        expect(appCss).toContain('.reduced-motion .animate-ping');
    });

    it('reaches the scripts that gate their own motion', () => {
        expect(footerSource).toContain("classList.contains('reduced-motion')");
        expect(collageSource).toContain("classList.contains('reduced-motion')");
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
