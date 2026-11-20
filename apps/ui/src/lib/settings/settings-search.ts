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
    /** How many matches to return; the total still counts them all. */
    limit?: number;
    /** Settings the reader is nearest to (the open section), listed first among equal matches. */
    near?: (item: T) => boolean;
}

export interface SearchResult<T> {
    /** The best matches, at most `limit` of them. */
    matches: SettingMatch<T>[];
    /** How many settings match in all, so a reader is never told fewer exist than do. */
    total: number;
}

/** A setting with its words folded once, ready to be searched on every keystroke. */
export interface PreparedSetting<T> {
    item: T;
    group: boolean;
    order: number;
    texts: ReadonlyArray<readonly [field: 'label' | 'help' | 'keyword', candidates: readonly string[]]>;
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
    return message
        .replace(/\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}/g, ' ')
        // Brackets left holding nothing once a placeholder is gone.
        .replace(/[([]\s*[)\]]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
}

/** Folds each setting's words once; the result is what `searchSettings` searches. */
export function prepareSettings<T>(settings: readonly SearchableSetting<T>[]): PreparedSetting<T>[] {
    return settings.map((source, order) => ({
        item: source.item,
        group: source.group === true,
        order,
        texts: [
            ['label', [foldForSearch(source.label)]],
            ['help', [foldForSearch(source.help ?? '')]],
            ['keyword', (source.keywords ?? []).map(foldForSearch)]
        ]
    }));
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

/** Shorter than this, a word of the query must start a word: "ai" is not found inside "maintenance". */
const MIN_LENGTH_INSIDE_A_WORD = 3;

/**
 * The settings that hold every word of the query, best first, and how many there are in all:
 * 1. how the query sits in the text: a label that starts with it, then a word that starts with it
 *    (a help line or keyword that starts with it counts as this), then a word that holds it;
 * 2. where: the label, then the help, then a keyword;
 * 3. settings near the reader (the open section) before the rest;
 * 4. a setting before a group of settings, then the order the settings are listed in.
 * Each word takes its closest match, in the best field at that closeness; a setting ranks by its
 * weakest word, and only a label that starts with the whole query counts as starting with it.
 */
export function searchSettings<T>(query: string, settings: readonly PreparedSetting<T>[], options: SearchOptions<T> = {}): SearchResult<T> {
    const { limit = 8, near } = options;
    const folded = foldForSearch(query);
    if (!folded) return { matches: [], total: 0 };
    const words = folded.split(' ');
    const scored: Array<{ match: SettingMatch<T>; near: number; single: number; order: number }> = [];
    for (const setting of settings) {
        let field: Field = 'label';
        let closeness: Closeness = 'start';
        let held = true;
        // A label that starts with the whole query is the closest match there is, whatever its words do alone.
        const starts = setting.texts[0][1][0].startsWith(folded);
        for (const word of starts ? [] : words) {
            let best: { field: Field; closeness: Closeness } | null = null;
            for (const [name, candidates] of setting.texts) {
                for (const text of candidates) {
                    let found = closenessIn(text, word);
                    if (found === 'inside' && word.length < MIN_LENGTH_INSIDE_A_WORD) found = null;
                    // Starting the text leads only for a label, and only for the whole query: a help
                    // line or a keyword that starts with it, or one word of several, is a word match.
                    if (found === 'start' && (name !== 'label' || words.length > 1)) found = 'word';
                    if (found && (!best || CLOSENESS_RANK[found] > CLOSENESS_RANK[best.closeness])) best = { field: name, closeness: found };
                }
            }
            if (!best) {
                held = false;
                break;
            }
            field = weaker(FIELD_RANK, field, best.field);
            closeness = weaker(CLOSENESS_RANK, closeness, best.closeness);
        }
        if (!held) continue;
        scored.push({ match: { item: setting.item, field, closeness }, near: near?.(setting.item) ? 1 : 0, single: setting.group ? 0 : 1, order: setting.order });
    }
    scored.sort((a, b) =>
        CLOSENESS_RANK[b.match.closeness] - CLOSENESS_RANK[a.match.closeness]
        || FIELD_RANK[b.match.field] - FIELD_RANK[a.match.field]
        || b.near - a.near
        || b.single - a.single
        || a.order - b.order
    );
    return { matches: scored.slice(0, limit).map((entry) => entry.match), total: scored.length };
}
