import { describe, expect, it } from 'vitest';

/**
 * The kit's contrast is proven once, in app.kit-contrast.test.ts. That proof only holds while
 * screens use the kit's colours, so these rules keep the classes that broke AA from coming back.
 */
const sources = import.meta.glob(['./**/*.svelte', '../App.svelte'], { query: '?raw', import: 'default', eager: true }) as Record<string, string>;

// The Settings screens still carry the older classes on their own rows and are not held to these rules.
const SETTINGS = /\/components\/settings\/|\/pages\/Settings\.svelte$/;
const FOCUS_VARIANT = '(?:focus|focus-visible|focus-within|has-focus-visible|peer-focus-visible|group-focus-visible)';

/** Each quoted run of classes: one element's classes, or one branch of a conditional. */
function classRuns(source: string): string[] {
    return source.split(/["'`]/).filter((run) => /(?:^|\s)[a-z-]+:?[a-z]+-/.test(run));
}

function offenders(test: (run: string) => boolean): string[] {
    return Object.entries(sources)
        .filter(([path]) => !SETTINGS.test(path))
        .flatMap(([path, source]) => classRuns(source).filter(test).map((run) => `${path}: ${run.trim().slice(0, 120)}`));
}

describe('focus rings outside the kit', () => {
    it('use the focus colour, never a brand step that fails 3:1 in one of the themes', () => {
        expect(offenders((run) => new RegExp(`${FOCUS_VARIANT}:ring-(?:brand|accent)-\\d`).test(run))).toEqual([]);
    });

    it('are opaque', () => {
        expect(offenders((run) => new RegExp(`${FOCUS_VARIANT}:ring-[a-z]+(?:-\\d+)?/\\d`).test(run))).toEqual([]);
    });
});

describe('muted text', () => {
    const LIGHT_INK = /(?<![\w:/-])text-slate-(?:300|400)(?![\w/-])/;
    // A run that sets a type size holds words; a bare slate-300 on an icon or a separator dot is decoration.
    const SETS_TYPE = /(?<![\w:-])text-(?:3xs|2xs|xs|sm|base|lg)\b/;

    it('is never slate-300 or slate-400 on a light ground', () => {
        // A run with a dark: text colour is a light-theme ink by definition; slate-400 on white is 2.56:1.
        expect(offenders((run) => run.includes('dark:text-') && SETS_TYPE.test(run) && LIGHT_INK.test(run))).toEqual([]);
    });

    it('is never slate-600 or darker on a dark ground', () => {
        expect(offenders((run) => /(?<![\w-])dark:text-slate-(?:600|700|800)(?![\w/-])/.test(run))).toEqual([]);
    });
});
