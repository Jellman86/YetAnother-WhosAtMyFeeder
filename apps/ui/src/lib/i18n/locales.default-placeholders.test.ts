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
 * name (WCAG 2.5.3). Conversely, when the English value requires a `{placeholder}` that the call
 * site never passes via `values`, every locale renders the raw `{placeholder}` token verbatim.
 */
const CALL_START = /\$_\(\s*['"]([\w.]+)['"]\s*,\s*\{/g;
const DEFAULT = /default:\s*(['"`])([\s\S]*?)(?<!\\)\1/;
const NAMED = /\{(\w+)\}/g;
const VALUE_NAMES = /\{(\w+)/g;
/** Keys whose placeholder tokens are intentionally left literal for later template splitting (e.g. `{link}`). */
const INTENTIONAL_LITERAL_PLACEHOLDER_KEYS = new Set<string>(['about.licenses.footer']);

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

/** Extract the balanced `{ ... }` options object for every `$_('key', { ... })` call. */
function extractCalls(source: string): Array<{ key: string; body: string }> {
    const results: Array<{ key: string; body: string }> = [];
    for (const match of source.matchAll(CALL_START)) {
        const key = match[1];
        const openBrace = (match.index ?? 0) + match[0].length - 1;
        let depth = 0;
        let quote: string | null = null;
        let escaped = false;
        let end = -1;
        for (let i = openBrace; i < source.length && i < openBrace + 2000; i += 1) {
            const ch = source[i];
            if (escaped) {
                escaped = false;
                continue;
            }
            if (quote) {
                if (ch === '\\') escaped = true;
                else if (ch === quote) quote = null;
                continue;
            }
            if (ch === "'" || ch === '"' || ch === '`') {
                quote = ch;
            } else if (ch === '{') {
                depth += 1;
            } else if (ch === '}') {
                depth -= 1;
                if (depth === 0) {
                    end = i;
                    break;
                }
            }
        }
        if (end > openBrace) {
            results.push({ key, body: source.slice(openBrace + 1, end) });
        }
    }
    return results;
}

describe('placeholders named in code defaults', () => {
    it('all appear in the English locale value', () => {
        const lost: string[] = [];
        for (const [path, source] of Object.entries(sources)) {
            if (typeof source !== 'string' || path.includes('/i18n/locales/')) continue;
            for (const { key, body } of extractCalls(source)) {
                const fallback = DEFAULT.exec(body);
                const value = lookup(key);
                if (!fallback || value === null) continue;
                // A template literal's `${expression}` is filled in by JavaScript, not by the locale.
                const wanted = names(fallback[2].replace(/\$\{[^}]*\}/g, ''), NAMED);
                const present = names(value, VALUE_NAMES);
                const missing = [...wanted].filter((name) => !present.has(name));
                if (missing.length) lost.push(`${key} needs {${missing.join('}, {')}} (${path.split('/').pop()})`);
            }
        }
        expect(lost.sort()).toEqual([]);
    });

    it('every call site passes values for placeholders required by the English catalog', () => {
        const rawPlaceholders: string[] = [];
        for (const [path, source] of Object.entries(sources)) {
            if (typeof source !== 'string' || path.includes('/i18n/locales/')) continue;
            for (const { key, body } of extractCalls(source)) {
                if (INTENTIONAL_LITERAL_PLACEHOLDER_KEYS.has(key)) continue;
                const value = lookup(key);
                if (value === null) continue;
                const required = names(value, VALUE_NAMES);
                if (required.size === 0) continue;
                if (!/\bvalues\b/.test(body)) {
                    rawPlaceholders.push(`${key} requires {${[...required].sort().join('}, {')}} (${path.split('/').pop()})`);
                }
            }
        }
        expect(rawPlaceholders.sort()).toEqual([]);
    });
});
