/**
 * Matching and ranking for the Settings search. Pure: the caller passes each setting's words in the
 * reader's language, so this needs no page, no store and no translation.
 */
export interface SearchableSetting<T> {
    item: T;
    label: string;
    help?: string;
    keywords?: readonly string[];
    /** A group of settings: listed after a setting that matches as well, since the setting is the closer answer. */
    group?: boolean;
}

export interface SettingMatch<T> {
    item: T;
    /** Where the weakest word of the query was found: a label match outranks help, help a keyword. */
    field: 'label' | 'help' | 'keyword';
}

/** Lower case without accents, so "Benachrichtigungssprache" and "ecran" find what a reader means. */
export function foldForSearch(text: string): string {
    return text
        .normalize('NFKD')
        .replace(/\p{M}+/gu, '')
        .replace(/ß/g, 'ss')
        .toLocaleLowerCase()
        .replace(/\s+/g, ' ')
        .trim();
}

/** A translated message as plain words: its placeholders and plural syntax are not searchable. */
export function messageWords(message: string): string {
    return message.replace(/\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}/g, ' ').replace(/\s+/g, ' ').trim();
}

const FIELD_RANK = { label: 3, help: 2, keyword: 1 } as const;
type Field = keyof typeof FIELD_RANK;

interface Folded<T> {
    source: SearchableSetting<T>;
    label: string;
    help: string;
    keywords: string;
    order: number;
}

/** Whether a word starts the text or a word within it, which reads as a closer match than mid-word. */
function startsAWord(text: string, word: string): boolean {
    let from = text.indexOf(word);
    while (from !== -1) {
        if (from === 0 || /[\s\-/(&.,:]/.test(text[from - 1])) return true;
        from = text.indexOf(word, from + 1);
    }
    return false;
}

function fieldOf<T>(setting: Folded<T>, word: string): Field | null {
    if (setting.label.includes(word)) return 'label';
    if (setting.help.includes(word)) return 'help';
    if (setting.keywords.includes(word)) return 'keyword';
    return null;
}

/**
 * The settings that hold every word of the query, best first. A setting ranks by the weakest field
 * any word was found in (label, then help, then keyword); within a rank, a setting comes before a
 * group of settings, a label that starts with the query leads, then one where a word of it starts a
 * word, then the order the settings are listed in.
 */
export function searchSettings<T>(query: string, settings: readonly SearchableSetting<T>[], limit = 8): SettingMatch<T>[] {
    const folded = foldForSearch(query);
    if (!folded) return [];
    const words = folded.split(' ');
    const scored: Array<{ match: SettingMatch<T>; rank: number; single: number; closeness: number; order: number }> = [];
    settings.forEach((source, order) => {
        const setting: Folded<T> = {
            source,
            label: foldForSearch(source.label),
            help: foldForSearch(source.help ?? ''),
            keywords: foldForSearch((source.keywords ?? []).join(' ')),
            order
        };
        let weakest: Field = 'label';
        for (const word of words) {
            const field = fieldOf(setting, word);
            if (!field) return;
            if (FIELD_RANK[field] < FIELD_RANK[weakest]) weakest = field;
        }
        const closeness = setting.label.startsWith(folded) ? 2 : words.some((word) => startsAWord(setting.label, word)) ? 1 : 0;
        scored.push({ match: { item: source.item, field: weakest }, rank: FIELD_RANK[weakest], single: source.group ? 0 : 1, closeness, order });
    });
    scored.sort((a, b) => b.rank - a.rank || b.single - a.single || b.closeness - a.closeness || a.order - b.order);
    return scored.slice(0, limit).map((entry) => entry.match);
}
