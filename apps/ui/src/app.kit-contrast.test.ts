import { describe, expect, it } from 'vitest';
// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';
import { contrastRatio, flatten, type Rgb } from './lib/utils/contrast';

const appCss = readFileSync(new URL('./app.css', import.meta.url), 'utf8');

/** The declarations of every block whose selector is exactly `selector`, later blocks winning. */
function declarations(selector: string): Map<string, string> {
    const found = new Map<string, string>();
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/,\s*/g, ',\\s*');
    for (const block of appCss.matchAll(new RegExp(`(?:^|\\n)${escaped} \\{([^}]*)\\}`, 'g'))) {
        for (const declaration of block[1].matchAll(/(--[\w-]+):\s*([^;]+);/g)) found.set(declaration[1], declaration[2].trim());
    }
    return found;
}

const ROOT = declarations(':root');
const DARK = declarations("html.dark, html[data-theme='dark']");
const BLUETIT = declarations('html.theme-bluetit');
const BLUETIT_LIGHT = declarations('html.theme-bluetit:not(.dark)');
const BLUETIT_DARK = declarations('html.theme-bluetit.dark');
const HIGH_CONTRAST = declarations('html.high-contrast.high-contrast.high-contrast');

/** Each mode and colour theme a reader can be in, as the cascade resolves it. */
const THEMES: Record<string, Map<string, string>> = {
    'classic light': new Map([...ROOT]),
    'classic dark': new Map([...ROOT, ...DARK]),
    'bluetit light': new Map([...ROOT, ...BLUETIT, ...BLUETIT_LIGHT]),
    'bluetit dark': new Map([...ROOT, ...DARK, ...BLUETIT, ...BLUETIT_DARK]),
    'high contrast': new Map([...ROOT, ...DARK, ...BLUETIT, ...BLUETIT_DARK, ...HIGH_CONTRAST])
};

const PALETTE = new Map<string, string>();
for (const colour of appCss.matchAll(/--color-((?:slate|red|amber)-\d+):\s*(#[0-9a-f]{6});/g)) PALETTE.set(colour[1], colour[2]);

function parse(value: string): Rgb {
    const hex = value.match(/^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i);
    if (hex) return [parseInt(hex[1], 16), parseInt(hex[2], 16), parseInt(hex[3], 16)];
    const triplet = value.match(/^(\d+) (\d+) (\d+)$/);
    if (triplet) return [Number(triplet[1]), Number(triplet[2]), Number(triplet[3])];
    throw new Error(`Not a colour: ${value}`);
}

function token(theme: Map<string, string>, name: string): Rgb {
    let value = theme.get(name);
    for (let depth = 0; value?.startsWith('var(') && depth < 4; depth += 1) value = theme.get(value.slice(4, -1));
    if (!value) throw new Error(`No value for ${name}`);
    return parse(value);
}

const slate = (step: number): Rgb => parse(PALETTE.get(`slate-${step}`) ?? '');

function utility(name: string): string {
    const start = appCss.indexOf(`@utility ${name} {`);
    if (start < 0) throw new Error(`No @utility ${name}`);
    return appCss.slice(start, appCss.indexOf('\n}', start));
}

/** The grounds a control sits on, and so the colours a focus ring or a control's edge is seen against. */
const grounds = (theme: Map<string, string>): Record<string, Rgb> => ({
    page: token(theme, '--app-bg'),
    panel: token(theme, '--surface'),
    well: token(theme, '--surface-raised')
});

describe('the kit focus ring', () => {
    it('is one opaque colour per mode, never a translucent brand tint', () => {
        for (const name of ['focus-ring', 'input-base']) {
            const source = utility(name);
            expect(source, name).toMatch(/ring-focus\b(?!\/)/);
            expect(source, name).not.toMatch(/ring-(?:brand|accent)-\d+/);
        }
        expect(utility('focus-ring')).toContain('focus-visible:ring-2');
        expect(utility('focus-ring')).toContain('focus-visible:ring-offset-surface');
        expect(utility('input-base')).toMatch(/focus:border-focus\b(?!\/)/);
    });

    for (const [themeName, theme] of Object.entries(THEMES)) {
        it(`meets 3:1 against the page, a panel and a well in ${themeName}`, () => {
            const ring = token(theme, '--focus');
            for (const [groundName, ground] of Object.entries(grounds(theme))) {
                expect(contrastRatio(ring, ground), `${themeName} ring on ${groundName}`).toBeGreaterThanOrEqual(3);
            }
        });

        it(`meets 3:1 on fixed dark media in ${themeName}`, () => {
            const ring = token(theme, '--focus-on-dark');
            for (const ground of [parse('#000000'), slate(950), slate(900)]) {
                expect(contrastRatio(ring, ground), `${themeName} ring on dark media`).toBeGreaterThanOrEqual(3);
            }
        });
    }
});

describe('the kit text colours', () => {
    const MUTED_LIGHT = slate(600);
    const MUTED_DARK = slate(400);

    it('names its muted text slate-600 on light and slate-400 on dark', () => {
        for (const name of ['eyebrow', 'taxon-rank']) {
            expect(utility(name), name).toContain('text-slate-600');
            expect(utility(name), name).toContain('dark:text-slate-400');
        }
    });

    for (const [themeName, theme] of Object.entries(THEMES)) {
        if (themeName === 'high contrast') continue;
        it(`keeps muted text at 4.5:1 on the page, a panel and a well in ${themeName}`, () => {
            const ink = themeName.endsWith('dark') ? MUTED_DARK : MUTED_LIGHT;
            for (const [groundName, ground] of Object.entries(grounds(theme))) {
                expect(contrastRatio(ink, ground), `${themeName} muted text on ${groundName}`).toBeGreaterThanOrEqual(4.5);
            }
        });

        it(`keeps a placeholder at 4.5:1 inside a field in ${themeName}`, () => {
            const ink = themeName.endsWith('dark') ? slate(400) : slate(500);
            expect(contrastRatio(ink, token(theme, '--surface'))).toBeGreaterThanOrEqual(4.5);
        });

        it(`keeps the button labels at 4.5:1 in ${themeName}`, () => {
            const dark = themeName.endsWith('dark');
            const white: Rgb = [255, 255, 255];
            expect(contrastRatio(white, token(theme, '--brand-700')), 'primary').toBeGreaterThanOrEqual(4.5);
            expect(contrastRatio(white, parse(PALETTE.get('red-700') ?? '')), 'danger solid').toBeGreaterThanOrEqual(4.5);
            const secondaryInk = dark ? slate(200) : slate(700);
            const ghostInk = dark ? slate(300) : slate(600);
            for (const ground of Object.values(grounds(theme))) {
                expect(contrastRatio(secondaryInk, ground), 'secondary').toBeGreaterThanOrEqual(4.5);
                expect(contrastRatio(ghostInk, ground), 'ghost').toBeGreaterThanOrEqual(4.5);
            }
        });
    }
});

describe('the kit switch', () => {
    for (const [themeName, theme] of Object.entries(THEMES)) {
        it(`draws its off track at 3:1 against the page, a panel and a well in ${themeName}`, () => {
            const track = token(theme, '--switch-off');
            for (const [groundName, ground] of Object.entries(grounds(theme))) {
                expect(contrastRatio(track, ground), `${themeName} off track on ${groundName}`).toBeGreaterThanOrEqual(3);
            }
            // The white thumb has to stand out from the track it slides on, too.
            expect(contrastRatio([255, 255, 255], track)).toBeGreaterThanOrEqual(3);
        });

        it(`draws its on track at 3:1 against a panel in ${themeName}`, () => {
            expect(contrastRatio(token(theme, '--switch-on'), token(theme, '--surface'))).toBeGreaterThanOrEqual(3);
        });
    }

    it('shows keyboard focus with the kit ring', () => {
        expect(utility('switch-track')).toContain('focus-ring');
        expect(utility('switch-track')).toContain('bg-switch-off');
        expect(utility('switch-track')).toContain('aria-checked:bg-switch-on');
    });
});

describe('the kit chip over a photograph', () => {
    it('is opaque enough that white text passes on a white frame', () => {
        const source = utility('photo-chip');
        const fill = source.match(/bg-black\/(\d+)/);
        expect(fill, 'photo-chip names a black fill').not.toBeNull();
        const onWhite = flatten([0, 0, 0], Number(fill?.[1]) / 100, [255, 255, 255]);
        expect(contrastRatio([255, 255, 255], onWhite)).toBeGreaterThanOrEqual(4.5);
        expect(source).not.toContain('backdrop-blur');
    });
});

describe('the kit sizes', () => {
    it('never sets readable text below 12px, whatever text size the reader picks', () => {
        for (const size of ['3xs', '2xs', 'xs', 'sm']) {
            expect(appCss, size).toMatch(new RegExp(`--text-${size}: max\\([\\d.]+rem, 12px\\);`));
        }
    });

    it('gives every button a comfortable target and its own padding', () => {
        const button = utility('btn');
        expect(button).toContain('min-h-11');
        expect(button).toContain('px-4');
        expect(button).toContain('py-2');
    });
});
