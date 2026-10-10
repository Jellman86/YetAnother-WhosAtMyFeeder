import { describe, expect, it } from 'vitest';
// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';

const appCss = readFileSync(new URL('./app.css', import.meta.url), 'utf8');

/**
 * Every size in the kit is rem, so one root size scales the app. On a large display the page
 * used to stay at laptop size, with the field log and Explorer read at 10-14px across 2560px.
 * The smallest print is 11px at the default size for the same reason.
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
        const config = readFileSync(new URL('../tailwind.config.js', import.meta.url), 'utf8');
        expect(config).toContain("spacing: { 11: 'max(2.75rem, 44px)' }");
    });

    it('keeps the smallest print at 11px or more at the default size', () => {
        const config = readFileSync(new URL('../tailwind.config.js', import.meta.url), 'utf8');
        expect(config).toContain("'2xs': '0.75rem'");
        expect(config).toContain("'3xs': '0.6875rem'");
    });
});
