import type { addMessages } from 'svelte-i18n';

/**
 * Translations are authored one file per top-level domain, `locales/<language>/<domain>.json`, so
 * features that touch different domains edit different files. The file name is the domain key,
 * which makes one domain in two files impossible. `locales/<language>.ts` joins a language's files
 * into the same dictionary the app always read, and is the only module the loader imports.
 */
export const SUPPORTED_LOCALES = ['en', 'es', 'fr', 'de', 'ja', 'zh', 'ru', 'pt', 'it'] as const;
export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];
/** svelte-i18n's own dictionary shape, which it does not export by name. */
export type LocaleDictionary = Parameters<typeof addMessages>[1];

const DOMAIN_FILE = /(?:^|\/)([a-z][a-z0-9_]*)\.json$/;

/** The dictionary whose top-level keys are the domain file names. */
export function dictionaryFromDomainFiles(files: Record<string, LocaleDictionary>): LocaleDictionary {
    return Object.fromEntries(
        Object.entries(files).map(([path, domain]) => {
            const file = DOMAIN_FILE.exec(path);
            if (!file) throw new Error(`[i18n] ${path} is not named <domain>.json`);
            return [file[1], domain];
        })
    );
}
