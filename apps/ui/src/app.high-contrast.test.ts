import { describe, expect, it } from 'vitest';
// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';
import { contrastRatio, type Rgb } from './lib/utils/contrast';
import themeStoreSource from './lib/stores/theme.svelte.ts?raw';
import appSource from './App.svelte?raw';
import sidebarSource from './lib/components/Sidebar.svelte?raw';

const appCss: string = readFileSync(new URL('./app.css', import.meta.url), 'utf8');

const sources = import.meta.glob(['./**/*.svelte', './**/*.ts', '!./**/*.test.ts'], {
    eager: true,
    query: '?raw',
    import: 'default'
}) as Record<string, string>;

const highContrast = appCss.slice(appCss.indexOf('/* High Contrast Mode'), appCss.indexOf('/* Respect user motion preferences'));

function hex(value: string): Rgb {
    const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(value.trim());
    if (!match) throw new Error(`Not a colour: ${value}`);
    return [parseInt(match[1], 16), parseInt(match[2], 16), parseInt(match[3], 16)];
}

function inkToken(name: string): Rgb {
    const match = new RegExp(`${name}:\\s*(#[0-9a-f]{6});`, 'i').exec(highContrast);
    if (!match) throw new Error(`High contrast defines no ${name}`);
    return hex(match[1]);
}

/** Every text colour family the app writes, from `text-slate-900` to `dark:hover:text-brand-300`. */
function inkFamilies(): Set<string> {
    const families = new Set<string>();
    for (const source of [...Object.values(sources), appCss]) {
        for (const match of source.matchAll(/(?<![\w-])text-([a-z]+)-\d{2,3}(?![\w-])/g)) families.add(match[1]);
    }
    return families;
}

const BLACK: Rgb = [0, 0, 0];

/**
 * High contrast paints the page black. Turned on over the light theme it left every ink class the
 * old stylesheet had not listed (headings, labels, the unsaved count) near-black on black, and a
 * list of classes can never be complete. The mode is now one scheme: it takes the dark variants
 * whatever theme is chosen, and every text colour family is repainted by family, not by class.
 */
describe('the high contrast theme', () => {
    it('never targets a Tailwind utility as if it were an element', () => {
        expect(appCss.match(/\.high-contrast\s+(?:text|bg|border|dark)[-:][^\s,{]*/g) ?? []).toEqual([]);
    });

    it('is one black scheme that takes the dark variants in the light theme too', () => {
        expect(themeStoreSource).toMatch(/classList\.toggle\('dark', isDark \|\| highContrast\)/);
        expect(themeStoreSource).toContain('setHighContrast(');
        expect(appSource).toContain('themeStore.setHighContrast(highContrast)');
        // The theme switch still shows the reader's own choice, which returns when the mode goes off.
        expect(sidebarSource).toContain('themeStore.prefersDark');
        expect(highContrast).toMatch(/--app-bg:\s*#000000;/);
        expect(highContrast).toMatch(/--app-fg:\s*#ffffff;/);
    });

    it('repaints every text colour family the app uses, so no ink class is left on black', () => {
        const families = inkFamilies();
        expect(families.size).toBeGreaterThan(5);
        const unpainted = [...families].filter((family) => !highContrast.includes(`[class*='text-${family}-']`));
        expect(unpainted).toEqual([]);
    });

    it('draws every ink at 7:1 or better on black, disabled text included', () => {
        for (const name of ['--hc-ink', '--hc-ink-brand', '--hc-ink-success', '--hc-ink-attention', '--hc-ink-danger', '--hc-ink-disabled']) {
            expect(contrastRatio(inkToken(name), BLACK), name).toBeGreaterThanOrEqual(7);
        }
    });

    it('keeps black text on its yellow fills, whatever ink class the words inside carry', () => {
        expect(contrastRatio(inkToken('--hc-fill'), BLACK)).toBeGreaterThanOrEqual(7);
        expect(highContrast).toContain('.btn-primary');
        expect(highContrast).toMatch(/\.bg-brand-700 \*/);
    });

    it('tells a switch that is on from one that is off by its fill, not only by its thumb', () => {
        expect(highContrast).toContain(".switch-track[aria-checked='true']");
    });

    it('holds with the reading font, which changes the face and nothing else', () => {
        const readingFont = appCss.slice(appCss.indexOf('/* Reading font'), appCss.indexOf('/* High Contrast Mode'));
        expect(readingFont).toContain("font-family: 'OpenDyslexic'");
        expect(readingFont).not.toMatch(/(?<!-)color:|background/);
    });
});
