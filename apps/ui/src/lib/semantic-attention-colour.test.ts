import { describe, expect, it } from 'vitest';
// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';
import tailwindConfigSource from '../../tailwind.config.js?raw';

const appCss = readFileSync(new URL('../app.css', import.meta.url), 'utf8');

/**
 * `layout-patterns.md` §1.3: "Amber is reserved for 'this needs a person'." The
 * theme accent cannot carry that meaning, because it is a brand colour: the
 * classic theme paints it emerald, so work waiting on a person read as healthy.
 * Attention is a semantic scale of its own, amber in every theme (DB-02).
 */
describe('attention is a semantic colour, not the brand accent', () => {
    const shades = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950];

    it('exposes attention as its own colour scale', () => {
        expect(tailwindConfigSource).toContain('attention: {');
        for (const shade of shades) {
            expect(tailwindConfigSource).toContain(`${shade}: 'rgb(var(--attention-${shade}) / <alpha-value>)'`);
        }
    });

    it('defines the scale once, as amber, in the root block', () => {
        const amber500 = appCss.match(/--attention-500:\s*([\d ]+);/);
        expect(amber500?.[1].trim()).toBe('245 158 11');
        const definitions = appCss.match(/--attention-500:/g) ?? [];
        expect(definitions).toHaveLength(1);
    });

    it('is never repainted by a colour theme', () => {
        const themeBlocks = appCss.match(/html\.theme-[\w-]+[^{]*\{[^}]*\}/g) ?? [];
        expect(themeBlocks.length).toBeGreaterThan(0);
        for (const block of themeBlocks) expect(block).not.toContain('--attention-');
    });
});
