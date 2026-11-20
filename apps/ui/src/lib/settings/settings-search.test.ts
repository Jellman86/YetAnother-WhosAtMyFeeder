import { describe, expect, it } from 'vitest';
import { authoredLocale } from '../i18n/authored-locales';
import { foldForSearch, messageWords, searchSettings, type SearchableSetting } from './settings-search';
import { SETTINGS_SEARCH_INDEX, type SettingsSearchEntry } from './settings-search-index';

const setting = (item: string, label: string, help = '', keywords: string[] = []): SearchableSetting<string> => ({ item, label, help, keywords });
const found = (query: string, settings: SearchableSetting<string>[]): string[] => searchSettings(query, settings).map((match) => match.item);

function message(dictionary: unknown, key: string): string {
    let node: unknown = dictionary;
    for (const part of key.split('.')) node = node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined;
    return typeof node === 'string' ? messageWords(node) : '';
}

/** The index as the page searches it in one language: that language's words, and the English keywords. */
function searchable(language: string): SearchableSetting<SettingsSearchEntry>[] {
    const dictionary = authoredLocale(language);
    return SETTINGS_SEARCH_INDEX.map((entry) => ({
        item: entry,
        label: message(dictionary, entry.labelKey),
        help: entry.helpKey ? message(dictionary, entry.helpKey) : '',
        keywords: entry.keywords,
        group: entry.kind === 'group'
    }));
}

describe('settings search matching', () => {
    it('ranks a label match over a help match, and a help match over a keyword match', () => {
        const settings = [
            setting('keyword', 'Notification cooldown', 'Wait before the next alert.', ['quiet']),
            setting('help', 'History duration', 'A quiet feeder keeps less.'),
            setting('label', 'Quiet hours', 'When no alert is sent.')
        ];
        expect(found('quiet', settings)).toEqual(['label', 'help', 'keyword']);
        expect(searchSettings('quiet', settings).map((match) => match.field)).toEqual(['label', 'help', 'keyword']);
    });

    it('puts a label that starts with the query first, then one where it starts a word', () => {
        const settings = [setting('inside', 'Subregion model'), setting('word', 'Bird model region'), setting('start', 'Region of the feeder')];
        expect(found('region', settings)).toEqual(['start', 'word', 'inside']);
    });

    it('folds case and accents on both sides', () => {
        const settings = [setting('accent', 'Durée de l’historique'), setting('sharp', 'Größe des Speichers')];
        expect(found('DUREE', settings)).toEqual(['accent']);
        expect(found('durée', settings)).toEqual(['accent']);
        expect(found('grosse', settings)).toEqual(['sharp']);
        expect(foldForSearch('  Größe   Événement ')).toBe('grosse evenement');
    });

    it('lists a setting before a group of settings that matches as well', () => {
        const settings = [{ ...setting('group', 'Cooldown, language and link'), group: true }, setting('single', 'Notification cooldown')];
        expect(found('cooldown', settings)).toEqual(['single', 'group']);
    });

    it('needs every word of the query, each found in any field, and ranks by the weakest', () => {
        const settings = [setting('both', 'Visit gap', 'Captures no more than this many seconds apart.'), setting('one', 'Visit film')];
        expect(found('visit seconds', settings)).toEqual(['both']);
        expect(searchSettings('visit seconds', settings)[0].field).toBe('help');
        expect(found('visit nothing', settings)).toEqual([]);
    });

    it('returns nothing for an empty query, and no more than the limit', () => {
        const many = Array.from({ length: 20 }, (_, index) => setting(`s${index}`, `Camera ${index}`));
        expect(found('   ', many)).toEqual([]);
        expect(searchSettings('camera', many)).toHaveLength(8);
        expect(searchSettings('camera', many, 3).map((match) => match.item)).toEqual(['s0', 's1', 's2']);
    });

    it('searches a message as words, without its placeholders or plural syntax', () => {
        expect(messageWords('Search radius ({unit})')).toBe('Search radius ( )');
        expect(messageWords('{count, plural, one {# day} other {# days}} kept')).toBe('kept');
    });
});

describe('settings search over the real index', () => {
    const anchors = (language: string, query: string): string[] => searchSettings(query, searchable(language), 8).map((match) => match.item.anchor);

    it('finds the visit gap and the alert cooldown by the words an owner would type', () => {
        expect(anchors('en', 'gap')[0]).toBe('setting-visit-gap');
        expect(anchors('en', 'quiet')).toContain('notification-cooldown-label');
        expect(anchors('en', 'cooldown')[0]).toBe('notification-cooldown-label');
        expect(anchors('en', 'gpu')).toContain('setting-inference-provider');
        expect(anchors('en', 'backup')[0]).toBe('settings-group-data-config-backup');
    });

    it('finds a setting by its German label, and still by an English synonym', () => {
        const german = message(authoredLocale('de'), 'settings.visit_gap.label');
        expect(german).not.toBe('');
        expect(anchors('de', german)[0]).toBe('setting-visit-gap');
        expect(anchors('de', german.toLocaleUpperCase('de'))[0]).toBe('setting-visit-gap');
        expect(anchors('de', 'dedupe')).toContain('setting-visit-gap');
    });
});
