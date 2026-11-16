import { describe, expect, it } from 'vitest';
// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';
import selectorSource from './LanguageSelector.svelte?raw';

const appCss: string = readFileSync(new URL('../../app.css', import.meta.url), 'utf8');
const highContrast = appCss.slice(appCss.indexOf('/* High Contrast Mode'), appCss.indexOf('/* Respect user motion preferences'));

/**
 * The chosen language is one item in a menu of choices. It must say so to a screen reader (a
 * checked menu radio, not a plain menu item), show it by a check as well as a fill, and keep that
 * fill in high contrast, whose button rules otherwise paint every item the same black.
 */
describe('the language menu', () => {
    it('marks the chosen language as a checked menu radio', () => {
        expect(selectorSource).toContain('role="menuitemradio"');
        expect(selectorSource).toContain('aria-checked={currentLocaleValue === code}');
        expect(selectorSource).not.toContain('role="menuitem"\n');
    });

    it('shows the choice by a check as well as its fill', () => {
        expect(selectorSource).toMatch(/\{#if currentLocaleValue === code\}\s*<svg[^>]*data-language-check/);
        expect(selectorSource).toContain("? 'bg-accent text-accent-fg'");
    });

    it('keeps the accent fill and its words in high contrast', () => {
        const fillRule = highContrast.slice(highContrast.indexOf('Chosen-state fills'));
        const fill = fillRule.slice(0, fillRule.indexOf('}'));
        expect(fill).toContain('.bg-accent');
        expect(fill).toContain('background-color: var(--hc-fill) !important');
        expect(highContrast).toMatch(/\.bg-accent,[^{]*\) \* \{\s*color: var\(--hc-on-fill\) !important/);
    });
});
