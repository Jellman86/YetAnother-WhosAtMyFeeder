import { describe, expect, it } from 'vitest';
import { authoredLocale } from './authored-locales';

const en = authoredLocale('en');

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
// `$_('a.b')` in a component, `get(_)('a.b')` in plain modules, and the helpers
// `t('a.b', values, fallback)`, `this.deps.t('a.b')` and `translate('a.b')`.
const LITERAL_KEY = /(?:\$_|get\(_\)|(?<![\w$])t|\.t|(?<![\w$])translate)\(\s*['"]([a-z]\w*(?:\.\w+)+)['"]/g;

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

    it('finds a key named through a helper, not only through $_()', () => {
        const found = (source: string) => [...source.matchAll(LITERAL_KEY)].map((match) => match[1]);
        expect(found("t('jobs.state_paused', undefined, 'Paused')")).toEqual(['jobs.state_paused']);
        expect(found("this.deps.t('notifications.event_backfill')")).toEqual(['notifications.event_backfill']);
        expect(found("translate('jobs.backfill_checked', { processed: 1, total: 2 })")).toEqual(['jobs.backfill_checked']);
        expect(found("get(_)('diagnostics.step_failed', { default: 'The check did not pass.' })")).toEqual(['diagnostics.step_failed']);
        expect(found("$_('nav.health', { default: 'Health' })")).toEqual(['nav.health']);
        // A call that is not a translation, and a helper whose name only ends in "t".
        expect(found("split('a.b'); format('jobs.title'); element.getAttribute('data.key')")).toEqual([]);
    });
});
