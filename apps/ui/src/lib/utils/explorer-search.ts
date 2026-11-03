import type { EventFilterSpecies } from '../api/events';
import type { ExplorerSearchRecord, ExplorerSearchResponse, ExplorerSearchTaxon } from '../api/explorer';
import type { ExplorerSubjects } from './garden-explorer';
import { toLocalYMD } from './date-only';

/**
 * The Explorer's one search box, as decisions: what a query is (an id, a date, words), which
 * results it offers in which groups, and what choosing one does to the Explorer's filters.
 *
 * The server answers what needs the species catalogue or the database (species and groups seen
 * here, a record by its id). Cameras, the species facet and dates are already known on the page,
 * so they are matched here.
 */

/** The server refuses longer queries; nothing a person types into this box comes near it. */
export const SEARCH_MAX_LENGTH = 100;
/** One letter matches most names; the catalogue is asked from two. */
const SERVER_MIN_LENGTH = 2;
const GROUP_LIMIT = 8;

const SEPARATORS = /[\s\-_.,;:'’()/]+/g;
const COMBINING_MARKS = /\p{M}/gu;
// The same shapes the server accepts: Frigate's start time and suffix, and a capture's UUID.
const FRIGATE_EVENT_ID = /^\d{9,11}\.\d{1,8}-[a-z0-9]{4,16}$/;
const GARDEN_CAPTURE_ID = /^[a-f0-9]{32}$/;

export type SearchRecordKind = 'detection' | 'garden';

/** Case, accents and separators set aside, as the server matches. */
export function normalizeSearchText(value: string): string {
    return value.normalize('NFKD').replace(COMBINING_MARKS, '').toLocaleLowerCase('en').replace(SEPARATORS, ' ').trim();
}

export function recordIdKind(value: string): SearchRecordKind | null {
    const text = value.trim();
    if (GARDEN_CAPTURE_ID.test(text)) return 'garden';
    if (FRIGATE_EVENT_ID.test(text)) return 'detection';
    return null;
}

/** The words a date may be written with: the reader's language first, then English. */
export interface DateWords {
    today: string[];
    yesterday: string[];
    /** Twelve lists of month names, full and short, January first. */
    months: string[][];
}

const ENGLISH_TODAY = 'today';
const ENGLISH_YESTERDAY = 'yesterday';

function monthNames(locale: string): string[][] {
    const names: string[][] = Array.from({ length: 12 }, () => []);
    for (const style of ['long', 'short'] as const) {
        let format: Intl.DateTimeFormat;
        try {
            format = new Intl.DateTimeFormat(locale, { month: style, timeZone: 'UTC' });
        } catch {
            continue;
        }
        for (let month = 0; month < 12; month++) {
            names[month].push(normalizeSearchText(format.format(new Date(Date.UTC(2026, month, 15)))));
        }
    }
    return names;
}

export function explorerDateWords(locale: string, words: { today: string; yesterday: string }): DateWords {
    const local = monthNames(locale);
    const english = monthNames('en');
    return {
        today: [...new Set([normalizeSearchText(words.today), ENGLISH_TODAY])],
        yesterday: [...new Set([normalizeSearchText(words.yesterday), ENGLISH_YESTERDAY])],
        // A month name with digits (Japanese "11月") is never typed as a word, so it cannot match one.
        months: local.map((names, month) => [...new Set([...names, ...english[month]])].filter((name) => /^\p{L}+$/u.test(name)))
    };
}

function calendarDay(year: number, month: number, day: number): Date | null {
    const date = new Date(year, month, day);
    return date.getFullYear() === year && date.getMonth() === month && date.getDate() === day ? date : null;
}

/** A day named without a year is its most recent occurrence: history holds nothing later. */
function latestOccurrence(month: number, day: number, now: Date): Date | null {
    const thisYear = calendarDay(now.getFullYear(), month, day);
    if (thisYear && thisYear <= now) return thisYear;
    // 29 February is looked for in the last leap year.
    for (let year = now.getFullYear() - 1; year >= now.getFullYear() - 8; year--) {
        const earlier = calendarDay(year, month, day);
        if (earlier) return earlier;
    }
    return null;
}

function monthIndex(word: string, words: DateWords): number {
    // A word of three letters or more may abbreviate a month ("sept"), but never a different one.
    const exact = words.months.findIndex((names) => names.includes(word));
    if (exact >= 0 || word.length < 3) return exact;
    const prefixed = words.months.map((names, month) => (names.some((name) => name.startsWith(word)) ? month : -1)).filter((month) => month >= 0);
    return prefixed.length === 1 ? prefixed[0] : -1;
}

/**
 * The day a query names, as YYYY-MM-DD: "today", "yesterday", "2026-11-02", "2 Nov" or
 * "November 2", optionally with a year. Numeric forms such as 2/11 are not read, because their
 * order differs between readers.
 */
export function parseSearchDate(raw: string, now: Date, words: DateWords): string | null {
    const text = normalizeSearchText(raw);
    if (!text) return null;
    if (words.today.includes(text)) return toLocalYMD(now);
    if (words.yesterday.includes(text)) {
        const yesterday = new Date(now);
        yesterday.setDate(now.getDate() - 1);
        return toLocalYMD(yesterday);
    }
    const iso = /^(\d{4}) (\d{2}) (\d{2})$/.exec(text);
    if (iso) {
        const date = calendarDay(Number(iso[1]), Number(iso[2]) - 1, Number(iso[3]));
        return date && date <= now ? toLocalYMD(date) : null;
    }
    const dayFirst = /^(\d{1,2}) (?:de )?(\p{L}+)(?: (?:de )?(\d{4}))?$/u.exec(text);
    const monthFirst = /^(\p{L}+) (\d{1,2})(?: (\d{4}))?$/u.exec(text);
    const parts = dayFirst ? { day: dayFirst[1], month: dayFirst[2], year: dayFirst[3] } : monthFirst ? { day: monthFirst[2], month: monthFirst[1], year: monthFirst[3] } : null;
    if (!parts) return null;
    const month = monthIndex(parts.month, words);
    if (month < 0) return null;
    const date = parts.year ? calendarDay(Number(parts.year), month, Number(parts.day)) : latestOccurrence(month, Number(parts.day), now);
    return date && date <= now ? toLocalYMD(date) : null;
}

export interface ExplorerQueryKinds {
    /** The query as matched: trimmed, lower case and without accents. */
    text: string;
    record: SearchRecordKind | null;
    date: string | null;
    /** Whether the server has anything to add: a record id, or words long enough to name a species. */
    askServer: boolean;
}

export function classifyExplorerQuery(raw: string, now: Date, words: DateWords): ExplorerQueryKinds {
    const trimmed = raw.trim().slice(0, SEARCH_MAX_LENGTH);
    const text = normalizeSearchText(trimmed);
    const record = recordIdKind(trimmed);
    return {
        text,
        record,
        date: record ? null : parseSearchDate(trimmed, now, words),
        askServer: record !== null || text.length >= SERVER_MIN_LENGTH
    };
}

/** A species facet entry with the names the rail shows. */
export type SearchFacetSpecies = Pick<EventFilterSpecies, 'value' | 'display_name' | 'common_name' | 'scientific_name' | 'count'> & {
    display_secondary?: string | null;
};

export type SearchOption =
    | { kind: 'record'; key: string; record: ExplorerSearchRecord }
    /** A species or group from the catalogue; `facetValue` is the species facet's own value, when it has one. */
    | { kind: 'taxon'; key: string; taxon: ExplorerSearchTaxon; facetValue: string | null }
    /** A species the facet lists that the catalogue does not place. */
    | { kind: 'species'; key: string; species: SearchFacetSpecies }
    | { kind: 'camera'; key: string; camera: string; count: number | null }
    | { kind: 'date'; key: string; day: string };

export type SearchGroupKey = 'records' | 'species' | 'cameras' | 'dates';

export interface SearchGroup {
    key: SearchGroupKey;
    options: SearchOption[];
}

function contains(name: string | null | undefined, text: string): boolean {
    return !!name && normalizeSearchText(name).includes(text);
}

/**
 * The results in their groups: the record an id names first, since pasting an id means it, then
 * species and groups, cameras and the date. Empty groups are left out.
 */
export function explorerSearchGroups(input: {
    query: ExplorerQueryKinds;
    response: ExplorerSearchResponse | null;
    facetSpecies: readonly SearchFacetSpecies[];
    cameras: readonly string[];
    cameraCounts: Record<string, number> | null;
}): SearchGroup[] {
    const { query, response, facetSpecies } = input;
    const groups: SearchGroup[] = [];
    if (response?.record) groups.push({ key: 'records', options: [{ kind: 'record', key: `record:${response.record.kind}:${response.record.id}`, record: response.record }] });
    if (query.record) return groups;

    const text = query.text;
    if (!text) return groups;
    const facetByScientific = new Map(
        facetSpecies.filter((item) => item.scientific_name).map((item) => [normalizeSearchText(item.scientific_name ?? ''), item])
    );
    const placed = new Set<string>();
    const species: SearchOption[] = (response?.taxa ?? []).map((taxon) => {
        const facet = taxon.rank === 'species' && taxon.bird_detections > 0 ? facetByScientific.get(normalizeSearchText(taxon.scientific_name)) : undefined;
        if (facet) placed.add(facet.value);
        return { kind: 'taxon', key: `taxon:${taxon.taxon_id}`, taxon, facetValue: facet?.value ?? null };
    });
    const facetMatches = facetSpecies
        .filter((item) => !placed.has(item.value))
        .filter((item) => [item.display_name, item.display_secondary, item.common_name, item.scientific_name].some((name) => contains(name, text)))
        .filter((item) => !response?.taxa.some((taxon) => normalizeSearchText(taxon.scientific_name) === normalizeSearchText(item.scientific_name ?? '')));
    for (const item of [...facetMatches].sort((a, b) => (b.count ?? 0) - (a.count ?? 0))) {
        species.push({ kind: 'species', key: `species:${item.value}`, species: item });
    }
    if (species.length) groups.push({ key: 'species', options: species.slice(0, GROUP_LIMIT) });

    const cameras = input.cameras.filter((camera) => contains(camera, text)).slice(0, GROUP_LIMIT);
    if (cameras.length) {
        groups.push({ key: 'cameras', options: cameras.map((camera) => ({ kind: 'camera', key: `camera:${camera}`, camera, count: input.cameraCounts?.[camera] ?? null })) });
    }
    if (query.date) groups.push({ key: 'dates', options: [{ kind: 'date', key: `date:${query.date}`, day: query.date }] });
    return groups;
}

/** A taxon filter as the Explorer holds it: its id for the reads, its name for the token. */
export interface TaxonChoice {
    id: number;
    rank: string;
    name: string | null;
    scientificName: string;
    /** The species the search found beneath it; unknown when a link names only the id. */
    birdSpecies?: number;
    gardenSpecies?: number;
}

/** Whether a chosen group can still match anything once the view shows these visitors. */
export function taxonAppliesTo(taxon: TaxonChoice, subjects: ExplorerSubjects): boolean {
    if (taxon.birdSpecies === undefined || taxon.gardenSpecies === undefined) return true;
    return (subjects !== 'garden' && taxon.birdSpecies > 0) || (subjects !== 'birds' && taxon.gardenSpecies > 0);
}

export type SearchChoice =
    | { kind: 'open'; record: ExplorerSearchRecord }
    | {
          kind: 'filter';
          subjects?: ExplorerSubjects;
          speciesFilter?: string;
          taxon?: TaxonChoice | null;
          cameraFilter?: string;
          datePreset?: 'today' | 'custom';
          customStartDate?: string;
          customEndDate?: string;
      };

/**
 * The visitors a choice needs: birds for a bird species, Garden animals for an animal, both when
 * the group holds both. A view that already shows what is needed is left as it is.
 */
function subjectsFor(current: ExplorerSubjects, needs: { birds: boolean; garden: boolean }, gardenAvailable: boolean): ExplorerSubjects | undefined {
    if (!gardenAvailable) return undefined;
    const shown = { birds: current !== 'garden', garden: current !== 'birds' };
    if ((!needs.birds || shown.birds) && (!needs.garden || shown.garden)) return undefined;
    return needs.birds && needs.garden ? 'all' : needs.garden ? 'garden' : 'birds';
}

/** What choosing a result does: narrow the Explorer through its existing filters, or open the record. */
export function explorerSearchChoice(
    option: SearchOption,
    context: { subjects: ExplorerSubjects; gardenAvailable: boolean; today: string }
): SearchChoice {
    switch (option.kind) {
        case 'record':
            return { kind: 'open', record: option.record };
        case 'taxon': {
            const { taxon } = option;
            const subjects = subjectsFor(context.subjects, { birds: taxon.bird_species > 0, garden: taxon.garden_species > 0 }, context.gardenAvailable);
            if (option.facetValue && taxon.garden_species === 0) {
                return { kind: 'filter', subjects, speciesFilter: option.facetValue, taxon: null };
            }
            return { kind: 'filter', subjects, speciesFilter: '', taxon: { id: taxon.taxon_id, rank: taxon.rank, name: taxon.name ?? null, scientificName: taxon.scientific_name, birdSpecies: taxon.bird_species, gardenSpecies: taxon.garden_species } };
        }
        case 'species':
            return { kind: 'filter', subjects: subjectsFor(context.subjects, { birds: true, garden: false }, context.gardenAvailable), speciesFilter: option.species.value, taxon: null };
        case 'camera':
            return { kind: 'filter', cameraFilter: option.camera };
        case 'date':
            return option.day === context.today
                ? { kind: 'filter', datePreset: 'today' }
                : { kind: 'filter', datePreset: 'custom', customStartDate: option.day, customEndDate: option.day };
    }
}
