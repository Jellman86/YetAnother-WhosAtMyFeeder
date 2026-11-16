// @ts-nocheck: this source audit runs under Vitest's Node environment; Node types are
// intentionally absent from the browser application tsconfig.
/**
 * The design-token ratchet. Colour comes from the semantic tokens in app.css (`bg-surface`,
 * `text-muted`, `border-status-fail`), resolved once for light, dark and high contrast, so a
 * screen needs no colour of its own. Three things bypass them, and this audit counts each one
 * per file:
 *
 * - `palette`: a raw palette step (`text-amber-600`, `bg-slate-100`, `bg-brand-700`,
 *   `text-white`), which keeps its colour whatever mode the reader is in;
 * - `dark`: a `dark:` colour override, which is a second colour chosen by hand for one mode;
 * - `arbitrary`: an arbitrary value (`text-[10px]`, `grid-cols-[9rem_1fr]`), outside the scale.
 *
 * The counts may only fall. A file whose count rises fails, as does a file not in the baseline
 * that adds any. A file whose count falls fails too, until the baseline is lowered with it in the
 * same change, so the ratchet never loosens again behind a migration:
 *
 *   npm run tokens:baseline
 *
 * The few places that need a literal colour are in ALLOWLIST below, each with its reason; those
 * classes are not counted.
 */
import { readdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { extname, join, relative } from 'node:path';
import postcss from 'postcss';
import { describe, expect, it } from 'vitest';
import { lowerBaseline, raisedCounts } from '../scripts/token-baseline.mjs';

type Counts = { palette: number; dark: number; arbitrary: number };
type Baseline = Record<string, Counts>;

const SOURCE_ROOT = join(process.cwd(), 'src');
const BASELINE_PATH = join(SOURCE_ROOT, 'design-tokens.baseline.json');
// Authored stylesheets too: an `@apply` is as much a class as one written in markup.
const SOURCE_EXTENSIONS = new Set(['.ts', '.svelte', '.css']);
// The generated API types carry no classes; the tests quote retired classes on purpose.
const EXCLUDED_PATH_PARTS = ['/generated/', '.test.ts', '/i18n/locales/'];

const FAMILIES = [
    'slate', 'gray', 'zinc', 'neutral', 'stone', 'red', 'orange', 'amber', 'yellow', 'lime', 'green',
    'emerald', 'teal', 'cyan', 'sky', 'blue', 'indigo', 'violet', 'purple', 'fuchsia', 'pink', 'rose',
    // The step scales behind the tokens: a step is a colour, not a meaning.
    'brand', 'success', 'attention'
].join('|');

/** A palette step or a bare white/black, with any variants and opacity: `dark:hover:bg-slate-800/50`. */
const PALETTE = new RegExp(
    `(?<![\\w-])(?:[\\w-]+:)*-?[a-z]+(?:-[a-z]+)*-(?:(?:${FAMILIES})-\\d{2,3}|white|black)(?:\\/\\d+)?(?![\\w-])`,
    'g'
);

/** The colour utilities a `dark:` variant can set. Sizes, alignment and other values are not colours. */
const DARK_COLOUR = new RegExp(
    '(?<![\\w-])dark:(?:[\\w-]+:)*(?:bg|text|border(?:-[xytrbles])?|ring(?:-offset)?|divide|fill|stroke|from|via|to|outline|decoration|placeholder|shadow|caret|accent)' +
        '-(?!(?:\\d|xs|sm|md|lg|xl|2xl|3xl|2xs|3xs|base|left|right|center|justify|start|end|none|inset|hidden|solid|dashed|dotted|double|clip|wrap|nowrap|balance|pretty|ellipsis|transparent|inherit|current)(?![\\w-]))[a-z][\\w/.-]*',
    'g'
);

/** An arbitrary value (`w-[3px]`, `text-[10px]`) or an arbitrary property (`[mask:none]`). */
const ARBITRARY = /(?<![\w\]-])(?:[\w-]+:)*(?:-?[a-z][\w-]*-\[[^\]\s'"`]+\]|\[[a-z-]+:[^\]\s'"`]+\])/g;

/**
 * Literal colours that are the point, not a bypass. Each entry names a file, the classes it may
 * keep and why. Add to this list only with a reason a reviewer accepts.
 */
const ALLOWLIST: { file: string; classes: RegExp; reason: string }[] = [
    {
        file: 'lib/components/settings/AppearanceSettings.svelte',
        classes: /^(?:bg|border|ring)-(?:blue|amber|teal|emerald)-\d{2,3}$/,
        reason: "the colour-theme picker shows each theme's own two colours, whatever theme is on"
    },
    {
        file: 'lib/components/settings/SystemHealthPanel.svelte',
        classes: /^(?:bg|text|fill|stroke)-(?:amber|blue|teal|violet|rose)-\d{2,3}$/,
        reason: 'categorical CPU-share and load series, chosen for colour-vision separation and always named in words; a series is not a state'
    },
    {
        file: 'lib/utils/system-history.ts',
        classes: /^(?:text|stroke)-(?:blue|teal|violet|amber|rose)-\d{2,3}$/,
        reason: 'the same categorical load series, drawn on the Health chart and named in its key'
    }
];

function sourceFiles(directory: string): string[] {
    return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
        const path = join(directory, entry.name);
        if (entry.isDirectory()) return sourceFiles(path);
        if (!SOURCE_EXTENSIONS.has(extname(entry.name))) return [];
        const normalised = path.replaceAll('\\', '/');
        return EXCLUDED_PATH_PARTS.some((part) => normalised.includes(part)) ? [] : [path];
    });
}

/** The class without its variants and opacity, as an allowlist entry names it. */
function bareClass(found: string): string {
    return found.replace(/^(?:[\w-]+:)*/, '').replace(/\/\d+$/, '');
}

/**
 * The one place in a stylesheet whose selectors are not counted. High contrast repaints the older
 * palette classes by name (`& .bg-white`, `& [class~='bg-attention-300']`) so that screens not yet
 * on the tokens stay readable; those rules paint only inside the mode, and they shrink as the
 * migration proceeds. They live nested in a single top-level rule whose selector is the mode's
 * root. The exemption is structural: postcss parses the sheet, and only rules whose ancestors
 * include that rule lose their selectors. Every other rule, at the top level or not, counts, and
 * declarations (an @apply included) count everywhere.
 */
const STYLESHEET_SCOPES: Record<string, { selector: string; reason: string }> = {
    'app.css': {
        selector: '.high-contrast',
        reason: 'the high-contrast repaint rules name legacy classes to override them inside the mode; they paint nothing outside it'
    }
};

function stylesheetText(source: string, file: string): string {
    const root = postcss.parse(source);
    // Comments are words, not rules.
    root.walkComments((comment) => {
        comment.remove();
    });
    const scope = STYLESHEET_SCOPES[file];
    if (scope) {
        const scopes = root.nodes.filter((node) => node.type === 'rule' && node.selector.trim() === scope.selector);
        if (scopes.length > 1) throw new Error(`${file}: only one top-level ${scope.selector} rule may hold the high-contrast repaints`);
        for (const rule of scopes) {
            rule.walkRules((inner) => {
                inner.selector = '';
            });
        }
    }
    return root.toString();
}

function countBypasses(raw: string, file = ''): Counts {
    const source = file.endsWith('.css') ? stylesheetText(raw, file) : raw;
    const allowed = ALLOWLIST.filter((entry) => entry.file === file);
    const keep = (found: string) => !allowed.some((entry) => entry.classes.test(bareClass(found)));
    return {
        palette: [...source.matchAll(PALETTE)].map((match) => match[0]).filter(keep).length,
        dark: [...source.matchAll(DARK_COLOUR)].map((match) => match[0]).filter(keep).length,
        arbitrary: [...source.matchAll(ARBITRARY)].length
    };
}

function measure(): Baseline {
    const counts: Baseline = {};
    for (const path of sourceFiles(SOURCE_ROOT).sort()) {
        const file = relative(SOURCE_ROOT, path).replaceAll('\\', '/');
        const found = countBypasses(readFileSync(path, 'utf8'), file);
        if (found.palette + found.dark + found.arbitrary > 0) counts[file] = found;
    }
    return counts;
}

function totals(baseline: Baseline): Counts & { files: number } {
    const sum = { palette: 0, dark: 0, arbitrary: 0, files: 0 };
    for (const counts of Object.values(baseline)) {
        sum.palette += counts.palette;
        sum.dark += counts.dark;
        sum.arbitrary += counts.arbitrary;
        sum.files += 1;
    }
    return sum;
}

describe('the bypass counter', () => {
    it('counts palette steps with their variants and opacity, white and black included', () => {
        expect(countBypasses('class="text-slate-600 dark:hover:bg-slate-800/50 bg-brand-700 text-white"').palette).toBe(4);
    });

    it('does not count the semantic tokens', () => {
        const tokens = 'bg-surface bg-surface-raised text-strong text-ink text-muted border-line ring-focus bg-accent text-accent-fg text-status-fail bg-status-ok-soft border-status-attention-line';
        expect(countBypasses(tokens)).toEqual({ palette: 0, dark: 0, arbitrary: 0 });
    });

    it('counts a dark colour override, not a dark size or layout change', () => {
        expect(countBypasses('dark:text-slate-300 dark:bg-surface dark:border-white/10 dark:text-sm dark:shadow-none dark:ring-inset').dark).toBe(3);
    });

    it('counts arbitrary values and properties, not ordinary indexing', () => {
        expect(countBypasses('w-[3px] grid-cols-[9rem_1fr] md:[mask:none] items[0] rows[index]').arbitrary).toBe(3);
    });

    it('skips an allowlisted literal colour in its own file only', () => {
        const swatch = 'bg-blue-600 ring-amber-400';
        expect(countBypasses(swatch, 'lib/components/settings/AppearanceSettings.svelte').palette).toBe(0);
        expect(countBypasses(swatch, 'lib/components/Sidebar.svelte').palette).toBe(2);
    });
});

describe('a stylesheet', () => {
    it('counts its @apply lists like any markup', () => {
        expect(countBypasses('.x { @apply text-amber-600 dark:text-strong w-[3px]; }', 'lib/new.css')).toEqual({ palette: 1, dark: 1, arbitrary: 1 });
    });

    // app.css keeps its high-contrast repaint rules nested in one top-level `.high-contrast { … }`
    // rule. Only rules inside that rule are exempt, and only their selectors.
    it('skips the selectors of rules nested in the one high-contrast scope rule', () => {
        const css = '.high-contrast { color-scheme: dark; & .bg-white, & :is(.bg-brand-700, [class~="bg-red-600"]) * { color: #fff; } & .dark\\:bg-slate-800 { color: #fff; } }';
        expect(countBypasses(css, 'app.css').palette).toBe(0);
        expect(countBypasses(css, 'lib/other.css').palette).toBe(4);
    });

    it('still counts what a rule inside the scope applies', () => {
        expect(countBypasses('.high-contrast { & .x { @apply bg-slate-900; } }', 'app.css').palette).toBe(1);
    });

    it('counts a top-level rule that only looks scoped: a flat selector list, a quoted bracket, an escaped class', () => {
        expect(countBypasses('.text-amber-600 { color: #d97706; }', 'app.css').palette).toBe(1);
        expect(countBypasses('.high-contrast .bg-white, .bg-slate-900 { color: #fff; }', 'app.css').palette).toBe(2);
        expect(countBypasses('.high-contrast [data-label="("], .text-amber-600 { color: #d97706; }', 'app.css').palette).toBe(1);
        expect(countBypasses('.high-contrast\\:text-amber-600 { color: #d97706; }', 'app.css').palette).toBe(1);
    });

    it('allows exactly one scope rule, so a second one cannot open another exemption', () => {
        expect(() => countBypasses('.high-contrast { & .a { color: red; } } .high-contrast { & .bg-white { color: red; } }', 'app.css')).toThrow(/one/);
    });

    it('ignores comments, which paint nothing', () => {
        expect(countBypasses('/* was text-slate-600 dark:text-slate-400 */ .x { color: red; }', 'lib/other.css')).toEqual({ palette: 0, dark: 0, arbitrary: 0 });
    });

    it('scans the authored stylesheets, app.css among them', () => {
        const scanned = sourceFiles(SOURCE_ROOT).map((path) => relative(SOURCE_ROOT, path).replaceAll('\\', '/'));
        expect(scanned).toContain('app.css');
        expect(scanned).toContain('tailwind-3-parity.css');
    });
});

describe('the baseline updater', () => {
    const baseline = { 'a.svelte': { palette: 3, dark: 2, arbitrary: 1 } };

    it('lowers counts that fell', () => {
        const measured = { 'a.svelte': { palette: 1, dark: 2, arbitrary: 0 } };
        expect(lowerBaseline(baseline, measured)).toEqual({ next: measured, raised: [] });
    });

    it('refuses a rise rather than absorbing it, in a listed file or a new one', () => {
        const risen = lowerBaseline(baseline, { 'a.svelte': { palette: 4, dark: 2, arbitrary: 1 }, 'b.css': { palette: 0, dark: 1, arbitrary: 0 } });
        expect(risen.next).toBeNull();
        expect(risen.raised).toEqual(['a.svelte: palette 3 -> 4', 'b.css: dark 0 -> 1']);
    });

    it('lets CI refuse a branch whose committed baseline allows more than its base', () => {
        expect(raisedCounts(baseline, { 'a.svelte': { palette: 3, dark: 3, arbitrary: 1 } })).toEqual(['a.svelte: dark 2 -> 3']);
        expect(raisedCounts(baseline, { 'a.svelte': { palette: 2, dark: 0, arbitrary: 0 } })).toEqual([]);
    });
});

describe('the design-token ratchet', () => {
    const measured = measure();
    const committed: Baseline = existsSync(BASELINE_PATH) ? JSON.parse(readFileSync(BASELINE_PATH, 'utf8')) : {};

    if ((globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env.UPDATE_TOKEN_BASELINE === '1') {
        // The updater only ever lowers: a rise is refused and nothing is written.
        const { next, raised } = lowerBaseline(committed, measured);
        if (!next) throw new Error(`[tokens] refusing to raise the baseline:\n  ${raised.join('\n  ')}\nUse the semantic tokens instead.`);
        writeFileSync(BASELINE_PATH, JSON.stringify(next, null, 2) + '\n');
        const sum = totals(next);
        console.log(`[tokens] baseline lowered: ${sum.palette} palette, ${sum.dark} dark, ${sum.arbitrary} arbitrary in ${sum.files} files`);
    }

    const baseline: Baseline = existsSync(BASELINE_PATH) ? JSON.parse(readFileSync(BASELINE_PATH, 'utf8')) : {};
    const zero: Counts = { palette: 0, dark: 0, arbitrary: 0 };

    it('lets no file add a raw palette class, a dark: colour override or an arbitrary value', () => {
        const risen: string[] = [];
        for (const [file, counts] of Object.entries(measured)) {
            const allowed = baseline[file] ?? zero;
            for (const kind of ['palette', 'dark', 'arbitrary'] as const) {
                if (counts[kind] > allowed[kind]) risen.push(`${file}: ${kind} ${allowed[kind]} -> ${counts[kind]} (use the semantic tokens in app.css)`);
            }
        }
        expect(risen).toEqual([]);
    });

    it('is lowered in the same change as a migration, so it never loosens again', () => {
        const stale: string[] = [];
        for (const [file, allowed] of Object.entries(baseline)) {
            const counts = measured[file] ?? zero;
            for (const kind of ['palette', 'dark', 'arbitrary'] as const) {
                if (counts[kind] < allowed[kind]) stale.push(`${file}: ${kind} baseline ${allowed[kind]}, now ${counts[kind]} (run npm run tokens:baseline)`);
            }
        }
        expect(stale).toEqual([]);
    });
});
