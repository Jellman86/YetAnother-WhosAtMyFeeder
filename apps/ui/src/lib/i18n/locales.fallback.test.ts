import { beforeAll, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { _, dictionary } from 'svelte-i18n';

import { authoredLocale } from './authored-locales';
import { i18nReady, setAppLocale } from './index';

/**
 * A translation can lag behind English, or fail to load one of its files. The application's own
 * loader must still show the English string for a key the selected language lacks, never the raw
 * key. Every translation here is loaded through the real lazy loader with `nav.settings` removed
 * from its authored file.
 */
const { withoutSettingsEntry } = vi.hoisted(() => ({
    withoutSettingsEntry: async (load: () => Promise<{ default: Record<string, unknown> }>) => {
        const { settings: _removed, ...rest } = (await load()).default;
        return { default: rest };
    }
}));

vi.mock('./locales/de/nav.json', (original) => withoutSettingsEntry(original));
vi.mock('./locales/es/nav.json', (original) => withoutSettingsEntry(original));
vi.mock('./locales/fr/nav.json', (original) => withoutSettingsEntry(original));
vi.mock('./locales/it/nav.json', (original) => withoutSettingsEntry(original));
vi.mock('./locales/ja/nav.json', (original) => withoutSettingsEntry(original));
vi.mock('./locales/pt/nav.json', (original) => withoutSettingsEntry(original));
vi.mock('./locales/ru/nav.json', (original) => withoutSettingsEntry(original));
vi.mock('./locales/zh/nav.json', (original) => withoutSettingsEntry(original));

const TRANSLATIONS = ['de', 'es', 'fr', 'it', 'ja', 'pt', 'ru', 'zh'] as const;

function navigation(language: string): Record<string, string> {
    return authoredLocale(language).nav as Record<string, string>;
}

beforeAll(async () => {
    await i18nReady;
});

describe('English fallback for keys a translation lacks', () => {
    it('loads exactly the authored English dictionary', async () => {
        expect(await setAppLocale('en')).toBe(true);
        expect(get(dictionary).en).toEqual(authoredLocale('en'));
    });

    for (const language of TRANSLATIONS) {
        it(`${language} renders a missing key in English, not as the raw key`, async () => {
            expect(await setAppLocale(language)).toBe(true);
            const format = get(_);

            expect(format('nav.settings')).toBe(navigation('en').settings);
            expect(format('nav.settings')).not.toBe('nav.settings');
            // The translation itself is active: a key it does carry is not English.
            expect(navigation(language).about).not.toBe(navigation('en').about);
            expect(format('nav.about')).toBe(navigation(language).about);
        });

        it(`${language} loads every other authored key unchanged`, async () => {
            expect(await setAppLocale(language)).toBe(true);
            const { nav, ...otherDomains } = authoredLocale(language);
            const { settings: _removed, ...navWithoutSettings } = nav as Record<string, unknown>;

            expect(get(dictionary)[language]).toEqual({ ...otherDomains, nav: navWithoutSettings });
        });
    }
});
