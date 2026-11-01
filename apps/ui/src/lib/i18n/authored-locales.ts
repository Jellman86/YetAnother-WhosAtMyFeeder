import type { LocaleDictionary } from './locale-partition';

/**
 * Every language's dictionary, read synchronously through the same `locales/<language>.ts` modules
 * the application loads lazily, for tests that inspect whole dictionaries. The application never
 * imports this module.
 */
const LANGUAGE_MODULES = import.meta.glob<LocaleDictionary>('./locales/*.ts', {
    eager: true,
    import: 'default'
});

export function authoredLocale(language: string): LocaleDictionary {
    const dictionary = LANGUAGE_MODULES[`./locales/${language}.ts`];
    if (!dictionary) throw new Error(`No locale module for ${language}`);
    return dictionary;
}
