import { beforeAll, describe, expect, it } from 'vitest';
import { getMessageFormatter, init, locale } from 'svelte-i18n';
import { authoredLocale } from './authored-locales';

const de = authoredLocale('de');
const en = authoredLocale('en');
const es = authoredLocale('es');
const fr = authoredLocale('fr');
const itLocale = authoredLocale('it');
const ja = authoredLocale('ja');
const pt = authoredLocale('pt');
const ru = authoredLocale('ru');
const zh = authoredLocale('zh');

/**
 * A number followed by a fixed word reads "1 visits" in English, and in Russian "визитов" is
 * wrong for 1 to 4 and for 21 to 24. Every count that a word follows chooses that word through an
 * ICU plural, with the forms each language needs.
 */
type LocaleRoot = Record<string, unknown>;

const LOCALES: Array<[string, LocaleRoot]> = [
    ['en', en as LocaleRoot],
    ['de', de as LocaleRoot],
    ['es', es as LocaleRoot],
    ['fr', fr as LocaleRoot],
    ['it', itLocale as LocaleRoot],
    ['ja', ja as LocaleRoot],
    ['pt', pt as LocaleRoot],
    ['ru', ru as LocaleRoot],
    ['zh', zh as LocaleRoot]
];

/** The plural forms each language must spell out; `other` is the fallback ICU requires. */
const REQUIRED_FORMS: Record<string, string[]> = {
    en: ['one', 'other'],
    de: ['one', 'other'],
    es: ['one', 'other'],
    fr: ['one', 'other'],
    it: ['one', 'other'],
    pt: ['one', 'other'],
    ru: ['one', 'few', 'many', 'other'],
    ja: ['other'],
    zh: ['other']
};

/**
 * English strings where `{count}` stands before a word that does not change with the number,
 * such as "of", "more" or an abbreviated unit. Anything else is a noun and must be a plural.
 */
const COUNT_BEFORE_INVARIANT_WORD = new Set([
    'about.instance.uptime_hours',
    'about.instance.uptime_minutes',
    'dashboard.field_log.birds_none_counted',
    'dashboard.field_log.birds_unknown',
    'dashboard.field_log.preview_frame_position',
    'dashboard.review_queue.remaining',
    'events.filters.only_active',
    'events.heard.more_species',
    'events.total_count',
    'jobs.errors_export_count',
    'jobs.global_not_responding',
    'jobs.stale_hint',
    'leaderboard.check.some_selected',
    'leaderboard.includes_unidentified',
    'notifications.bell_unread',
    'notifications.global_progress_stale',
    'settings.data.archive_failed_count',
    'settings.data.archive_usage_detail',
    'settings.detection.band_needs_attention',
    'settings.detection.model_manager_count',
    'settings.detection.model_manager_show_advanced',
    'taxonomy.more',
    'taxonomy.seen_here'
]);

const COUNT_BEFORE_WORD = /\{count\}\s+[\p{L}{]/u;
/** "sighting(s)", "Tag(e)", "giorno(i)": a word that guesses at its own plural beside a placeholder. */
const BRACKETED_PLURAL = /\p{L}\((?:s|e|en|i)\)/u;

type Ast = ReturnType<ReturnType<typeof getMessageFormatter>['getAst']>;
type AstElement = Ast[number];
interface PluralUse {
    name: string;
    forms: string[];
}

function leaves(value: LocaleRoot, prefix = ''): Array<[string, string]> {
    return Object.entries(value).flatMap(([key, child]): Array<[string, string]> => {
        const path = prefix ? `${prefix}.${key}` : key;
        if (child && typeof child === 'object' && !Array.isArray(child)) return leaves(child as LocaleRoot, path);
        return typeof child === 'string' ? [[path, child]] : [];
    });
}

function pluralUses(elements: Ast): PluralUse[] {
    return elements.flatMap((element: AstElement): PluralUse[] => {
        if ('pluralType' in element && 'options' in element) {
            const options = element.options as Record<string, { value: Ast }>;
            return [
                { name: element.value, forms: Object.keys(options) },
                ...Object.values(options).flatMap((option) => pluralUses(option.value))
            ];
        }
        if ('options' in element) {
            return Object.values(element.options as Record<string, { value: Ast }>).flatMap((option) => pluralUses(option.value));
        }
        if ('children' in element) return pluralUses(element.children as Ast);
        return [];
    });
}

/** The AST does not depend on the locale, so the current one is fine. */
function plurals(message: string): PluralUse[] {
    return pluralUses(getMessageFormatter(message).getAst());
}

function format(messages: LocaleRoot, key: string, values: Record<string, number>): string {
    const message = new Map(leaves(messages)).get(key);
    if (message === undefined) throw new Error(`No message for ${key}`);
    return String(getMessageFormatter(message).format(values));
}

const sources = import.meta.glob(['../../**/*.svelte', '../../**/*.ts', '!../../**/*.test.ts'], {
    eager: true,
    query: '?raw',
    import: 'default'
}) as Record<string, string>;

beforeAll(() => {
    init({ fallbackLocale: 'en', initialLocale: 'en' });
});

describe('counted strings', () => {
    // First: svelte-i18n memoises a formatter by message alone, under the locale current when it
    // was first built, so these messages must be formatted before any other test parses them.
    it('reads one, a few and many visits correctly in English and Russian', async () => {
        await locale.set('en');
        expect(format(en as LocaleRoot, 'dashboard.top_visitors_count', { count: 1 })).toBe('1 visit');
        expect(format(en as LocaleRoot, 'dashboard.top_visitors_count', { count: 2 })).toBe('2 visits');
        await locale.set('ru');
        const russian = [1, 3, 5, 11, 21, 24, 25].map((count) => format(ru as LocaleRoot, 'dashboard.top_visitors_count', { count }));
        await locale.set('en');
        expect(russian).toEqual(['1 визит', '3 визита', '5 визитов', '11 визитов', '21 визит', '24 визита', '25 визитов']);
    });

    it('let the count choose the English word that follows it', () => {
        const fixed = leaves(en as LocaleRoot)
            .filter(([key, value]) => COUNT_BEFORE_WORD.test(value) && !COUNT_BEFORE_INVARIANT_WORD.has(key))
            .map(([key, value]) => `${key}: ${value}`);
        expect(fixed).toEqual([]);
    });

    it('never guess at a plural with brackets beside a placeholder', () => {
        for (const [localeName, messages] of LOCALES) {
            const guessed = leaves(messages)
                .filter(([, value]) => /\{\w+[},]/.test(value) && BRACKETED_PLURAL.test(value))
                .map(([key, value]) => `${localeName} ${key}: ${value}`);
            expect(guessed).toEqual([]);
        }
    });

    for (const [localeName, messages] of LOCALES) {
        it(`${localeName} spells out every plural form the language needs`, () => {
            const missing: string[] = [];
            for (const [key, value] of leaves(messages)) {
                for (const use of plurals(value)) {
                    const absent = REQUIRED_FORMS[localeName].filter((form) => !use.forms.includes(form));
                    if (absent.length) missing.push(`${key} {${use.name}} lacks ${absent.join(', ')}`);
                }
            }
            expect(missing).toEqual([]);
        });

        it(`${localeName} counts with a plural wherever English does`, () => {
            const english = new Map(leaves(en as LocaleRoot));
            const drift: string[] = [];
            for (const [key, value] of leaves(messages)) {
                const source = english.get(key);
                if (source === undefined) continue;
                const wanted = [...new Set(plurals(source).map((use) => use.name))].sort();
                const found = [...new Set(plurals(value).map((use) => use.name))].sort();
                if (wanted.join() !== found.join()) drift.push(`${key}: wants {${wanted.join(', ')}}, has {${found.join(', ')}}`);
            }
            expect(drift).toEqual([]);
        });
    }

    it('are given a number, so the plural can choose and the count is formatted once', () => {
        // A pre-formatted "1,234" reaches the plural as NaN: it picks "other" and prints "NaN".
        const english = new Map(leaves(en as LocaleRoot));
        const counted = new Set([...english].filter(([, value]) => plurals(value).length > 0).map(([key]) => key));
        const formatted: string[] = [];
        const call = /['"]([a-z]\w*(?:\.\w+)+)['"]([^;]{0,400}?)\bcount:\s*([^,}\n]+)/g;
        for (const [path, source] of Object.entries(sources)) {
            if (typeof source !== 'string' || path.includes('/i18n/locales/')) continue;
            for (const match of source.matchAll(call)) {
                // Another key between this one and `count:` means the count belongs to that call.
                if (!counted.has(match[1]) || /['"][a-z]\w*(?:\.\w+)+['"]/.test(match[2])) continue;
                if (/toLocaleString\(|String\(/.test(match[3])) formatted.push(`${match[1]} (${path.split('/').pop()})`);
            }
        }
        expect(formatted).toEqual([]);
    });
});
