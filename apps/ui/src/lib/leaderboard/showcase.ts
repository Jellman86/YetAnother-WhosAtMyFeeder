import type { LeaderboardPortrait } from '../api';
import type { SourceMode } from './source-metrics';
import { activityTimestampForMode, countForMode, deltaForMode, trendForMode } from './source-metrics';

/** One species in the leaderboard's showcase: what it is, how it stands, and what to show for it. */
export interface ShowcaseRow {
    key: string;
    /** Its place in the rankings table, so the spotlight and the table never disagree. */
    rank: number;
    /** Every name the species goes by on the timeline's per-species series. */
    names: string[];
    displayName: string;
    subName: string | null;
    count: number;
    /** The trend as the table prints it; null when there is no fully recorded earlier window to compare with. */
    trend: string | null;
    delta: number | null;
    avgConfidence: number | null;
    lastSeen: string | null;
    /** This feeder's own crop, a path served by the About reel's image route. */
    photo: string | null;
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
    avg_confidence?: number | null;
}

export interface ReferenceImage {
    url: string | null;
    source: string | null;
}

/** How many species the spotlight tours and lists beside it. */
export const SPOTLIGHT_LIST = 6;

/** Ranked species to ask a photograph for: the list plus the flagged species shown beneath it. */
export const SPOTLIGHT_PORTRAITS = 16;

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
        /** False for the all-time span, and for a window whose predecessor began before the history did. */
        trendAvailable: boolean;
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
        const metricRow = row as unknown as Parameters<typeof countForMode>[0];
        return {
            key: row.species,
            rank: index + 1,
            names: [row.species, row.scientific_name].filter(
                (name): name is string => typeof name === 'string' && name.trim() !== ''
            ),
            displayName: row.displayName,
            subName: row.subName,
            count: countForMode(metricRow, options.sourceMode),
            trend: options.trendAvailable ? trendForMode(metricRow, options.sourceMode) : null,
            delta: options.trendAvailable ? (deltaForMode(metricRow, options.sourceMode) ?? null) : null,
            avgConfidence: row.avg_confidence ?? null,
            lastSeen: activityTimestampForMode(metricRow, options.sourceMode) ?? null,
            photo: portraitFor(row, options.portraits),
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

type PresenceBucket = 'hour' | 'day' | 'month';

export interface Presence {
    /** One cell per timeline bucket, oldest first: was the species on camera in it at all. */
    present: boolean[];
    bucket: PresenceBucket;
    /** The timeline's own labels for the first and last bucket, as its chart shows them. */
    firstLabel: string | null;
    lastLabel: string | null;
}

interface PresenceTimeline {
    bucket?: string | null;
    points?: Array<{ bucket_start: string; label?: string | null }> | null;
    compare_series?: Array<{ species: string; points?: Array<{ bucket_start: string; count?: number | null }> | null }> | null;
}

/**
 * Which buckets of the window a species was on camera in, from the timeline's per-species
 * series. Only presence is drawn, never the series' counts: those are frames, and the
 * spotlight counts visits, so mixing the two would mislead. A species the timeline did not
 * chart has no strip rather than an empty one, which would read as "never seen".
 */
export function presenceFor(names: string[], timeline: PresenceTimeline | null): Presence | null {
    const bucket = timeline?.bucket;
    if (bucket !== 'hour' && bucket !== 'day' && bucket !== 'month') return null;
    const points = timeline?.points ?? [];
    if (points.length === 0) return null;
    const wanted = new Set(names.map((name) => name.trim().toLowerCase()));
    const series = (timeline?.compare_series ?? []).find((entry) => wanted.has(entry.species.trim().toLowerCase()));
    if (!series) return null;
    const counts = new Map((series.points ?? []).map((point) => [point.bucket_start, Number(point.count ?? 0)] as const));
    return {
        present: points.map((point) => (counts.get(point.bucket_start) ?? 0) > 0),
        bucket,
        firstLabel: points[0]?.label ?? null,
        lastLabel: points[points.length - 1]?.label ?? null
    };
}
