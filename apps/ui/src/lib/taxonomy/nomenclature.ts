/**
 * How a taxon's names are written, following the zoological conventions every field guide uses:
 * the genus and the ranks beneath it are italic, the family and every rank above it are upright,
 * a genus is capitalised and an epithet is not, and a common name is never italic.
 *
 * Pure, so the lineage, the tree, the outline and the card all decide the same way.
 */

/** Ranks from the top down. A rank not listed here is shown upright and sorted last. */
const RANK_ORDER = [
    'domain',
    'kingdom',
    'subkingdom',
    'phylum',
    'subphylum',
    'infraphylum',
    'parvphylum',
    'superclass',
    'megaclass',
    'class',
    'subclass',
    'infraclass',
    'superorder',
    'order',
    'suborder',
    'infraorder',
    'parvorder',
    'superfamily',
    'family',
    'subfamily',
    'tribe',
    'subtribe',
    'genus',
    'subgenus',
    'species',
    'subspecies',
    'variety',
    'form'
];

const GENUS = RANK_ORDER.indexOf('genus');

/** Words inside a name that are not themselves names, so they stay upright. */
const CONNECTING_TERMS = new Set(['subsp.', 'ssp.', 'var.', 'f.', 'cf.', 'aff.', 'x', '×']);

export interface NamePart {
    text: string;
    italic: boolean;
}

export type NamingStyle = 'standard' | 'hobbyist' | 'scientific';

export interface TaxonName {
    kind: 'common' | 'scientific';
    /** The whole name as plain text, for an accessible name or a title. */
    text: string;
    parts: NamePart[];
}

interface NamedTaxon {
    rank: string;
    scientific_name: string;
    name?: string | null;
}

function rankIndex(rank: string): number {
    return RANK_ORDER.indexOf(rank.trim().toLowerCase());
}

export function isItalicRank(rank: string): boolean {
    return rankIndex(rank) >= GENUS;
}

/** Sorts taxa from the highest rank down; a rank this does not know keeps its place after the known ones. */
export function byRank(a: { rank: string }, b: { rank: string }): number {
    const left = rankIndex(a.rank);
    const right = rankIndex(b.rank);
    return (left < 0 ? RANK_ORDER.length : left) - (right < 0 ? RANK_ORDER.length : right);
}

function capitalise(word: string): string {
    return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
}

function writeWord(word: string, index: number): string {
    // An abbreviated genus ("P.") is already written as its author meant it.
    if (index === 0 && /^\p{L}\.$/u.test(word)) return word;
    if (index === 0) return capitalise(word);
    const subgenus = word.match(/^\((.+)\)$/);
    if (subgenus) return `(${capitalise(subgenus[1])})`;
    return word.toLowerCase();
}

/**
 * The scientific name split into its italic and upright runs. Ranks above the genus are one
 * upright, capitalised word; from the genus down, the names are italic and a connecting term
 * (subsp., var., the hybrid sign) between them stays upright.
 */
export function formatScientificName(rank: string, name: string): NamePart[] {
    const words = name.trim().split(/\s+/).filter(Boolean);
    if (words.length === 0) return [];
    if (!isItalicRank(rank)) return [{ text: words.map((word, index) => (index === 0 ? capitalise(word) : word)).join(' '), italic: false }];

    const parts: NamePart[] = [];
    words.forEach((word, index) => {
        const connecting = CONNECTING_TERMS.has(word.toLowerCase());
        const text = connecting ? word : writeWord(word, index);
        const italic = !connecting;
        const last = parts[parts.length - 1];
        if (last && last.italic === italic) last.text += ` ${text}`;
        else parts.push({ text: index === 0 ? text : ` ${text}`, italic });
    });
    return parts;
}

export function namingStyle(showCommon: boolean, preferScientific: boolean): NamingStyle {
    if (!showCommon) return 'scientific';
    return preferScientific ? 'hobbyist' : 'standard';
}

function scientificName(taxon: NamedTaxon): TaxonName {
    const parts = formatScientificName(taxon.rank, taxon.scientific_name);
    return { kind: 'scientific', text: parts.map((part) => part.text).join(''), parts };
}

function commonName(name: string): TaxonName {
    return { kind: 'common', text: name, parts: [{ text: name, italic: false }] };
}

/**
 * The name a reader sees first and the one beneath it, in the reader's naming style. A common
 * name that only repeats the scientific one is not a second name, so it is shown once.
 */
export function taxonNames(taxon: NamedTaxon, style: NamingStyle): { primary: TaxonName; secondary: TaxonName | null } {
    const scientific = scientificName(taxon);
    const common = taxon.name?.trim() || null;
    const sameName = common !== null && common.toLowerCase() === scientific.text.toLowerCase();
    if (style === 'scientific' || common === null || sameName) return { primary: scientific, secondary: null };

    const repeats = common.toLowerCase().includes(scientific.text.toLowerCase());
    if (style === 'hobbyist') return { primary: scientific, secondary: repeats ? null : commonName(common) };
    return { primary: commonName(common), secondary: repeats ? null : scientific };
}
