import { describe, expect, it } from 'vitest';
// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';
import { contrastRatio, flatten, type Rgb } from './lib/utils/contrast';
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

/** Every quoted string and `@apply` list in the app: where a set of classes for one element is written. */
function classStrings(): string[] {
    const found: string[] = [];
    for (const source of [...Object.values(sources), appCss]) {
        for (const match of source.matchAll(/(["'`])((?:(?!\1)[^\n]){1,1500}?)\1/g)) found.push(match[2]);
        for (const match of source.matchAll(/@apply ([^;]+);/g)) found.push(match[1]);
    }
    return found;
}

/** Whether the mode names this fill class in a rule of its own, as `.bg-x` or `[class~='bg-x']`. */
function repaintedByName(fill: string): boolean {
    const escaped = fill.replace(/[:/]/g, '\\$&');
    return highContrast.includes(`[class~='${fill}']`) || new RegExp(`\\.${escaped.replace(/\\/g, '\\\\')}(?![\\w/\\\\-])`).test(highContrast);
}

function declaredIn(selector: string): Map<string, string> {
    const found = new Map<string, string>();
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/,\s*/g, ',\\s*');
    for (const block of appCss.matchAll(new RegExp(`(?:^|\\n)${escaped} \\{([^}]*)\\}`, 'g'))) {
        for (const declaration of block[1].matchAll(/(--[\w-]+):\s*([^;]+);/g)) found.set(declaration[1], declaration[2].trim());
    }
    return found;
}

/** The scales a theme drives, as high contrast resolves them over the dark bluetit theme. */
const MODE_TOKENS = new Map([
    ...declaredIn(':root'),
    ...declaredIn("html.dark, html[data-theme='dark']"),
    ...declaredIn('html.theme-bluetit'),
    ...declaredIn('html.theme-bluetit.dark'),
    ...declaredIn('html.high-contrast.high-contrast.high-contrast')
]);

/** A fill class as it is drawn on the mode's black page, or null when its colour is not known. */
function fillColour(fill: string): Rgb | null {
    const match = /^bg-(?:(white|black)|([a-z]+)-(\d{2,3}))(?:\/(\d+))?$/.exec(fill);
    if (!match) return null;
    let colour: Rgb | null = null;
    if (match[1]) colour = match[1] === 'white' ? [255, 255, 255] : [0, 0, 0];
    else {
        const literal = new RegExp(`--color-${match[2]}-${match[3]}:\\s*(#[0-9a-f]{6});`, 'i').exec(appCss);
        if (literal) colour = hex(literal[1]);
        else {
            let value = MODE_TOKENS.get(`--${match[2]}-${match[3]}`);
            for (let depth = 0; value?.startsWith('var(') && depth < 4; depth += 1) value = MODE_TOKENS.get(value.slice(4, -1));
            const triplet = value?.match(/^(\d+) (\d+) (\d+)$/);
            if (triplet) colour = [Number(triplet[1]), Number(triplet[2]), Number(triplet[3])];
        }
    }
    if (!colour) return null;
    return flatten(colour, match[4] ? Number(match[4]) / 100 : 1, BLACK);
}

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
    });

    it('tells a switch that is on from one that is off by its fill, not only by its thumb', () => {
        expect(highContrast).toContain(".switch-track[aria-checked='true']");
    });

    it('gives a disabled control its ground with its ink, after the fills, so a disabled primary button is never grey on yellow', () => {
        const disabled = highContrast.indexOf(':is(button, input, select, textarea):disabled');
        const block = highContrast.slice(disabled, highContrast.indexOf('}', disabled));
        expect(block).toContain('color: var(--hc-ink-disabled) !important');
        expect(block).toContain('background-color: #000000 !important');
        // Later in the sheet and one element heavier than any fill rule, so it wins on both.
        expect(disabled).toBeGreaterThan(highContrast.lastIndexOf('background-color: var(--hc-fill)'));
        expect(highContrast).toMatch(/:disabled \*,[\s\S]{0,80}\[aria-disabled='true'\] \* \{\s*color: var\(--hc-ink-disabled\) !important/);
    });

    it('repaints what sits inside a filled element, so a white or tinted word in a badge follows its fill', () => {
        for (const ink of ['--hc-on-fill', '--hc-on-dark-fill']) {
            expect(highContrast, ink).toMatch(new RegExp(`\\) \\* \\{\\s*color: var\\(${ink}\\) !important`));
        }
        expect(contrastRatio(inkToken('--hc-on-dark-fill'), inkToken('--hc-dark-fill'))).toBeGreaterThanOrEqual(7);
    });

    it('holds every fill the app sets white words on: dark enough for them, or repainted by name', () => {
        const unheld = new Set<string>();
        for (const classes of classStrings()) {
            if (!/(?<![\w:-])text-white(?![\w/-])/.test(classes)) continue;
            const fills = [...classes.matchAll(/(?<![\w/-])((?:dark:)?bg-(?:[a-z]+-\d{2,3}|white|black)(?:\/\d+)?)(?![\w-])/g)].map((match) => match[1]);
            // The mode takes the dark variants, so a dark fill replaces the light one beside it.
            const dark = fills.filter((fill) => fill.startsWith('dark:'));
            for (const fill of dark.length > 0 ? dark : fills) {
                if (repaintedByName(fill)) continue;
                const drawn = fillColour(fill.replace(/^dark:/, ''));
                if (!drawn || contrastRatio([255, 255, 255], drawn) < 7) unheld.add(fill);
            }
        }
        expect([...unheld].sort()).toEqual([]);
    });

    it('leaves no ink written as a colour inside a component, where the mode cannot reach it', () => {
        // A scoped `color: rgb(...)` outranks nothing here and is repainted by nothing: the AI
        // panel's role label sat under 7:1. Component inks are tokens the themes and this mode set.
        const literalInks: string[] = [];
        const tokens = new Set<string>();
        for (const [file, source] of Object.entries(sources)) {
            if (!file.endsWith('.svelte') || !source.includes('<style')) continue;
            const style = source.slice(source.lastIndexOf('<style'));
            for (const match of style.matchAll(/(?<![-\w])color:\s*([^;]+);/g)) {
                if (/#[0-9a-f]{3,8}\b|rgba?\(\s*\d/i.test(match[1])) literalInks.push(`${file}: color: ${match[1]}`);
                for (const token of match[1].matchAll(/var\((--[\w-]+)/g)) tokens.add(token[1]);
            }
        }
        expect(literalInks).toEqual([]);
        expect(tokens.size).toBeGreaterThan(0);
        const tokenBlock = highContrast.slice(highContrast.indexOf('html.high-contrast.high-contrast.high-contrast'));
        expect([...tokens].filter((token) => !tokenBlock.includes(`${token}:`))).toEqual([]);
    });

    it('holds with the reading font, which changes the face and nothing else', () => {
        const readingFont = appCss.slice(appCss.indexOf('/* Reading font'), appCss.indexOf('/* High Contrast Mode'));
        expect(readingFont).toContain("font-family: 'OpenDyslexic'");
        expect(readingFont).not.toMatch(/(?<!-)color:|background/);
    });
});
