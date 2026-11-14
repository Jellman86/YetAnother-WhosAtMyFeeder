import { describe, expect, it } from 'vitest';
// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';
import {
    FIXTURE_TAILWIND_VERSION,
    dropUnsupportedBrowserFallbacks,
    hasUnsupportedBrowserFallbacks
} from './supported-browser-css';

const COLOR_MIX = '@supports (color:color-mix(in lab, red, red))';
const SRGB = 'color-mix(in srgb, rgb(var(--brand-500)) 5%, transparent)';
const OKLAB = 'color-mix(in oklab, var(--color-brand-500) 5%, transparent)';

/** One fallback rule and the block that overrides it, in the shape Tailwind writes them. */
function pair(fallbackRule: string, override: string, selector = '.a'): string {
    return `${fallbackRule}${COLOR_MIX}{${selector}{${override}}}`;
}

/**
 * The stylesheets under "Tailwind's own output" are Tailwind 4.3.5 output as the production build
 * minifies it, copied from `dist/assets/index-*.css` before this step runs. The version gate at
 * the end makes an upgrade refresh them on purpose.
 */
describe("Tailwind's own output loses the fallbacks no supported browser reads", () => {
    it('keeps the color-mix value and deletes a color-mix fallback', () => {
        const built = `.bg-brand-500\\/5{background-color:${SRGB}}${COLOR_MIX}{.bg-brand-500\\/5{background-color:${OKLAB}}}`;

        expect(dropUnsupportedBrowserFallbacks(built)).toEqual({ css: `.bg-brand-500\\/5{background-color:${OKLAB}}`, removed: 1, kept: [] });
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

    it('leaves every other @supports block alone', () => {
        const built =
            '.bg-linear-to-b\\/srgb{--tw-gradient-position:to bottom}' +
            '@supports (background-image:linear-gradient(in lab, red, red)){.bg-linear-to-b\\/srgb{--tw-gradient-position:to bottom in srgb}}';

        expect(dropUnsupportedBrowserFallbacks(built)).toEqual({ css: built, removed: 0, kept: [] });
    });

    it('returns a stylesheet with nothing to remove byte for byte', () => {
        const built =
            '/*! tailwindcss v4.3.5 | MIT License | https://tailwindcss.com */@layer theme,base,components,utilities;' +
            '.before\\:content-\\[\\\'·\\\'\\]:before{--tw-content:"·";content:var(--tw-content)}' +
            ".select-base{background-image:url(\"data:image/svg+xml,%3Csvg width='12' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M5 7l5 6 5-6' stroke='%2364748b'/%3E%3C/svg%3E\");background-size:12px 12px}" +
            '@keyframes ping{75%,to{opacity:0;transform:scale(2)}}@media (forced-colors:active){.outline-hidden{outline-offset:2px;outline:2px solid #0000}}';

        expect(dropUnsupportedBrowserFallbacks(built).css).toBe(built);
    });
});

describe('a pair that is not provably a Tailwind fallback is left exactly as it was', () => {
    function kept(built: string): string[] {
        const result = dropUnsupportedBrowserFallbacks(built);
        expect(result.css).toBe(built);
        expect(result.removed).toBe(0);
        return result.kept.map(entry => entry.reason);
    }

    it('when the rule before the block has another selector', () => {
        expect(kept(pair(`.b{color:${SRGB}}`, `color:${OKLAB}`))).toEqual(['the rule before the block has a different selector']);
    });

    it('when another rule sits between the fallback and the block', () => {
        expect(kept(`.a{color:${SRGB}}.b{color:red}${COLOR_MIX}{.a{color:${OKLAB}}}`)).toEqual(['the rule before the block has a different selector']);
    });

    it('when nothing precedes the block in its own at-rule', () => {
        expect(kept(`.a{color:${SRGB}}@media (min-width:1024px){${COLOR_MIX}{.a{color:${OKLAB}}}}`)).toEqual(['no rule comes before the block']);
    });

    it('when the property is set twice in the fallback rule', () => {
        expect(kept(pair(`.a{color:#e2e8f0;color:${SRGB}}`, `color:${OKLAB}`))).toEqual(['color is set 2 times in the fallback rule']);
    });

    it('when the fallback rule does not set the property', () => {
        expect(kept(pair('.a{opacity:1}', `color:${OKLAB}`))).toEqual(['color is set 0 times in the fallback rule']);
    });

    it('when a shorthand in the fallback rule also sets the colour', () => {
        expect(kept(pair(`.a{background-color:${SRGB};background:red}`, `background-color:${OKLAB}`))).toEqual([
            'background in the fallback rule also sets background-color'
        ]);
        expect(kept(pair(`.a{border-color:${SRGB};border:1px solid red}`, `border-color:${OKLAB}`))).toEqual([
            'border in the fallback rule also sets border-color'
        ]);
        expect(kept(pair(`.a{border-top:1px solid red;border-color:${SRGB}}`, `border-color:${OKLAB}`))).toEqual([
            'border-top in the fallback rule also sets border-color'
        ]);
    });

    it('when a longhand in the fallback rule also sets the colour', () => {
        expect(kept(pair(`.a{border-color:${SRGB};border-top-color:red}`, `border-color:${OKLAB}`))).toEqual([
            'border-top-color in the fallback rule also sets border-color'
        ]);
        expect(kept(pair(`.a{outline-color:${SRGB};outline:2px solid red}`, `outline-color:${OKLAB}`))).toEqual([
            'outline in the fallback rule also sets outline-color'
        ]);
    });

    it('but not for a neighbour that sets something else', () => {
        const built = pair(`.a{border-style:solid;border-width:1px;border-color:${SRGB};background-image:none}`, `border-color:${OKLAB}`);

        expect(dropUnsupportedBrowserFallbacks(built).css).toBe(`.a{border-style:solid;border-width:1px;background-image:none}.a{border-color:${OKLAB}}`);
    });

    it('when !important differs between the two', () => {
        expect(kept(pair(`.a{color:${SRGB}!important}`, `color:${OKLAB}`))).toEqual(['color differs in !important']);
        expect(kept(pair(`.a{color:${SRGB}}`, `color:${OKLAB}!important`))).toEqual(['color differs in !important']);
    });

    it('when both are !important it is still a pair', () => {
        expect(dropUnsupportedBrowserFallbacks(pair(`.a{color:${SRGB}!important}`, `color:${OKLAB}!important`)).css).toBe(`.a{color:${OKLAB}!important}`);
    });

    it('when the fallback is not one of the values Tailwind writes', () => {
        for (const value of ['red', 'var(--x)', 'rgb(0 0 0 / 0.5)', 'color-mix(in oklab, red 5%, blue)']) {
            expect(kept(pair(`.a{color:${value}}`, `color:${OKLAB}`))).toEqual([`${value} is not a fallback Tailwind writes`]);
        }
    });

    it('when the override is not a color-mix value', () => {
        expect(kept(pair(`.a{color:${SRGB}}`, 'color:red'))).toEqual(['red is not a color-mix value']);
    });

    it('when the block holds more than one rule, or something that is not a rule', () => {
        expect(kept(`.a{color:${SRGB}}${COLOR_MIX}{.a{color:${OKLAB}}.b{color:${OKLAB}}}`)).toEqual(['the block does not hold exactly one rule']);
        expect(kept(`.a{color:${SRGB}}${COLOR_MIX}{@media (min-width:1px){.a{color:${OKLAB}}}}`)).toEqual(['the block does not hold exactly one rule']);
    });

    it('and one unsafe declaration keeps the whole pair', () => {
        expect(kept(pair(`.a{color:${SRGB};background-color:red}`, `color:${OKLAB};background-color:${OKLAB}`))).toEqual([
            'red is not a fallback Tailwind writes'
        ]);
    });

    it('when the @property block carries anything but initial values on the universal selector', () => {
        const built =
            '@layer properties{@supports (((-webkit-hyphens:none)) and (not (margin-trim:block))) or ((-moz-orient:inline) and (not (color:rgb(from red r g b)))){.a{color:red}}}';

        expect(kept(built)).toEqual(['the @property fallback block holds more than initial values']);
    });
});

describe('fallbacks are found by parsing, however the stylesheet is written', () => {
    const OVERRIDE = `{.a{color:${OKLAB}}}`;

    it.each([
        ['as Lightning CSS minifies it', `${COLOR_MIX}${OVERRIDE}`],
        ['with no space after @supports', `@supports(color:color-mix(in lab,red,red))${OVERRIDE}`],
        ['with extra spaces and capitals', `@SUPPORTS ( color : color-mix( in lab , red , red ) ) ${OVERRIDE}`],
        ['unminified', `@supports (color: color-mix(in lab, red, red)) {\n  .a {\n    color: ${OKLAB};\n  }\n}\n`],
        ['behind a comment', `/* note */ ${COLOR_MIX}/* why */${OVERRIDE}`],
        ['nested in a layer and a breakpoint', `@layer utilities{@media (min-width:1024px){${COLOR_MIX}${OVERRIDE}}}`],
        ['as the @property fallback', '@layer properties{@supports (((-webkit-hyphens:none)) and (not (margin-trim:block))) or ((-moz-orient:inline) and (not (color:rgb(from red r g b)))){*{--tw-x:initial}}}']
    ])('%s', (_name, css) => {
        expect(hasUnsupportedBrowserFallbacks(css)).toBe(true);
    });

    it.each([
        ['another @supports condition', '@supports (background-image:linear-gradient(in lab, red, red)){.a{color:red}}'],
        ['color-mix used as a value', `.a{color:${OKLAB}}`],
        ['the condition quoted in a comment', '/* @supports (color:color-mix(in lab, red, red)) */.a{color:red}'],
        ['the condition inside a string', '.a:before{content:"@supports (color:color-mix(in lab, red, red)){}"}']
    ])('and not in %s', (_name, css) => {
        expect(hasUnsupportedBrowserFallbacks(css)).toBe(false);
    });

    it('removes a pair from unminified output with a comment between the two', () => {
        const built = `.a {\n  color: ${SRGB};\n}\n/* fallback above */\n@supports (color: color-mix(in lab, red, red)) {\n  .a {\n    color: ${OKLAB};\n  }\n}\n`;
        const result = dropUnsupportedBrowserFallbacks(built);

        expect(result.removed).toBe(1);
        expect(hasUnsupportedBrowserFallbacks(result.css)).toBe(false);
        expect(result.css.replace(/\s+/g, '')).toBe(`/*fallbackabove*/.a{color:${OKLAB.replace(/\s+/g, '')};}`);
    });

    it('removes a pair written with no space after @supports', () => {
        const built = `.a{color:${SRGB}}@supports(color:color-mix(in lab,red,red)){.a{color:${OKLAB}}}`;

        expect(dropUnsupportedBrowserFallbacks(built).css).toBe(`.a{color:${OKLAB}}`);
    });
});

describe('the fixtures above are tied to the Tailwind version they were copied from', () => {
    function packageJson(path: string): { version: string; devDependencies: Record<string, string> } {
        return JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'));
    }

    it('is the installed version, so an upgrade has to refresh them', () => {
        expect(packageJson('../../../node_modules/tailwindcss/package.json').version).toBe(FIXTURE_TAILWIND_VERSION);
        expect(packageJson('../../../node_modules/@tailwindcss/vite/package.json').version).toBe(FIXTURE_TAILWIND_VERSION);
    });

    it('is pinned exactly, so the installed version cannot drift on its own', () => {
        const pinned = packageJson('../../../package.json').devDependencies;

        expect(pinned.tailwindcss).toBe(FIXTURE_TAILWIND_VERSION);
        expect(pinned['@tailwindcss/vite']).toBe(FIXTURE_TAILWIND_VERSION);
    });
});
