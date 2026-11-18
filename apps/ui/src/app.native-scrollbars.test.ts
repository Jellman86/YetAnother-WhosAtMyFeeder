import { describe, expect, it } from 'vitest';
// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';

const appCss = readFileSync(new URL('./app.css', import.meta.url), 'utf8');
const appRules = appCss.replace(/\/\*[\s\S]*?\*\//g, '');

/** How the app treats scrollbars and short windows on a Mac (the Mac polish pass, NIGGLE 1). */
describe('the app keeps the platform scrollbars and a steady page', () => {
    it('does not style scrollbars, which would turn off macOS overlay scrollbars', () => {
        // Any ::-webkit-scrollbar rule makes Safari and Chrome on a Mac draw a permanent bar in every
        // scrolling area. The native bar already follows the mode through `color-scheme`.
        expect(appRules).not.toContain('::-webkit-scrollbar');
        expect(appCss).toMatch(/color-scheme: dark;/);
    });

    it('names its two scrollbar utilities with the standard properties, which keep overlay scrollbars', () => {
        // `scrollbar-thin` and `scrollbar-none` were used without a definition, so they did nothing.
        expect(appCss).toMatch(/@utility scrollbar-thin \{\s*scrollbar-width: thin;\s*\}/);
        expect(appCss).toMatch(/@utility scrollbar-none \{\s*scrollbar-width: none;\s*\}/);
    });
});
