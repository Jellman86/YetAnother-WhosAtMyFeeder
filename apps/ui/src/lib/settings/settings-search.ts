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
    /** The weakest field any word of the query was found in. */
    field: 'label' | 'help' | 'keyword';
    /** How the query sits in that text: at its start, at the start of a word, or inside one. */
    closeness: 'start' | 'word' | 'inside';
}

export interface SearchOptions<T> {
    limit?: number;
    /** Settings the reader is nearest to (the open section), listed first among equal matches. */
    near?: (item: T) => boolean;
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
const CLOSENESS_RANK = { start: 3, word: 2, inside: 1 } as const;
type Field = keyof typeof FIELD_RANK;
type Closeness = keyof typeof CLOSENESS_RANK;

const WORD_BREAK = /[\s\-/(&.,:]/;

/** How a word sits in a text, or null when it is not there. */
function closenessIn(text: string, word: string): Closeness | null {
    let from = text.indexOf(word);
    if (from === -1) return null;
    if (from === 0) return 'start';
    while (from !== -1) {
        if (WORD_BREAK.test(text[from - 1])) return 'word';
        from = text.indexOf(word, from + 1);
    }
    return 'inside';
}

const weaker = <K extends string>(rank: Record<K, number>, a: K, b: K): K => (rank[a] <= rank[b] ? a : b);

/**
 * The settings that hold every word of the query, best first:
 * 1. how the query sits in the text: at its start, then at the start of a word, then inside one;
 * 2. where: the label, then the help, then a keyword;
 * 3. settings near the reader (the open section) before the rest;
 * 4. a setting before a group of settings, then the order the settings are listed in.
 * Each word takes its closest match, in the best field at that closeness; a setting ranks by its
 * weakest word, and only a text that starts with the whole query counts as starting with it.
 */
export function searchSettings<T>(query: string, settings: readonly SearchableSetting<T>[], options: SearchOptions<T> = {}): SettingMatch<T>[] {
    const { limit = 8, near } = options;
    const folded = foldForSearch(query);
    if (!folded) return [];
    const words = folded.split(' ');
    const scored: Array<{ match: SettingMatch<T>; near: number; single: number; order: number }> = [];
    settings.forEach((source, order) => {
        const texts: Array<[Field, string[]]> = [
            ['label', [foldForSearch(source.label)]],
            ['help', [foldForSearch(source.help ?? '')]],
            ['keyword', (source.keywords ?? []).map(foldForSearch)]
        ];
        let field: Field = 'label';
        let closeness: Closeness = 'start';
        // A text that starts with the whole query is the closest match there is, whatever its words do alone.
        const starts = texts.find(([, candidates]) => candidates.some((text) => text.startsWith(folded)));
        for (const word of starts ? [] : words) {
            let best: { field: Field; closeness: Closeness } | null = null;
            for (const [name, candidates] of texts) {
                for (const text of candidates) {
                    let found = closenessIn(text, word);
                    // One word of several at the start of a text is a word match: the query does not start it.
                    if (found === 'start' && words.length > 1 && !text.startsWith(folded)) found = 'word';
                    if (found && (!best || CLOSENESS_RANK[found] > CLOSENESS_RANK[best.closeness])) best = { field: name, closeness: found };
                }
            }
            if (!best) return;
            field = weaker(FIELD_RANK, field, best.field);
            closeness = weaker(CLOSENESS_RANK, closeness, best.closeness);
        }
        if (starts) field = starts[0];
        scored.push({ match: { item: source.item, field, closeness }, near: near?.(source.item) ? 1 : 0, single: source.group ? 0 : 1, order });
    });
    scored.sort((a, b) =>
        CLOSENESS_RANK[b.match.closeness] - CLOSENESS_RANK[a.match.closeness]
        || FIELD_RANK[b.match.field] - FIELD_RANK[a.match.field]
        || b.near - a.near
        || b.single - a.single
        || a.order - b.order
    );
    return scored.slice(0, limit).map((entry) => entry.match);
}
