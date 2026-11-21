import { describe, expect, it } from 'vitest';
// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';

const appCss = readFileSync(new URL('./app.css', import.meta.url), 'utf8');

/**
 * Every size in the kit is rem, so one root size scales the app. On a large display the page
 * used to stay at laptop size, with the field log and Explorer read at 10-14px across 2560px.
 */
describe('the type scale on large displays', () => {
    const root = appCss.match(/\nhtml \{([^}]*)\}/)?.[1] ?? '';

    it('grows the root size with the window, from the reader’s own size to a cap', () => {
        // A share of the reader's size, never a pixel term, so it doubles with the browser text size.
        expect(root.replace(/\s+/g, '')).toContain('font-size:calc(100%*clamp(1,1+tan(atan2(100vw-1280px,4096px)),1.25)*var(--text-scale,1))');
    });

    it('starts from a percentage, so the browser text-size setting still applies', () => {
        expect(root).not.toMatch(/font-size:\s*\d+px/);
    });

    it('keeps a 44px touch target at the smaller text sizes', () => {
        expect(appCss).toContain('--spacing-11: max(2.75rem, 44px);');
    });

    // What these sizes come to on screen is measured in a browser, at every Appearance size and at
    // twice the browser's text size: browser-tests/type-scale.spec.ts. Here only the written form
    // is held, because a pixel count in it would stop the scale following the reader's settings.
    describe('the floor under the small steps', () => {
        it('is written in rem, part from the browser size and part from the Appearance size', () => {
            expect(appCss).toContain('--text-floor: calc(0.5rem / var(--text-scale, 1) + 1rem / 3);');
            for (const step of ['3xs', '2xs', 'xs', 'sm', 'base']) {
                expect(appCss, step).toMatch(new RegExp(`--text-${step}: max\\([\\d.]+rem, var\\(--text-floor\\)[^;]*\\);`));
            }
            expect(appCss).not.toMatch(/--text-[\w-]+:[^;]*\d+px/);
        });

        it('sets normal text at the base step, which stays above small print', () => {
            expect(appCss).toMatch(/\n  body \{[^}]*font-size: var\(--text-base\);/);
        });
    });
});

describe('figures', () => {
    it('are lining and tabular in the base styles, so no face sets "08:00" as "o8:oo"', () => {
        const base = appCss.slice(appCss.indexOf('@layer base {'), appCss.indexOf('/* Ensure Tailwind font utilities'));
        expect(base).toMatch(/font-variant-numeric:\s*lining-nums tabular-nums;/);
        // Tailwind's numeric utilities rebuild font-variant-numeric from per-element variables that
        // do not inherit, so the defaults are set on every element, not only inherited from the root.
        expect(base).toMatch(/\*,\s*::before,\s*::after\s*\{[^}]*--tw-numeric-figure:\s*lining-nums;[^}]*--tw-numeric-spacing:\s*tabular-nums;/);
    });
});
