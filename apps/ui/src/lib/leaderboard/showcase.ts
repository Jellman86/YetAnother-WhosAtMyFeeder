import type { LeaderboardPortrait } from '../api';
import type { SourceMode } from './source-metrics';
import { countForMode } from './source-metrics';

/** One species at the top of the leaderboard: what it is, how it stands, and what to show for it. */
export interface ShowcaseRow {
    key: string;
    /** Its place in the rankings table, so the reel and the table never disagree. */
    rank: number;
    displayName: string;
    subName: string | null;
    count: number;
    /** This feeder's own crop, a path served by the reel's image route. */
    photo: string | null;
    /** The visit that crop is from, and whether a film of it is ready. */
    photoEvent: string | null;
    film: boolean;
    /** The species' reference image from the taxonomy cache, and where it came from. */
    reference: string | null;
    referenceSource: string | null;
    /** Probably a misidentification: only the camera backs it and nobody reported it nearby. */
    flagged: boolean;
}

/** The subset of a leaderboard table row the showcase needs. */
export interface ShowcaseSource {
    species: string;
    scientific_name?: string | null;
    taxa_id?: number | null;
    displayName: string;
    subName: string | null;
}

export interface ReferenceImage {
    url: string | null;
    source: string | null;
}

/** How many species the share bar names before it sums the rest. */
const SPOTLIGHT_LIST = 6;

/** Ranked species to ask a photograph for: the list plus the flagged species shown beneath it. */
export const SPOTLIGHT_PORTRAITS = 16;

/**
 * Match a species' own photograph to its row. The taxon is the identity when both sides
 * carry one; otherwise the names, which the leaderboard writes the same way on both routes.
 */
export function portraitFor(row: ShowcaseSource, portraits: LeaderboardPortrait[]): LeaderboardPortrait | null {
    const byTaxon = row.taxa_id ? portraits.find((portrait) => portrait.taxa_id === row.taxa_id) : undefined;
    if (byTaxon) return byTaxon;
    const names = new Set(
        [row.species, row.scientific_name, row.displayName, row.subName]
            .filter((name): name is string => typeof name === 'string' && name.trim() !== '')
            .map((name) => name.trim().toLowerCase())
    );
    const byName = portraits.find(
        (portrait) =>
            names.has(portrait.species.trim().toLowerCase()) ||
            (portrait.scientific_name ? names.has(portrait.scientific_name.trim().toLowerCase()) : false)
    );
    return byName ?? null;
}

/** One card in the leaderboard's reel: a visit's photograph, and its film once one is made. */
export interface ReelCard {
    key: string;
    frigateEvent: string;
    title: string;
    detail: string;
    badge: string;
    film: boolean;
    /** What a click does, for readers: the card's whole name. */
    label: string;
}

/** Fewer photographs than this make a strip that reads as a gap, not a reel. */
export const REEL_MINIMUM = 4;

/**
 * The reel's cards: every ranked species with a photograph of its own, in rank order. A
 * flagged species (probably a misidentification) is never put on show.
 */
export function reelCards(
    rows: ShowcaseRow[],
    text: { detail: (row: ShowcaseRow) => string; badge: (row: ShowcaseRow) => string; label: (row: ShowcaseRow) => string }
): ReelCard[] {
    const cards = rows
        .filter((row): row is ShowcaseRow & { photoEvent: string } => !row.flagged && row.photoEvent !== null)
        .map((row) => ({
            key: row.key,
            frigateEvent: row.photoEvent,
            title: row.displayName,
            detail: text.detail(row),
            badge: text.badge(row),
            film: row.film,
            label: text.label(row)
        }));
    return cards.length >= REEL_MINIMUM ? cards : [];
}

export function buildShowcaseRows<T extends ShowcaseSource>(
    rows: T[],
    options: {
        sourceMode: SourceMode;
        portraits: LeaderboardPortrait[];
        referenceFor: (species: string) => ReferenceImage;
        isFlagged?: (row: T) => boolean;
        limit?: number;
    }
): ShowcaseRow[] {
    const limit = options.limit ?? rows.length;
    return rows.slice(0, limit).map((row, index) => {
        const reference = options.referenceFor(row.species);
        const portrait = portraitFor(row, options.portraits);
        const metricRow = row as unknown as Parameters<typeof countForMode>[0];
        return {
            key: row.species,
            rank: index + 1,
            displayName: row.displayName,
            subName: row.subName,
            count: countForMode(metricRow, options.sourceMode),
            photo: portrait?.image_url ?? null,
            photoEvent: portrait?.frigate_event ?? null,
            film: Boolean(portrait?.film_url),
            reference: reference.url,
            referenceSource: reference.source,
            flagged: options.isFlagged?.(row) ?? false
        };
    });
}

/**
 * The ranked rows split the way the spotlight shows them. Flagged species (probably
 * misidentifications) never take a place in the tour or the list; they are named apart so
 * they can be checked. Every other species past the list is summed, not dropped.
 */
export function spotlightGroups(rows: ShowcaseRow[], listSize = SPOTLIGHT_LIST) {
    const trusted = rows.filter((row) => !row.flagged);
    const list = trusted.slice(0, listSize);
    const others = trusted.slice(listSize);
    return {
        list,
        others: { species: others.length, count: others.reduce((sum, row) => sum + row.count, 0) },
        checks: rows.filter((row) => row.flagged)
    };
}

export interface ShareSegment {
    key: string;
    kind: 'species' | 'others' | 'checks';
    count: number;
    percent: number;
}

/**
 * The share bar: one segment per listed species, then everyone else, then the species that
 * need a check. Percentages are of every ranked count, so the segments fill the bar exactly
 * and nothing is quietly left out.
 */
export function shareSegments(rows: ShowcaseRow[], listSize = SPOTLIGHT_LIST): ShareSegment[] {
    const total = rows.reduce((sum, row) => sum + row.count, 0);
    if (total <= 0) return [];
    const { list, others, checks } = spotlightGroups(rows, listSize);
    const share = (count: number) => (count / total) * 100;
    const segments: ShareSegment[] = list.map((row) => ({
        key: row.key,
        kind: 'species',
        count: row.count,
        percent: share(row.count)
    }));
    if (others.count > 0) segments.push({ key: 'others', kind: 'others', count: others.count, percent: share(others.count) });
    const checkCount = checks.reduce((sum, row) => sum + row.count, 0);
    if (checkCount > 0) segments.push({ key: 'checks', kind: 'checks', count: checkCount, percent: share(checkCount) });
    return segments;
}
