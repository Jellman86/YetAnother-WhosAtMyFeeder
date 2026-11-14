import { describe, expect, it } from 'vitest';
// @ts-expect-error -- node built-ins resolve at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';
// @ts-expect-error -- node built-ins resolve at runtime, not in the app tsconfig
import { dirname } from 'node:path';
// @ts-expect-error -- node built-ins resolve at runtime, not in the app tsconfig
import { fileURLToPath } from 'node:url';
import { compile, optimize } from '@tailwindcss/node';
import { Scanner } from '@tailwindcss/oxide';
import { FIXTURE_TAILWIND_VERSION, dropUnsupportedBrowserFallbacks } from './supported-browser-css';

const COLOR_MIX = '@supports (color:color-mix(in lab, red, red))';
const SRGB = 'color-mix(in srgb, rgb(var(--brand-500)) 5%, transparent)';
const OKLAB = 'color-mix(in oklab, var(--color-brand-500) 5%, transparent)';

/** One fallback rule and the block that overrides it, in the shape Tailwind writes them. */
function pair(fallbackRule: string, override: string, selector = '.a'): string {
    return `${fallbackRule}${COLOR_MIX}{${selector}{${override}}}`;
}

/** Asserts a stylesheet comes back byte for byte, and returns why each block was left. */
function retained(built: string): string[] {
    const result = dropUnsupportedBrowserFallbacks(built);
    expect(result.css).toBe(built);
    expect(result.unwrapped).toBe(0);
    return result.retained.map(entry => entry.reason);
}

/**
 * The stylesheets under "Tailwind's own output" are Tailwind 4.3.5 output as the production build
 * minifies it, copied from `dist/assets/index-*.css` before this step runs.
 */
describe("Tailwind's own output loses the fallbacks no supported browser reads", () => {
    it('keeps the color-mix value and deletes a color-mix fallback', () => {
        const built = `.bg-brand-500\\/5{background-color:${SRGB}}${COLOR_MIX}{.bg-brand-500\\/5{background-color:${OKLAB}}}`;

        expect(dropUnsupportedBrowserFallbacks(built)).toEqual({ css: `.bg-brand-500\\/5{background-color:${OKLAB}}`, unwrapped: 1, retained: [] });
    });

    it('deletes a hex fallback for a shadow colour', () => {
        const value = 'color-mix(in oklab, oklab(0% none none/.5) var(--tw-shadow-alpha), transparent)';
        const built = `.shadow-black\\/50{--tw-shadow-color:#00000080}${COLOR_MIX}{.shadow-black\\/50{--tw-shadow-color:${value}}}`;

        expect(dropUnsupportedBrowserFallbacks(built).css).toBe(`.shadow-black\\/50{--tw-shadow-color:${value}}`);
    });

    it('deletes a currentColor fallback', () => {
        const value = 'color-mix(in oklab, currentcolor 30%, transparent)';
        const built = `.border-current\\/30{border-color:currentColor}${COLOR_MIX}{.border-current\\/30{border-color:${value}}}`;

        expect(dropUnsupportedBrowserFallbacks(built).css).toBe(`.border-current\\/30{border-color:${value}}`);
    });

    it('deletes only the fallback from a rule that sets more', () => {
        const ring = '--tw-ring-shadow:var(--tw-ring-inset, ) 0 0 0 calc(2px + var(--tw-ring-offset-width)) var(--tw-ring-color,currentcolor);box-shadow:var(--tw-ring-shadow), var(--tw-shadow)';
        const fallback = 'color-mix(in srgb, rgb(var(--brand-500)) 50%, transparent)';
        const value = 'color-mix(in oklab, var(--color-brand-500) 50%, transparent)';
        const built = `.focus-ring:focus{${ring};--tw-ring-color:${fallback}}${COLOR_MIX}{.focus-ring:focus{--tw-ring-color:${value}}}.focus-ring:focus{--tw-ring-offset-width:2px}`;

        expect(dropUnsupportedBrowserFallbacks(built).css).toBe(
            `.focus-ring:focus{${ring}}.focus-ring:focus{--tw-ring-color:${value}}.focus-ring:focus{--tw-ring-offset-width:2px}`
        );
    });

    it('works inside a layer and a breakpoint', () => {
        const built = `@layer utilities{.a{color:blue}@media (min-width:1024px){${pair(`.a{color:${SRGB}}`, `color:${OKLAB}`)}}}`;

        expect(dropUnsupportedBrowserFallbacks(built).css).toBe(`@layer utilities{.a{color:blue}@media (min-width:1024px){.a{color:${OKLAB}}}}`);
    });

    it('drops the initial values written for browsers without @property and keeps the layer', () => {
        const built =
            '@layer properties{@supports (((-webkit-hyphens:none)) and (not (margin-trim:block))) or ((-moz-orient:inline) and (not (color:rgb(from red r g b)))){*,:before,:after,::backdrop{--tw-font-weight:initial;--tw-shadow:0 0 #0000}}}' +
            '@property --tw-font-weight{syntax:"*";inherits:false}';

        expect(dropUnsupportedBrowserFallbacks(built).css).toBe('@layer properties{}@property --tw-font-weight{syntax:"*";inherits:false}');
    });

    it('returns a stylesheet with nothing to unwrap byte for byte', () => {
        const built =
            '/*! tailwindcss v4.3.5 | MIT License | https://tailwindcss.com */@layer theme,base,components,utilities;' +
            '.before\\:content-\\[\\\'·\\\'\\]:before{--tw-content:"·";content:var(--tw-content)}' +
            ".select-base{background-image:url(\"data:image/svg+xml,%3Csvg width='12' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M5 7l5 6 5-6' stroke='%2364748b'/%3E%3C/svg%3E\");background-size:12px 12px}" +
            '@keyframes ping{75%,to{opacity:0;transform:scale(2)}}@media (forced-colors:active){.outline-hidden{outline-offset:2px;outline:2px solid #0000}}' +
            '.bg-linear-to-b\\/srgb{--tw-gradient-position:to bottom}@supports (background-image:linear-gradient(in lab, red, red)){.bg-linear-to-b\\/srgb{--tw-gradient-position:to bottom in srgb}}';

        expect(dropUnsupportedBrowserFallbacks(built)).toEqual({ css: built, unwrapped: 0, retained: [] });
    });
});

describe('a block that does not validate exactly is left as written, never guessed at', () => {
    it('when the selectors differ only in whitespace, which changes what they match', () => {
        expect(retained(pair(`.a b{color:${SRGB}}`, `color:${OKLAB}`, '.ab'))).toEqual(['the rule before the block has a different selector']);
        expect(retained(pair(`.ab{color:${SRGB}}`, `color:${OKLAB}`, '.a b'))).toEqual(['the rule before the block has a different selector']);
        expect(retained(pair(`.a>b{color:${SRGB}}`, `color:${OKLAB}`, '.a > b'))).toEqual(['the rule before the block has a different selector']);
    });

    it('when the rule before the block has another selector', () => {
        expect(retained(pair(`.b{color:${SRGB}}`, `color:${OKLAB}`))).toEqual(['the rule before the block has a different selector']);
    });

    it('when another rule sits between the fallback and the block', () => {
        expect(retained(`.a{color:${SRGB}}.b{color:red}${COLOR_MIX}{.a{color:${OKLAB}}}`)).toEqual(['the rule before the block has a different selector']);
    });

    it('when nothing precedes the block in its own at-rule', () => {
        expect(retained(`.a{color:${SRGB}}@media (min-width:1024px){${COLOR_MIX}{.a{color:${OKLAB}}}}`)).toEqual(['no rule comes before the block']);
    });

    it('when the fallback is a variable, as an arbitrary colour like text-[var(--x)]/50 gives', () => {
        const built = `.text-\\[var\\(--x\\)\\]\\/50{color:var(--x)}${COLOR_MIX}{.text-\\[var\\(--x\\)\\]\\/50{color:color-mix(in oklab, var(--x) 50%, transparent)}}`;

        expect(retained(built)).toEqual(['the fallback is a variable, which is kept']);
    });

    it('when the property is set twice in the fallback rule', () => {
        expect(retained(pair(`.a{color:#e2e8f0;color:${SRGB}}`, `color:${OKLAB}`))).toEqual(['color is set 2 times in the fallback rule']);
    });

    it('when the fallback rule does not set the property', () => {
        expect(retained(pair('.a{opacity:1}', `color:${OKLAB}`))).toEqual(['color is set 0 times in the fallback rule']);
    });

    it('when a shorthand in the fallback rule also sets the colour', () => {
        expect(retained(pair(`.a{background-color:${SRGB};background:red}`, `background-color:${OKLAB}`))).toEqual([
            'background in the fallback rule also sets background-color'
        ]);
        expect(retained(pair(`.a{border-color:${SRGB};border:1px solid red}`, `border-color:${OKLAB}`))).toEqual([
            'border in the fallback rule also sets border-color'
        ]);
        expect(retained(pair(`.a{border-top:1px solid red;border-color:${SRGB}}`, `border-color:${OKLAB}`))).toEqual([
            'border-top in the fallback rule also sets border-color'
        ]);
    });

    it('when a longhand in the fallback rule also sets the colour', () => {
        expect(retained(pair(`.a{border-color:${SRGB};border-top-color:red}`, `border-color:${OKLAB}`))).toEqual([
            'border-top-color in the fallback rule also sets border-color'
        ]);
        expect(retained(pair(`.a{outline-color:${SRGB};outline:2px solid red}`, `outline-color:${OKLAB}`))).toEqual([
            'outline in the fallback rule also sets outline-color'
        ]);
    });

    it('but a neighbour that sets something else does not stop it', () => {
        const built = pair(`.a{border-style:solid;border-width:1px;border-color:${SRGB};background-image:none}`, `border-color:${OKLAB}`);

        expect(dropUnsupportedBrowserFallbacks(built).css).toBe(`.a{border-style:solid;border-width:1px;background-image:none}.a{border-color:${OKLAB}}`);
    });

    it('when !important differs between the two', () => {
        expect(retained(pair(`.a{color:${SRGB}!important}`, `color:${OKLAB}`))).toEqual(['color differs in !important']);
        expect(retained(pair(`.a{color:${SRGB}}`, `color:${OKLAB}!important`))).toEqual(['color differs in !important']);
    });

    it('while two !important declarations are still a pair', () => {
        expect(dropUnsupportedBrowserFallbacks(pair(`.a{color:${SRGB}!important}`, `color:${OKLAB}!important`)).css).toBe(`.a{color:${OKLAB}!important}`);
    });

    it('when the fallback is not one of the values Tailwind has been seen to write', () => {
        for (const value of ['red', 'rgb(0 0 0 / 0.5)', 'color-mix(in oklab, red 5%, blue)', 'color-mix(in srgb, red 5%, blue)', 'CURRENTCOLOR']) {
            expect(retained(pair(`.a{color:${value}}`, `color:${OKLAB}`))).toEqual(['the fallback is not a value Tailwind writes']);
        }
    });

    it('when the override is not an oklab color-mix value', () => {
        expect(retained(pair(`.a{color:${SRGB}}`, 'color:red'))).toEqual(['the override is not an oklab color-mix value']);
        expect(retained(pair(`.a{color:${SRGB}}`, `color:${SRGB}`))).toEqual(['the override is not an oklab color-mix value']);
    });

    it('when the block holds more than one rule, or something that is not a rule', () => {
        expect(retained(`.a{color:${SRGB}}${COLOR_MIX}{.a{color:${OKLAB}}.b{color:${OKLAB}}}`)).toEqual(['the block does not hold exactly one rule']);
        expect(retained(`.a{color:${SRGB}}${COLOR_MIX}{@media (min-width:1px){.a{color:${OKLAB}}}}`)).toEqual(['the block does not hold exactly one rule']);
    });

    it('and one declaration that fails keeps the whole pair', () => {
        expect(retained(pair(`.a{color:${SRGB};background-color:red}`, `color:${OKLAB};background-color:${OKLAB}`))).toEqual([
            'the fallback is not a value Tailwind writes'
        ]);
    });

    it('when the @property block carries anything but initial values on the universal selector', () => {
        const built =
            '@layer properties{@supports (((-webkit-hyphens:none)) and (not (margin-trim:block))) or ((-moz-orient:inline) and (not (color:rgb(from red r g b)))){.a{color:red}}}';

        expect(retained(built)).toEqual(['the @property fallback block holds more than initial values']);
    });

    it('and a stylesheet that does not parse comes back as it was', () => {
        const broken = `.a{color:${SRGB}}${COLOR_MIX}{.a{color:${OKLAB}}`;

        expect(dropUnsupportedBrowserFallbacks(broken)).toEqual({ css: broken, unwrapped: 0, retained: [] });
    });
});

describe('the condition is read as tokens, so its spelling does not matter', () => {
    const FALLBACK = `.a{color:${SRGB}}`;
    const OVERRIDE = `{.a{color:${OKLAB}}}`;

    it.each([
        ['with no space after @supports', '@supports(color:color-mix(in lab,red,red))'],
        ['with extra spaces and capitals', '@SUPPORTS ( color : color-mix( in lab , red , red ) ) '],
        ['with a comment inside the condition', '@supports(color:/**/color-mix(in lab, red, red))'],
        ['with comments between every token', '@supports /* a */ ( /* b */ color /* c */ : color-mix( in /* d */ lab , red , red ) )']
    ])('%s', (_name, prelude) => {
        const result = dropUnsupportedBrowserFallbacks(`${FALLBACK}${prelude}${OVERRIDE}`);

        expect(result.unwrapped).toBe(1);
        expect(result.css).toBe(`.a{color:${OKLAB}}`);
    });

    it.each([
        ['another @supports condition', '@supports (background-image:linear-gradient(in lab, red, red)){.a{color:red}}'],
        ['color-mix used as a value', `.a{color:${OKLAB}}`],
        ['the condition quoted in a comment', '/* @supports (color:color-mix(in lab, red, red)) */.a{color:red}'],
        ['the condition inside a string', '.a:before{content:"@supports (color:color-mix(in lab, red, red)){}"}'],
        ['a string that only looks like the condition', '@supports (color:"color-mix(in lab, red, red)"){.a{color:red}}']
    ])('and %s is not taken for it', (_name, css) => {
        expect(dropUnsupportedBrowserFallbacks(css)).toEqual({ css, unwrapped: 0, retained: [] });
    });

    it('unwraps a pair in unminified output with a comment between the two', () => {
        const built = `.a {\n  color: ${SRGB};\n}\n/* fallback above */\n@supports (color: color-mix(in lab, red, red)) {\n  .a {\n    color: ${OKLAB};\n  }\n}\n`;
        const result = dropUnsupportedBrowserFallbacks(built);

        expect(result.unwrapped).toBe(1);
        expect(result.css.replace(/\s+/g, '')).toBe(`/*fallbackabove*/.a{color:${OKLAB.replace(/\s+/g, '')};}`);
    });
});

/**
 * Drift is caught here, not in the build. This compiles the app's real stylesheet with the
 * installed Tailwind, the way the Vite plugin does, and runs the step over it. If a Tailwind
 * upgrade changes the shape of its fallbacks, this fails with the blocks it could no longer
 * unwrap; the production build itself never fails, it only ships a few more bytes.
 */
describe("the app's real stylesheet, compiled with the installed Tailwind", () => {
    async function compileAppCss(): Promise<string> {
        const file = fileURLToPath(new URL('../../app.css', import.meta.url));
        const base = dirname(file);
        const compiler = await compile(readFileSync(file, 'utf8'), { base, from: file, onDependency: () => undefined });
        const root = compiler.root === 'none' ? [] : compiler.root === null ? [{ base, pattern: '**/*', negated: false }] : [{ ...compiler.root, negated: false }];
        const scanner = new Scanner({ sources: [...root, ...compiler.sources] });
        return optimize(compiler.build(scanner.scan()), { minify: true }).code;
    }

    it('has every fallback unwrapped, with nothing retained', async () => {
        const result = dropUnsupportedBrowserFallbacks(await compileAppCss());

        expect(result.retained, 'Blocks the build step could not unwrap. If Tailwind changed its output, update supported-browser-css.ts and its fixtures.').toEqual([]);
        expect(result.unwrapped).toBeGreaterThan(150);
        expect(result.css).not.toMatch(/@supports\s*\(color:\s*color-mix/);
    });

    it('is compiled with the Tailwind version the fixtures above were copied from', () => {
        const packageJson = (path: string): { version: string; devDependencies: Record<string, string> } =>
            JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'));
        const pinned = packageJson('../../../package.json').devDependencies;

        for (const name of ['tailwindcss', '@tailwindcss/vite', '@tailwindcss/node', '@tailwindcss/oxide']) {
            expect(packageJson(`../../../node_modules/${name}/package.json`).version, name).toBe(FIXTURE_TAILWIND_VERSION);
            expect(pinned[name], `${name} in package.json`).toBe(FIXTURE_TAILWIND_VERSION);
        }
    });
});
