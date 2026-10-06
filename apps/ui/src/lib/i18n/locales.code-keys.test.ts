import { describe, expect, it } from 'vitest';
import en from './locales/en.json';

const sources = import.meta.glob(['../../**/*.svelte', '../../**/*.ts', '!../../**/*.test.ts'], {
    eager: true,
    query: '?raw',
    import: 'default'
}) as Record<string, string>;

/**
 * A key the code uses but no locale file defines renders its English `default`
 * in every language, and the locale audit cannot see it because the files still
 * agree with each other. 120 such keys, most of the first-run setup wizard and
 * the connection test dialogs, went untranslated this way.
 */
const LITERAL_KEY = /\$_\(\s*['"]([a-z]\w*(?:\.\w+)+)['"]/g;

function defined(root: unknown, key: string): boolean {
    let node = root;
    for (const part of key.split('.')) {
        if (typeof node !== 'object' || node === null || !(part in node)) return false;
        node = (node as Record<string, unknown>)[part];
    }
    return true;
}

describe('locale keys used in code', () => {
    it('are all defined in the English locale', () => {
        const missing = new Set<string>();
        for (const [path, source] of Object.entries(sources)) {
            if (typeof source !== 'string' || path.includes('/i18n/locales/')) continue;
            for (const match of source.matchAll(LITERAL_KEY)) {
                if (!defined(en, match[1])) missing.add(`${match[1]} (${path.split('/').pop()})`);
            }
        }
        expect([...missing].sort()).toEqual([]);
    });
});
