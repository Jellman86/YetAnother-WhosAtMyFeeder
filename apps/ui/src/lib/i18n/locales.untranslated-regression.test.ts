import { describe, expect, it } from 'vitest';
import { authoredLocale } from './authored-locales';
import baseline from './locales.identical-baseline.json';

const de = authoredLocale('de');
const en = authoredLocale('en');
const es = authoredLocale('es');
const fr = authoredLocale('fr');
const itLocale = authoredLocale('it');
const ja = authoredLocale('ja');
const pt = authoredLocale('pt');
const ru = authoredLocale('ru');
const zh = authoredLocale('zh');

// Ratchet guard against silent translation rot. The structural audit
// (`locales.audit.test.ts`) already enforces key parity and placeholder
// preservation; this test catches the other failure mode: a *new* user-facing
// string that lands in a locale still byte-identical to English (the classic
// "copied English verbatim" regression). Every string currently identical to
// English is captured in `locales.identical-baseline.json` — legitimately shared
// values (brand names, URL/host placeholders, cross-language cognates like the
// French "Notifications"/"Latitude"). Anything newly identical fails here until
// it is translated, or, if it is a genuine cognate/brand, added to the baseline
// in the same change so the decision is explicit and reviewable.

type LocaleRoot = Record<string, unknown>;

function leaves(value: LocaleRoot, prefix = ''): Array<[string, unknown]> {
    return Object.entries(value).flatMap(([key, child]) => {
        const path = prefix ? `${prefix}.${key}` : key;
        if (child && typeof child === 'object' && !Array.isArray(child)) {
            return leaves(child as LocaleRoot, path);
        }
        return [[path, child]];
    });
}

// A string worth translating: has letters, is more than a token long, and is not
// a URL/host/placeholder that must stay identical. Kept in lock-step with the
// generator for `locales.identical-baseline.json`.
const URLISH = /https?:\/\/|\/api\/|:\d{2,5}\b|@|\.(com|org|net|gmail|example)\b|placeholder/i;
const HAS_LETTER = /[A-Za-zÀ-ÿ]/;
function isTranslatable(value: string): boolean {
    const trimmed = value.trim();
    return trimmed.length > 3 && HAS_LETTER.test(trimmed) && !URLISH.test(trimmed);
}

const englishLeaves = new Map(leaves(en as LocaleRoot));

// Keys in `locale` whose string value equals English, is worth translating, and
// is not already accepted in `allowed`.
function newIdenticalKeys(locale: LocaleRoot, allowed: Set<string>): string[] {
    return leaves(locale)
        .filter(([key, value]) => {
            const englishValue = englishLeaves.get(key);
            return (
                typeof value === 'string' &&
                typeof englishValue === 'string' &&
                value === englishValue &&
                isTranslatable(value) &&
                !allowed.has(key)
            );
        })
        .map(([key]) => key)
        .sort();
}

const LOCALES: Array<[string, LocaleRoot]> = [
    ['de', de as LocaleRoot],
    ['es', es as LocaleRoot],
    ['fr', fr as LocaleRoot],
    ['it', itLocale as LocaleRoot],
    ['ja', ja as LocaleRoot],
    ['pt', pt as LocaleRoot],
    ['ru', ru as LocaleRoot],
    ['zh', zh as LocaleRoot]
];

describe('no untranslated-string regressions', () => {
    for (const [name, locale] of LOCALES) {
        it(`${name} introduces no new strings identical to English`, () => {
            const allowed = new Set((baseline as Record<string, string[]>)[name] ?? []);
            expect(
                newIdenticalKeys(locale, allowed),
                'these strings are identical to English — translate them, or add the key to ' +
                    `locales.identical-baseline.json ("${name}") if the value is a genuine brand/cognate`
            ).toEqual([]);
        });
    }

    it('flags a new untranslated string that is not in the baseline', () => {
        // A key that carries a real English sentence; copying it verbatim into a
        // locale (outside the baseline) must be caught.
        const [probeKey, probeValue] =
            [...englishLeaves].find(
                ([, value]) => typeof value === 'string' && isTranslatable(value) && value.trim().includes(' ')
            ) ?? [];
        expect(probeKey, 'expected at least one translatable English sentence to probe with').toBeTruthy();

        const syntheticLocale = { [probeKey as string]: probeValue } as LocaleRoot;
        expect(newIdenticalKeys(syntheticLocale, new Set())).toContain(probeKey);
        // ...and it stays silent once the key is accepted in the baseline.
        expect(newIdenticalKeys(syntheticLocale, new Set([probeKey as string]))).toEqual([]);
    });
});
