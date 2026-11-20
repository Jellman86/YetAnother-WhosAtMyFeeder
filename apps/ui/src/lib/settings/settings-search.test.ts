import { describe, expect, it } from 'vitest';
import { authoredLocale } from '../i18n/authored-locales';
import { foldForSearch, messageWords, prepareSettings, searchSettings, type SearchableSetting, type SearchOptions, type SettingMatch } from './settings-search';
import { SETTINGS_SEARCH_INDEX, settingsSearchSection, type SettingsSearchEntry } from './settings-search-index';
import type { SettingsSection } from './settings-route';

const setting = (item: string, label: string, help = '', keywords: string[] = []): SearchableSetting<string> => ({ item, label, help, keywords });
/** The matches for a query over settings given as the page gives them. */
const matches = <T>(query: string, settings: SearchableSetting<T>[], options?: SearchOptions<T>): SettingMatch<T>[] => searchSettings(query, prepareSettings(settings), options).matches;
const found = (query: string, settings: SearchableSetting<string>[]): string[] => matches(query, settings).map((match) => match.item);

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
    it('ranks a text that starts with the query first, then a word that starts with it, then one that holds it', () => {
        const settings = [setting('inside', 'Subregion model'), setting('word', 'Bird model region'), setting('start', 'Region of the feeder')];
        expect(found('region', settings)).toEqual(['start', 'word', 'inside']);
        expect(matches('region', settings).map((match) => match.closeness)).toEqual(['start', 'word', 'inside']);
    });

    it('within each of those, ranks a label match over a help match, and a help match over a keyword match', () => {
        const settings = [
            setting('keyword', 'Notification cooldown', 'Wait before the next alert.', ['quiet']),
            setting('help', 'History duration', 'Quiet feeders keep less.'),
            setting('label', 'Quiet hours', 'When no alert is sent.')
        ];
        expect(found('quiet', settings)).toEqual(['label', 'help', 'keyword']);
        expect(matches('quiet', settings).map((match) => match.field)).toEqual(['label', 'help', 'keyword']);
        // A help text where the query starts a word still outranks a label that only holds it mid-word,
        // but never a label where it starts a word: only a label can lead by starting with the query.
        expect(found('quiet', [setting('label-inside', 'Unquiet nights'), setting('help-start', 'History', 'Quiet feeders keep less.'), setting('label-word', 'Keep quiet')]))
            .toEqual(['label-word', 'help-start', 'label-inside']);
    });

    it('lists settings near the reader first among equal matches, never ahead of a closer match', () => {
        const settings = [setting('far-word', 'Show camera names'), setting('near-word', 'Sync camera list'), setting('far-start', 'Cameras to watch')];
        const near = (item: string): boolean => item.startsWith('near');
        expect(matches('camera', settings, { near }).map((match) => match.item)).toEqual(['far-start', 'near-word', 'far-word']);
        expect(found('camera', settings)).toEqual(['far-start', 'far-word', 'near-word']);
    });

    it('lists a setting before a group of settings that matches as well', () => {
        const settings = [{ ...setting('group', 'Alert cooldown and language'), group: true }, setting('single', 'Notification cooldown')];
        expect(found('cooldown', settings)).toEqual(['single', 'group']);
    });

    it('folds case and accents on both sides', () => {
        const settings = [setting('accent', 'Durée de l\u2019historique'), setting('sharp', 'Größe des Speichers')];
        expect(found('DUREE', settings)).toEqual(['accent']);
        expect(found('durée', settings)).toEqual(['accent']);
        expect(found('grosse', settings)).toEqual(['sharp']);
        expect(foldForSearch('  Größe   Événement ')).toBe('grosse evenement');
    });

    it('needs every word of the query, each found in any field, and ranks by the weakest', () => {
        const settings = [setting('both', 'Visit gap', 'Captures no more than this many seconds apart.'), setting('one', 'Visit film')];
        expect(found('visit seconds', settings)).toEqual(['both']);
        expect(matches('visit seconds', settings)[0]).toMatchObject({ field: 'help', closeness: 'word' });
        expect(found('visit nothing', settings)).toEqual([]);
        // Only a text that starts with the whole query starts with it.
        expect(matches('visit gap', settings)[0].closeness).toBe('start');
        expect(matches('gap visit', settings)[0].closeness).toBe('word');
    });

    it('returns nothing for an empty query, and no more than the limit', () => {
        const many = Array.from({ length: 20 }, (_, index) => setting(`s${index}`, `Camera ${index}`));
        expect(found('   ', many)).toEqual([]);
        expect(matches('camera', many)).toHaveLength(8);
        expect(matches('camera', many, { limit: 3 }).map((match) => match.item)).toEqual(['s0', 's1', 's2']);
    });

    it('says how many settings match, however few it returns', () => {
        const many = Array.from({ length: 25 }, (_, index) => setting(`s${index}`, `Camera ${index}`));
        const result = searchSettings('camera', prepareSettings(many));
        expect(result.matches).toHaveLength(8);
        expect(result.total).toBe(25);
        expect(searchSettings('camera 3', prepareSettings(many))).toMatchObject({ total: 1 });
        expect(searchSettings('nothing', prepareSettings(many))).toEqual({ matches: [], total: 0 });
        expect(searchSettings('  ', prepareSettings(many))).toEqual({ matches: [], total: 0 });
    });

    it('needs a word to start with a query of one or two letters, so "ai" is not found inside "maintenance"', () => {
        const settings = [setting('inside', 'Maintenance jobs', 'Detail of the email.'), setting('word', 'Use AI insights'), setting('keyword', 'Insights', '', ['ai'])];
        expect(found('ai', settings)).toEqual(['word', 'keyword']);
        expect(found('a', settings)).toEqual(['word', 'keyword']);
        // Three letters are enough to be found inside a word.
        expect(found('ain', settings)).toEqual(['inside']);
    });

    it('searches a message as words, without its placeholders or plural syntax', () => {
        expect(messageWords('Search radius ({unit})')).toBe('Search radius');
        expect(messageWords('Size [{unit}] (GB)')).toBe('Size (GB)');
        expect(messageWords('{count, plural, one {# day} other {# days}} kept')).toBe('kept');
    });
});

describe('settings search over the real index', () => {
    const anchors = (language: string, query: string, open?: SettingsSection): string[] =>
        matches(query, searchable(language), { near: open ? (entry) => settingsSearchSection(entry) === open : undefined }).map((match) => match.item.anchor);

    it('puts "Cameras to watch" first for "camera", ahead of settings that only mention a camera', () => {
        expect(anchors('en', 'camera')[0]).toBe('settings-group-cameras');
        expect(anchors('en', 'camera', 'cameras')[0]).toBe('settings-group-cameras');
        expect(anchors('en', 'camera', 'sharing')[0]).toBe('settings-group-cameras');
        const all = anchors('en', 'camera');
        expect(all.indexOf('settings-group-cameras')).toBeLessThan(all.indexOf('setting-public-show-cameras'));
    });

    it('finds the visit gap and the alert cooldown by the words an owner would type', () => {
        expect(anchors('en', 'gap')[0]).toBe('setting-visit-gap');
        expect(anchors('en', 'quiet')).toContain('notification-cooldown-label');
        expect(anchors('en', 'cooldown')).toContain('notification-cooldown-label');
        expect(anchors('en', 'gpu')).toContain('setting-inference-provider');
        expect(anchors('en', 'backup')[0]).toBe('settings-group-data-config-backup');
    });

    it('ranks German the same way: the label that starts with the query leads, and the open section breaks a tie', () => {
        const dictionary = authoredLocale('de');
        expect(message(dictionary, 'settings.public_access.show_camera_names')).toBe('Kameranamen anzeigen');
        expect(message(dictionary, 'settings.cameras.title')).toBe('Beobachtete Kameras');
        const all = anchors('de', 'kamera');
        expect(all[0]).toBe('setting-public-show-cameras');
        expect(all.indexOf('setting-public-show-cameras')).toBeLessThan(all.indexOf('settings-group-cameras'));
        // Among the labels where "kamera" only starts a word, the open section's come first.
        const words = (open: SettingsSection): string[] => matches('kamera', searchable('de'), { near: (entry) => settingsSearchSection(entry) === open, limit: 50 })
            .filter((match) => match.field === 'label' && match.closeness === 'word').map((match) => settingsSearchSection(match.item));
        expect(words('cameras')[0]).toBe('cameras');
    });

    it('counts every match for a short query in the real index, not only those returned', () => {
        const result = searchSettings('notification', prepareSettings(searchable('en')));
        expect(result.matches).toHaveLength(8);
        expect(result.total).toBeGreaterThan(8);
        // "ai" finds the AI settings, not every word with those letters in it.
        const ai = searchSettings('ai', prepareSettings(searchable('en')), { limit: 50 });
        expect(ai.total).toBe(ai.matches.length);
        expect(ai.matches.map((match) => match.item.anchor)).toContain('setting-llm-enabled');
        expect(ai.matches.map((match) => match.item.anchor)).not.toContain('settings-group-data-maintenance-jobs');
    });

    it('finds a setting by its German label, and still by an English synonym', () => {
        const german = message(dictionary('de'), 'settings.visit_gap.label');
        expect(german).not.toBe('');
        expect(anchors('de', german)[0]).toBe('setting-visit-gap');
        expect(anchors('de', german.toLocaleUpperCase('de'))[0]).toBe('setting-visit-gap');
        expect(anchors('de', 'dedupe')).toContain('setting-visit-gap');
    });
});

function dictionary(language: string): unknown {
    return authoredLocale(language);
}
