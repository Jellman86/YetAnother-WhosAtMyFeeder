import type { TaxonFacts, TaxonOtherName, TaxonPhoto } from '../api/taxonomy';

/**
 * What the family tree says about each taxon at this install, decided without the DOM: which
 * taxa still need asking about, what a card states about visits, calls and photographs, and how
 * the scientific detail is written. Every fact has its own loading, absent and failed state, and
 * a fact that is not known is hidden rather than guessed.
 */

/** One taxon's facts as a surface holds them. `absent`: the catalogue does not hold the taxon. */
export type FactEntry =
    | { state: 'loading' }
    | { state: 'ready'; facts: TaxonFacts }
    | { state: 'absent' }
    | { state: 'failed' };

/** The most taxa one facts request may name, as the route accepts. */
const FACTS_BATCH_LIMIT = 100;

/** The taxa worth asking about, each once and in batches the route accepts. */
export function factsBatches(
    ids: Iterable<number>,
    entries: ReadonlyMap<number, FactEntry>,
    { limit = FACTS_BATCH_LIMIT, retryFailed = false }: { limit?: number; retryFailed?: boolean } = {}
): number[][] {
    const wanted = [...new Set(ids)].filter((id) => {
        const entry = entries.get(id);
        return entry === undefined || (retryFailed && entry.state === 'failed');
    });
    const batches: number[][] = [];
    for (let start = 0; start < wanted.length; start += limit) batches.push(wanted.slice(start, start + limit));
    return batches;
}

export type VisitsView =
    | { kind: 'loading' }
    | { kind: 'failed' }
    /** The catalogue does not hold the taxon: nothing is claimed either way. */
    | { kind: 'unknown' }
    | { kind: 'none' }
    | {
          kind: 'seen';
          visits: number;
          speciesSeen: number;
          firstSeen: string;
          lastSeen: string;
          /** First and last seen fall on one day, so the card states one date. */
          sameDay: boolean;
      };

export function visitsView(entry: FactEntry | undefined, sameDay: (first: string, last: string) => boolean): VisitsView {
    if (entry === undefined || entry.state === 'loading') return { kind: 'loading' };
    if (entry.state === 'failed') return { kind: 'failed' };
    if (entry.state === 'absent') return { kind: 'unknown' };
    const { visits, species_seen, first_seen, last_seen } = entry.facts;
    if (visits <= 0 || !first_seen || !last_seen) return { kind: 'none' };
    return {
        kind: 'seen',
        visits,
        speciesSeen: species_seen,
        firstSeen: first_seen,
        lastSeen: last_seen,
        sameDay: sameDay(first_seen, last_seen)
    };
}

/** BirdNET calls to badge, or null: none recorded, audio not shared, or not known yet. */
export function heardCount(entry: FactEntry | undefined): number | null {
    if (entry?.state !== 'ready') return null;
    const heard = entry.facts.heard;
    return heard !== null && heard !== undefined && heard > 0 ? heard : null;
}

/** This install's own photograph, once the facts say there is one the reader may load. */
export function ownPhoto(entry: FactEntry | undefined): TaxonPhoto | null {
    return entry?.state === 'ready' ? (entry.facts.photo ?? null) : null;
}

/** Whether two instants fall on the same day where the reader is. */
export function sameLocalDay(first: string, last: string): boolean {
    const a = new Date(first);
    const b = new Date(last);
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/**
 * An authority as the catalogue stores it. Under the zoological code parentheses mean the species
 * has moved genus since it was described; only the source knows that, so none are added here.
 */
export function authorityText(authorship: string | null | undefined): string | null {
    const text = (authorship ?? '').split(/\s+/).filter(Boolean).join(' ');
    return text || null;
}

export interface NameGroup {
    language: string;
    label: string;
    names: string[];
}

/** A language named in the reader's own language, as the browser knows it; its tag otherwise. */
export function languageLabel(tag: string, locale: string): string {
    try {
        const label = new Intl.DisplayNames([locale], { type: 'language', fallback: 'none' }).of(tag);
        return label ? label.charAt(0).toLocaleUpperCase(locale) + label.slice(1) : tag;
    } catch {
        return tag;
    }
}

/** Names by language, languages in the order of their labels, each keeping the route's preferred-first order. */
export function groupOtherNames(names: readonly TaxonOtherName[], labelFor: (tag: string) => string): NameGroup[] {
    const groups = new Map<string, NameGroup>();
    for (const { language, name } of names) {
        const group = groups.get(language) ?? { language, label: labelFor(language), names: [] };
        group.names.push(name);
        groups.set(language, group);
    }
    return [...groups.values()].sort((a, b) => a.label.localeCompare(b.label));
}

const IUCN_CATEGORIES = ['DD', 'LC', 'NT', 'VU', 'EN', 'CR', 'EW', 'EX'] as const;
export type IucnCategory = (typeof IUCN_CATEGORIES)[number];

export function iucnCategory(code: string | null | undefined): IucnCategory | null {
    const value = (code ?? '').trim().toUpperCase();
    return (IUCN_CATEGORIES as readonly string[]).includes(value) ? (value as IucnCategory) : null;
}
