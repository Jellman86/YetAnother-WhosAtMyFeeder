import { describe, expect, it } from 'vitest';
// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';

const appCss: string = readFileSync(new URL('./app.css', import.meta.url), 'utf8');

/**
 * A selector written `.high-contrast text-slate-500` matches an element named `text-slate-500`,
 * which never exists, so the most common secondary text stayed grey on black in high contrast.
 */
describe('the high contrast theme', () => {
    it('never targets a Tailwind utility as if it were an element', () => {
        expect(appCss.match(/\.high-contrast\s+(?:text|bg|border|dark)[-:][^\s,{]*/g) ?? []).toEqual([]);
    });

    it('lifts the quiet slate text colours', () => {
        expect(appCss).toContain('.high-contrast .text-slate-400,');
        expect(appCss).toContain('.high-contrast .text-slate-500,');
    });
});
