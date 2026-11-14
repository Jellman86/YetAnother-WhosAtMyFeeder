import { describe, expect, it } from 'vitest';
import { dropUnsupportedBrowserFallbacks, hasUnsupportedBrowserFallbacks } from './supported-browser-css';

/**
 * Every stylesheet here is Tailwind 4.3.5 output as the production build minifies it, copied
 * from `dist/assets/index-*.css`, so the shapes are the ones the build step really meets.
 */
describe('fallbacks no supported browser reads are removed from the built stylesheet', () => {
    it('keeps the color-mix value and deletes the fallback it overrides', () => {
        const built =
            '.bg-brand-500\\/5{background-color:color-mix(in srgb, rgb(var(--brand-500)) 5%, transparent)}' +
            '@supports (color:color-mix(in lab, red, red)){.bg-brand-500\\/5{background-color:color-mix(in oklab, var(--color-brand-500) 5%, transparent)}}';

        expect(dropUnsupportedBrowserFallbacks(built)).toBe(
            '.bg-brand-500\\/5{background-color:color-mix(in oklab, var(--color-brand-500) 5%, transparent)}'
        );
    });

    it('deletes only the overridden declaration from a rule that sets more', () => {
        const built =
            '.focus-ring:focus{--tw-ring-shadow:var(--tw-ring-inset, ) 0 0 0 calc(2px + var(--tw-ring-offset-width)) var(--tw-ring-color,currentcolor);box-shadow:var(--tw-ring-shadow), var(--tw-shadow);--tw-ring-color:color-mix(in srgb, rgb(var(--brand-500)) 50%, transparent)}' +
            '@supports (color:color-mix(in lab, red, red)){.focus-ring:focus{--tw-ring-color:color-mix(in oklab, var(--color-brand-500) 50%, transparent)}}' +
            '.focus-ring:focus{--tw-ring-offset-width:2px}';

        expect(dropUnsupportedBrowserFallbacks(built)).toBe(
            '.focus-ring:focus{--tw-ring-shadow:var(--tw-ring-inset, ) 0 0 0 calc(2px + var(--tw-ring-offset-width)) var(--tw-ring-color,currentcolor);box-shadow:var(--tw-ring-shadow), var(--tw-shadow)}' +
                '.focus-ring:focus{--tw-ring-color:color-mix(in oklab, var(--color-brand-500) 50%, transparent)}' +
                '.focus-ring:focus{--tw-ring-offset-width:2px}'
        );
    });

    it('leaves the value in place, after any rule that sat between it and its fallback', () => {
        const built =
            '.a{color:color-mix(in srgb, rgb(var(--brand-500)) 50%, transparent)}.b{color:red}' +
            '@supports (color:color-mix(in lab, red, red)){.a{color:color-mix(in oklab, var(--color-brand-500) 50%, transparent)}}';

        expect(dropUnsupportedBrowserFallbacks(built)).toBe(
            '.b{color:red}.a{color:color-mix(in oklab, var(--color-brand-500) 50%, transparent)}'
        );
    });

    it('does not delete an important fallback that a normal value cannot override', () => {
        const built =
            '.a{color:red!important}@supports (color:color-mix(in lab, red, red)){.a{color:color-mix(in oklab, var(--color-brand-500) 50%, transparent)}}';

        expect(dropUnsupportedBrowserFallbacks(built)).toBe(
            '.a{color:red!important}.a{color:color-mix(in oklab, var(--color-brand-500) 50%, transparent)}'
        );
    });

    it('works inside a layer and a breakpoint, and only among the rules beside it', () => {
        const built =
            '@layer utilities{.a{color:blue}@media (min-width:1024px){.a{color:color-mix(in srgb, rgb(var(--brand-500)) 20%, transparent)}' +
            '@supports (color:color-mix(in lab, red, red)){.a{color:color-mix(in oklab, var(--color-brand-500) 20%, transparent)}}}}';

        expect(dropUnsupportedBrowserFallbacks(built)).toBe(
            '@layer utilities{.a{color:blue}@media (min-width:1024px){.a{color:color-mix(in oklab, var(--color-brand-500) 20%, transparent)}}}'
        );
    });

    it('drops the initial values written for browsers without @property and keeps the layer', () => {
        const built =
            '@layer properties{@supports (((-webkit-hyphens:none)) and (not (margin-trim:block))) or ((-moz-orient:inline) and (not (color:rgb(from red r g b)))){*,:before,:after,::backdrop{--tw-font-weight:initial;--tw-shadow:0 0 #0000}}}' +
            '@property --tw-font-weight{syntax:"*";inherits:false}';

        expect(dropUnsupportedBrowserFallbacks(built)).toBe('@layer properties{}@property --tw-font-weight{syntax:"*";inherits:false}');
    });

    it('leaves every other @supports block alone', () => {
        const built =
            '.bg-linear-to-b\\/srgb{--tw-gradient-position:to bottom}' +
            '@supports (background-image:linear-gradient(in lab, red, red)){.bg-linear-to-b\\/srgb{--tw-gradient-position:to bottom in srgb}}';

        expect(dropUnsupportedBrowserFallbacks(built)).toBe(built);
    });

    it('returns a stylesheet with nothing to remove byte for byte', () => {
        const built =
            '/*! tailwindcss v4.3.5 | MIT License | https://tailwindcss.com */@layer theme,base,components,utilities;' +
            '.before\\:content-\\[\\\'·\\\'\\]:before{--tw-content:"·";content:var(--tw-content)}' +
            ".select-base{background-image:url(\"data:image/svg+xml,%3Csvg width='12' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M5 7l5 6 5-6' stroke='%2364748b'/%3E%3C/svg%3E\");background-size:12px 12px}" +
            '@keyframes ping{75%,to{opacity:0;transform:scale(2)}}@media (forced-colors:active){.outline-hidden{outline-offset:2px;outline:2px solid #0000}}';

        expect(dropUnsupportedBrowserFallbacks(built)).toBe(built);
    });

    it('says whether a stylesheet still carries a fallback', () => {
        const withFallback = '@supports (color:color-mix(in lab, red, red)){.a{color:red}}';

        expect(hasUnsupportedBrowserFallbacks(withFallback)).toBe(true);
        expect(hasUnsupportedBrowserFallbacks(dropUnsupportedBrowserFallbacks(withFallback))).toBe(false);
    });
});
