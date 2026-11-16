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
    // Filled controls: their words on their fill, at rest and on hover.
    pair('--accent-fg', '--accent', words);
    pair('--accent-fg', '--accent-hover', words);
    pair('--danger-fg', '--danger', words);
    pair('--danger-fg', '--danger-hover', words);
    pair('--on-media', '--media', 7);
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
