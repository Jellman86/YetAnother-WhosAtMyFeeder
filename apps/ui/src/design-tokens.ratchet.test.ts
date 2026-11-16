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
 * Parts of a stylesheet that name classes without painting with them. High contrast repaints the
 * older palette classes by name (`.high-contrast .bg-white`, `[class~='bg-attention-300']`) so that
 * screens not yet on the tokens stay readable; those selectors shrink as the migration proceeds,
 * and they are counted nowhere. Everything else in app.css, its `@apply` lists included, counts.
 */
const STYLESHEET_EXCEPTIONS: Record<string, { from: string; to: string; reason: string }> = {
    'app.css': {
        from: '/* High Contrast Mode',
        to: '/* Respect user motion preferences',
        reason: 'the high-contrast repaint selectors name legacy classes to override them; they paint nothing themselves'
    }
};

/** Split a selector list at its top-level commas, leaving those inside `:is(...)` or `[...]` alone. */
function selectorsOf(list: string): string[] {
    const parts: string[] = [];
    let depth = 0;
    let current = '';
    for (const char of list) {
        if (char === '(' || char === '[') depth += 1;
        if (char === ')' || char === ']') depth -= 1;
        if (char === ',' && depth === 0) {
            parts.push(current.trim());
            current = '';
        } else current += char;
    }
    parts.push(current.trim());
    return parts.filter(Boolean);
}

/** Scoped to the high-contrast root: `.high-contrast …` or `html.high-contrast…`. */
const HIGH_CONTRAST_SCOPE = /^(?:html)?\.high-contrast(?![\w-])/;

function withoutExceptions(source: string, file: string): string {
    const exception = STYLESHEET_EXCEPTIONS[file];
    if (!exception) return source;
    const from = source.indexOf(exception.from);
    const to = source.indexOf(exception.to, from);
    if (from < 0 || to < 0) throw new Error(`${file}: the ${exception.from} section the ratchet skips has moved`);
    // Comments are words, not rules. A selector list is skipped only when every selector in it is
    // scoped to the high-contrast root; an ordinary rule placed in the section, or a list that mixes
    // one in, is counted like any other. Declarations, and so any @apply, always count.
    const section = source
        .slice(from, to)
        .replace(/\/\*[\s\S]*?\*\//g, '')
        .replace(/([^{}]*)\{/g, (whole, list: string) => {
            const selectors = selectorsOf(list);
            const scoped = selectors.length > 0 && selectors.every((selector) => HIGH_CONTRAST_SCOPE.test(selector));
            return scoped ? '{' : whole;
        });
    return source.slice(0, from) + section + source.slice(to);
}

function countBypasses(raw: string, file = ''): Counts {
    const source = withoutExceptions(raw, file);
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

    it('skips only the high-contrast repaint selectors in app.css, not what that section applies', () => {
        const css = '.a { @apply text-amber-600; }\n/* High Contrast Mode */\n.high-contrast .bg-white, .high-contrast .dark\\:bg-slate-800 { color: #fff; }\n.high-contrast .b { @apply bg-slate-900; }\n/* Respect user motion preferences */';
        expect(countBypasses(css, 'app.css').palette).toBe(2);
        expect(countBypasses(css, 'lib/other.css').palette).toBe(4);
    });

    const hcSection = (rules: string) => `/* High Contrast Mode */\n${rules}\n/* Respect user motion preferences */`;

    it('counts an ordinary rule placed between the high-contrast markers', () => {
        expect(countBypasses(hcSection('.text-amber-600 { color: #d97706; }'), 'app.css').palette).toBe(1);
    });

    it('counts a selector list that mixes a high-contrast selector with an unscoped one', () => {
        expect(countBypasses(hcSection('.high-contrast .bg-white, .bg-slate-900 { color: #fff; }'), 'app.css').palette).toBe(2);
    });

    it('skips a selector scoped to the high-contrast root, by class or on html, and ignores comments', () => {
        const rules = '/* repaints [class*=text-slate-500] */\nhtml.high-contrast.high-contrast .bg-white, .high-contrast :is(.bg-brand-700, [class~=\'bg-red-600\']) * { color: #fff; }';
        expect(countBypasses(hcSection(rules), 'app.css').palette).toBe(0);
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
