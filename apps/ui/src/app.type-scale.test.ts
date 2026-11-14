import { describe, expect, it } from 'vitest';
// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';

const appCss = readFileSync(new URL('./app.css', import.meta.url), 'utf8');

/**
 * Every size in the kit is rem, so one root size scales the app. On a large display the page
 * used to stay at laptop size, with the field log and Explorer read at 10-14px across 2560px.
 * The smallest print never falls under 12px, at any text size.
 */
describe('the type scale on large displays', () => {
    const root = appCss.match(/\nhtml \{([^}]*)\}/)?.[1] ?? '';

    it('grows the root size with the window, from the reader’s own size to a cap', () => {
        expect(root.replace(/\s+/g, '')).toContain('font-size:calc(clamp(100%,calc(100%+(100vw-1280px)/256),125%)*var(--text-scale,1))');
    });

    it('starts from a percentage, so the browser text-size setting still applies', () => {
        expect(root).not.toMatch(/font-size:\s*\d+px/);
    });

    it('keeps a 44px touch target at the smaller text sizes', () => {
        expect(appCss).toContain('--spacing-11: max(2.75rem, 44px);');
    });

    it('keeps the smallest print in rem with a 12px floor, so the Standard size never sets it under 12px', () => {
        // Standard puts the root at 14px, where 0.6875rem alone is 9.6px.
        expect(appCss).toContain('--text-3xs: max(0.6875rem, 12px);');
        expect(appCss).toContain('--text-2xs: max(0.75rem, 12px);');
        expect(appCss).toContain('--text-xs: max(0.75rem, 12px);');
        expect(appCss).toContain('--text-sm: max(0.875rem, 12px);');
    });
});
