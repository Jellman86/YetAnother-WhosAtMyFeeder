import type { LeaderboardPortrait, LeaderboardSpan } from '../api';
import type { SourceMode } from './source-metrics';
import { activityTimestampForMode, countForMode, deltaForMode, trendForMode } from './source-metrics';

/** One species in the leaderboard's showcase: what it is, how it stands, and what to show for it. */
export interface ShowcaseRow {
    key: string;
    displayName: string;
    subName: string | null;
    count: number;
    /** The trend as the table prints it; null for the all-time span, which has no previous window. */
    trend: string | null;
    delta: number | null;
    avgConfidence: number | null;
    lastSeen: string | null;
    /** This feeder's own crop, a path served by the About reel's image route. */
    photo: string | null;
    /** The species' reference image from the taxonomy cache, and where it came from. */
    reference: string | null;
    referenceSource: string | null;
}

/** The subset of a leaderboard table row the showcase needs. */
export interface ShowcaseSource {
    species: string;
    scientific_name?: string | null;
    taxa_id?: number | null;
    displayName: string;
    subName: string | null;
    avg_confidence?: number | null;
}

export interface ReferenceImage {
    url: string | null;
    source: string | null;
}

/** How many species stand beside the leader as tiles. */
export const SHOWCASE_TILES = 8;

/**
 * Match a species' own photograph to its row. The taxon is the identity when both sides
 * carry one; otherwise the names, which the leaderboard writes the same way on both routes.
 */
export function portraitFor(row: ShowcaseSource, portraits: LeaderboardPortrait[]): string | null {
    const byTaxon = row.taxa_id ? portraits.find((portrait) => portrait.taxa_id === row.taxa_id) : undefined;
    if (byTaxon) return byTaxon.image_url;
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
    return byName?.image_url ?? null;
}

export function buildShowcaseRows<T extends ShowcaseSource>(
    rows: T[],
    options: {
        span: LeaderboardSpan;
        sourceMode: SourceMode;
        portraits: LeaderboardPortrait[];
        referenceFor: (species: string) => ReferenceImage;
        limit?: number;
    }
): ShowcaseRow[] {
    const limit = options.limit ?? SHOWCASE_TILES + 1;
    return rows.slice(0, limit).map((row) => {
        const reference = options.referenceFor(row.species);
        const metricRow = row as unknown as Parameters<typeof countForMode>[0];
        return {
            key: row.species,
            displayName: row.displayName,
            subName: row.subName,
            count: countForMode(metricRow, options.sourceMode),
            trend: options.span === 'all' ? null : trendForMode(metricRow, options.sourceMode),
            delta: options.span === 'all' ? null : (deltaForMode(metricRow, options.sourceMode) ?? null),
            avgConfidence: row.avg_confidence ?? null,
            lastSeen: activityTimestampForMode(metricRow, options.sourceMode) ?? null,
            photo: portraitFor(row, options.portraits),
            reference: reference.url,
            referenceSource: reference.source
        };
    });
}

/**
 * The display order after one species is brought forward: it takes the leader's place and the
 * leader takes the slot it vacated, so nothing else in the grid moves. An order that no longer
 * describes the rows (a new window) is discarded by the caller, never patched.
 */
export function swapDisplayOrder(order: readonly string[], expanded: string, chosen: string): string[] {
    const next = [...order];
    const from = next.indexOf(expanded);
    const to = next.indexOf(chosen);
    if (from === -1 || to === -1 || from === to) return next;
    next[from] = chosen;
    next[to] = expanded;
    return next;
}
