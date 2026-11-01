import { describe, expect, it } from 'vitest';
import { authoredLocale } from './authored-locales';

const en = authoredLocale('en');

const sources = import.meta.glob(['../../**/*.svelte', '../../**/*.ts', '!../../**/*.test.ts'], {
    eager: true,
    query: '?raw',
    import: 'default'
}) as Record<string, string>;

/**
 * The English `default` is what the author meant; the locale value is what ships. When the default
 * names a `{placeholder}` the English value lacks, the value passed in is silently dropped. The
 * Active Cameras buttons were all announced as "Select" and "Preview" this way, with no camera
 * name (WCAG 2.5.3).
 */
const CALL = /\$_\(\s*['"]([\w.]+)['"]\s*,\s*\{([\s\S]{0,600}?)\}\s*\)/g;
const DEFAULT = /default:\s*(['"`])([\s\S]*?)(?<!\\)\1/;
const NAMED = /\{(\w+)\}/g;
const VALUE_NAMES = /\{(\w+)/g;

function lookup(key: string): string | null {
    let node: unknown = en;
    for (const part of key.split('.')) {
        if (typeof node !== 'object' || node === null || !(part in node)) return null;
        node = (node as Record<string, unknown>)[part];
    }
    return typeof node === 'string' ? node : null;
}

function names(text: string, pattern: RegExp): Set<string> {
    return new Set([...text.matchAll(pattern)].map((match) => match[1]));
}

describe('placeholders named in code defaults', () => {
    it('all appear in the English locale value', () => {
        const lost: string[] = [];
        for (const [path, source] of Object.entries(sources)) {
            if (typeof source !== 'string' || path.includes('/i18n/locales/')) continue;
            for (const call of source.matchAll(CALL)) {
                const fallback = DEFAULT.exec(call[2]);
                const value = lookup(call[1]);
                if (!fallback || value === null) continue;
                // A template literal's `${expression}` is filled in by JavaScript, not by the locale.
                const wanted = names(fallback[2].replace(/\$\{[^}]*\}/g, ''), NAMED);
                const present = names(value, VALUE_NAMES);
                const missing = [...wanted].filter((name) => !present.has(name));
                if (missing.length) lost.push(`${call[1]} needs {${missing.join('}, {')}} (${path.split('/').pop()})`);
            }
        }
        expect(lost.sort()).toEqual([]);
    });
});
