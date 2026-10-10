import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const appCss = readFileSync(new URL('./app.css', import.meta.url), 'utf8');

/**
 * Every size in the kit is rem, so one root size scales the app. On a large display the page
 * used to stay at laptop size, with the field log and Explorer read at 10-14px across 2560px.
 */
describe('the type scale on large displays', () => {
    const root = appCss.match(/\nhtml \{([^}]*)\}/)?.[1] ?? '';

    it('grows the root size with the window, from the reader’s own size to a cap', () => {
        expect(root.replace(/\s+/g, '')).toContain('font-size:clamp(100%,calc(100%+(100vw-1536px)/256),118.75%)');
    });

    it('starts from a percentage, so the browser text-size setting still applies', () => {
        expect(root).not.toMatch(/font-size:\s*\d+px/);
    });
});
