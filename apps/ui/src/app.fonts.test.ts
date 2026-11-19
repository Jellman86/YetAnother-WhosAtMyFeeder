import { describe, expect, it } from 'vitest';
// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';

/**
 * The web fonts the app asks Google Fonts for. Classic (Source Serif 4) is the default text face, and
 * scientific names are set in italic at regular, semibold and bold. Without the italic files the
 * browser slants the upright letters itself, which reads as a crooked roman rather than an italic.
 */
const appCss: string = readFileSync(new URL('./app.css', import.meta.url), 'utf8');
const fontsUrl = appCss.match(/@import url\('(https:\/\/fonts\.googleapis\.com\/css2\?[^']+)'\);/)?.[1] ?? '';

function familyAxes(family: string): string | null {
    const query = new URL(fontsUrl).searchParams.getAll('family');
    return query.find((entry) => entry.startsWith(`${family}:`))?.slice(family.length + 1) ?? null;
}

describe('the Google Fonts request', () => {
    it('is the first rule in the stylesheet', () => {
        expect(fontsUrl).not.toBe('');
        expect(appCss.trimStart().startsWith(`@import url('${fontsUrl}')`)).toBe(true);
    });

    it('loads the real Source Serif 4 italic for every weight the app sets in italic, and no more', () => {
        expect(familyAxes('Source Serif 4')).toBe('ital,wght@0,400;0,600;0,700;1,400;1,600;1,700');
    });
});
