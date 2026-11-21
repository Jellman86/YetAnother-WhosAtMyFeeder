import { describe, expect, it } from 'vitest';
// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';
import { contrastRatio, type Rgb } from './lib/utils/contrast';

/**
 * Every foreground token against every ground it can sit on, in every mode and colour theme, read
 * from the values app.css actually declares. WCAG 2.2 AA: words 4.5:1, marks and edges 3:1. High
 * contrast holds words to 7:1, the bar that mode exists for.
 */
const appCss: string = readFileSync(new URL('./app.css', import.meta.url), 'utf8');

/** The custom properties of every block whose selector is exactly `selector`, later blocks winning. */
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

/** Each mode a reader can be in, as the cascade resolves it. High contrast always adds `dark`. */
const MODES: Record<string, Map<string, string>> = {
    'classic light': new Map([...ROOT]),
    'classic dark': new Map([...ROOT, ...DARK]),
    'bluetit light': new Map([...ROOT, ...BLUETIT, ...BLUETIT_LIGHT]),
    'bluetit dark': new Map([...ROOT, ...DARK, ...BLUETIT, ...BLUETIT_DARK]),
    'high contrast over classic': new Map([...ROOT, ...DARK, ...HIGH_CONTRAST]),
    'high contrast over bluetit': new Map([...ROOT, ...DARK, ...BLUETIT, ...BLUETIT_DARK, ...HIGH_CONTRAST])
};

function parse(value: string): Rgb {
    const hex = value.match(/^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i);
    if (hex) return [parseInt(hex[1], 16), parseInt(hex[2], 16), parseInt(hex[3], 16)];
    const triplet = value.match(/^(\d+) (\d+) (\d+)$/);
    if (triplet) return [Number(triplet[1]), Number(triplet[2]), Number(triplet[3])];
    throw new Error(`Not a colour: ${value}`);
}

function token(mode: Map<string, string>, name: string): Rgb {
    let value = mode.get(name);
    for (let depth = 0; value?.startsWith('var(') && depth < 4; depth += 1) value = mode.get(value.slice(4, -1));
    if (!value) throw new Error(`No value for ${name}`);
    return parse(value);
}

const TONES = ['ok', 'attention', 'fail', 'info', 'neutral'] as const;
const GROUNDS = ['--surface', '--surface-raised', '--surface-sunken', '--app-bg'];
const WORDS = ['--ink-strong', '--ink', '--ink-muted'];

function check(mode: Map<string, string>, highContrast: boolean) {
    const words = highContrast ? 7 : 4.5;
    const failures: string[] = [];
    const pair = (foreground: string, ground: string, minimum: number) => {
        const ratio = contrastRatio(token(mode, foreground), token(mode, ground));
        if (ratio < minimum) failures.push(`${foreground} on ${ground}: ${ratio.toFixed(2)} < ${minimum}`);
    };
    for (const ground of GROUNDS) {
        for (const ink of WORDS) pair(ink, ground, words);
        pair('--ink-subtle', ground, 3);
        pair('--line-strong', ground, 3);
        pair('--focus', ground, 3);
        pair('--accent-ink', ground, words);
        for (const tone of TONES) {
            pair(`--status-${tone}`, ground, words);
            pair(`--status-${tone}-line`, ground, 3);
        }
    }
    for (const tone of TONES) {
        // A chip or a callout: its own ink and the body inks on its soft ground, its edge against it.
        pair(`--status-${tone}`, `--status-${tone}-soft`, words);
        pair(`--status-${tone}-line`, `--status-${tone}-soft`, 3);
        for (const ink of WORDS) pair(ink, `--status-${tone}-soft`, words);
    }
    // A chosen row's recessed key carries strong words and an accent icon.
    pair('--ink-strong', '--accent-soft', words);
    pair('--accent-ink', '--accent-soft', 3);
    pair('--accent-line', '--surface', 3);
    // A meter (a score bar, a level): its fill against its track, so the extent reads (UI 3:1).
    for (const tone of TONES) pair(`--status-${tone}-line`, '--track', 3);
    pair('--accent-line', '--track', 3);
    // Filled controls: their words on their fill, at rest and on hover.
    pair('--accent-fg', '--accent', words);
    pair('--accent-fg', '--accent-hover', words);
    pair('--danger-fg', '--danger', words);
    pair('--danger-fg', '--danger-hover', words);
    pair('--on-media', '--media', 7);
    pair('--on-media', '--media-raised', 7);
    pair('--brand-400', '--media', 4.5);
    pair('--brand-400', '--media-raised', 4.5);
    pair('--on-media-fail', '--media', words);
    pair('--on-media-fail', '--media-raised', words);
    return failures;
}

describe('the semantic tokens', () => {
    it('are resolved in every mode, with no token left to a theme it was not written for', () => {
        const names = [...appCss.matchAll(/--color-([\w-]+): rgb\(var\((--[\w-]+)\)\);/g)].map((match) => match[2]);
        expect(names.length).toBeGreaterThan(30);
        for (const [modeName, mode] of Object.entries(MODES)) {
            for (const name of names) expect(() => token(mode, name), `${modeName} ${name}`).not.toThrow();
        }
    });

    for (const [modeName, mode] of Object.entries(MODES)) {
        it(`meet WCAG 2.2 AA for every foreground and ground they pair in ${modeName}`, () => {
            expect(check(mode, modeName.startsWith('high contrast'))).toEqual([]);
        });
    }

    it('keep amber for work that needs a person and green for healthy, in every colour theme', () => {
        for (const mode of Object.values(MODES)) {
            const [r, g, b] = token(mode, '--status-attention');
            expect(r, 'attention is warm').toBeGreaterThan(b);
            const [okR, okG] = token(mode, '--status-ok');
            expect(okG, 'ok is green').toBeGreaterThan(okR);
        }
        // A colour theme repaints the brand, never a status tone.
        for (const block of [BLUETIT, BLUETIT_LIGHT, BLUETIT_DARK]) {
            expect([...block.keys()].filter((name) => /^--status-(?:ok|attention|fail|neutral)/.test(name))).toEqual([]);
        }
    });

    it('are what the kit controls paint with', () => {
        const utility = (name: string) => appCss.slice(appCss.indexOf(`@utility ${name} {`), appCss.indexOf('\n}', appCss.indexOf(`@utility ${name} {`)));
        expect(utility('btn-primary')).toContain('bg-accent text-accent-fg');
        expect(utility('btn-secondary')).toContain('text-ink');
        expect(utility('btn-ghost')).toContain('text-muted');
        expect(utility('btn-danger')).toContain('text-status-fail');
        expect(utility('btn-danger-solid')).toContain('bg-danger text-danger-fg');
        expect(utility('input-base')).toContain('text-strong placeholder:text-muted');
        expect(utility('eyebrow')).toContain('text-muted');
        for (const name of ['btn-primary', 'btn-secondary', 'btn-ghost', 'btn-danger', 'btn-danger-solid', 'input-base', 'eyebrow', 'tab-button-active', 'tab-button-inactive', 'sidebar-nav-active', 'sidebar-nav-inactive', 'choice-active', 'choice-option', 'choice-option-selected', 'photo-chip']) {
            expect(utility(name), name).not.toMatch(/(?:^|\s)(?:[\w-]+:)*[a-z]+-(?:slate|gray|red|rose|brand|white|black)(?:-\d{2,3})?(?:\/\d+)?(?=\s|;)/);
            expect(utility(name), name).not.toContain('dark:');
        }
    });
});

/** A colour's place in OKLab, scaled by 100: the space the chart palette is validated in. */
function oklab([r, g, b]: Rgb): [number, number, number] {
    const linear = [r, g, b].map((channel) => {
        const value = channel / 255;
        return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
    });
    const l = Math.cbrt(0.4122214708 * linear[0] + 0.5363325363 * linear[1] + 0.0514459929 * linear[2]);
    const m = Math.cbrt(0.2119034982 * linear[0] + 0.6806995451 * linear[1] + 0.1073969566 * linear[2]);
    const s = Math.cbrt(0.0883024619 * linear[0] + 0.2817188376 * linear[1] + 0.6299787005 * linear[2]);
    return [
        100 * (0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s),
        100 * (1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s),
        100 * (0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s)
    ];
}

function difference(a: Rgb, b: Rgb): number {
    const [first, second] = [oklab(a), oklab(b)];
    return Math.hypot(first[0] - second[0], first[1] - second[1], first[2] - second[2]);
}

const SERIES = ['--series-1', '--series-2', '--series-3', '--series-4'];
/** Colours a line must not be mistaken for: the brand, the keyboard focus, and every status tone. */
const RESERVED = ['--accent', '--accent-ink', '--accent-line', '--focus', ...TONES.flatMap((tone) => [`--status-${tone}`, `--status-${tone}-line`])];

describe('the chart series colours', () => {
    for (const [modeName, mode] of Object.entries(MODES)) {
        it(`are four colours apart from each other, the accent and every status tone in ${modeName}`, () => {
            const failures: string[] = [];
            SERIES.forEach((name, index) => {
                // 15 is the normal-vision floor the palette was validated to; a status tone keeps 10.
                for (const other of SERIES.slice(index + 1)) {
                    const apart = difference(token(mode, name), token(mode, other));
                    if (apart < 15) failures.push(`${name} and ${other}: ${apart.toFixed(1)} apart`);
                }
                for (const reserved of RESERVED) {
                    const apart = difference(token(mode, name), token(mode, reserved));
                    if (apart < 10) failures.push(`${name} near ${reserved}: ${apart.toFixed(1)} apart`);
                }
                // Every line is drawn on the chart's panel.
                const ratio = contrastRatio(token(mode, name), token(mode, '--surface'));
                if (ratio < 3) failures.push(`${name} on --surface: ${ratio.toFixed(2)} < 3`);
            });
            // The sidebar's meters fill with the CPU's and the first accelerator's colours, on the
            // status card's raised ground and against the meter's track.
            for (const name of SERIES.slice(0, 2)) {
                for (const ground of ['--surface-raised', '--track']) {
                    const ratio = contrastRatio(token(mode, name), token(mode, ground));
                    if (ratio < 3) failures.push(`${name} on ${ground}: ${ratio.toFixed(2)} < 3`);
                }
            }
            expect(failures).toEqual([]);
        });
    }

    it('are fixed, so a colour theme never repaints a line', () => {
        for (const block of [BLUETIT, BLUETIT_LIGHT, BLUETIT_DARK]) {
            expect([...block.keys()].filter((name) => name.startsWith('--series-'))).toEqual([]);
        }
    });
});
