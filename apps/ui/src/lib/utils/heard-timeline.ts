import type { HeardGroup } from '../api/audio';
import type { DetectionVisit } from '../api/visits';

/**
 * Where heard calls sit in the Explorer.
 *
 * Visits stay the rows (layout-patterns 1.2). BirdNET-Go calls that match a confirmed visit fold
 * into it, the way the visit already says "matching call". Every other call gathers into one band
 * per gap between two visits, so a morning of sparrow chatter is one line, not forty.
 */

interface HeardSpeciesCount {
    name: string;
    count: number;
}

type HeardBandPosition = 'after-last' | 'between' | 'before-first';

export interface HeardBand {
    key: string;
    position: HeardBandPosition;
    /** Newest first by the time each group began, the Explorer's reading order. */
    groups: HeardGroup[];
    firstHeard: string;
    lastHeard: string;
    callCount: number;
    species: HeardSpeciesCount[];
    /** Spectrograms for the band's picture: the strongest groups of its busiest species. */
    pictures: number[];
}

export type HeardTimelineEntry =
    | { kind: 'visit'; visit: DetectionVisit; matchedCalls: number }
    | { kind: 'band'; band: HeardBand };

export interface HeardTimelineInput {
    /** The page's visits in display order. */
    visits: DetectionVisit[];
    groups: HeardGroup[];
    sort: 'newest' | 'oldest';
    correlationWindowSeconds: number;
    /** A visit just before this page in display order exists, so the leading gap is not the end. */
    hasPreviousPage: boolean;
    /** A visit just after this page exists, so the trailing gap is not the end either. */
    hasNextPage: boolean;
}

const time = (value: string): number => Date.parse(value);

function fold(value: string | null | undefined): string {
    return (value ?? '').trim().toLocaleLowerCase();
}

function sameSpecies(group: HeardGroup, visit: DetectionVisit): boolean {
    const bird = visit.representative;
    const scientific = fold(group.scientific_name);
    if (scientific && scientific === fold(bird.scientific_name)) return true;
    const heard = fold(group.species);
    return heard !== '' && [bird.common_name, bird.display_name].some((name) => fold(name) === heard);
}

/**
 * The visit a group of calls confirms, if any. Only a visit the app already confirmed by a call
 * can claim one, so the Explorer never states a match the pipeline did not make, and the camera
 * to microphone mapping that decided the confirmation still holds.
 */
function matchingVisit(group: HeardGroup, visits: DetectionVisit[], windowMs: number): DetectionVisit | null {
    const from = time(group.first_heard) - windowMs;
    const to = time(group.last_heard) + windowMs;
    return (
        visits.find(
            (visit) =>
                Boolean(visit.audio_confirmed) &&
                sameSpecies(group, visit) &&
                time(visit.start_time) <= to &&
                time(visit.end_time) >= from
        ) ?? null
    );
}

function speciesCounts(groups: HeardGroup[]): HeardSpeciesCount[] {
    const counts = new Map<string, HeardSpeciesCount>();
    for (const group of groups) {
        const key = fold(group.scientific_name) || fold(group.species);
        const entry = counts.get(key) ?? { name: group.species, count: 0 };
        entry.count += group.call_count;
        counts.set(key, entry);
    }
    return [...counts.values()].sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
}

function pictures(groups: HeardGroup[], species: HeardSpeciesCount[]): number[] {
    const chosen: number[] = [];
    for (const { name } of species) {
        const strongest = groups
            .filter((group) => group.species === name && group.best_birdnet_id)
            .sort((a, b) => b.best_confidence - a.best_confidence)[0];
        if (strongest?.best_birdnet_id) chosen.push(strongest.best_birdnet_id);
        if (chosen.length === 3) break;
    }
    return chosen;
}

function band(groups: HeardGroup[], position: HeardBandPosition): HeardBand {
    // Each line is labelled with the time its calls began, so it is ordered by that time too.
    const ordered = [...groups].sort((a, b) => time(b.first_heard) - time(a.first_heard));
    const species = speciesCounts(ordered);
    const firstHeard = ordered[ordered.length - 1].first_heard;
    const lastHeard = ordered.reduce((last, group) => (time(group.last_heard) > time(last) ? group.last_heard : last), ordered[0].last_heard);
    return {
        key: `${position}:${firstHeard}`,
        position,
        groups: ordered,
        firstHeard,
        lastHeard,
        callCount: ordered.reduce((sum, group) => sum + group.call_count, 0),
        species,
        pictures: pictures(ordered, species)
    };
}

export function buildHeardTimeline(input: HeardTimelineInput): HeardTimelineEntry[] {
    const { visits, sort, hasPreviousPage, hasNextPage } = input;
    const windowMs = Math.max(0, input.correlationWindowSeconds) * 1000;
    const chrono = [...visits].sort((a, b) => time(a.start_time) - time(b.start_time));
    const matched = new Map<string, number>();
    const gaps: HeardGroup[][] = chrono.map(() => []);
    gaps.push([]);

    for (const group of input.groups) {
        const visit = matchingVisit(group, chrono, windowMs);
        if (visit) {
            matched.set(visit.visit_id, (matched.get(visit.visit_id) ?? 0) + group.call_count);
            continue;
        }
        const heardAt = time(group.first_heard);
        const gap = chrono.filter((candidate) => time(candidate.start_time) <= heardAt).length;
        gaps[gap].push(group);
    }

    // Gap 0 is older than every visit, gap n newer. Which of them ends the timeline depends on
    // whether this page is the first or last in its direction.
    const newestIsEnd = sort === 'newest' ? !hasPreviousPage : !hasNextPage;
    const oldestIsEnd = sort === 'newest' ? !hasNextPage : !hasPreviousPage;
    const position = (gap: number): HeardBandPosition => {
        if (gap === chrono.length && newestIsEnd) return 'after-last';
        if (gap === 0 && oldestIsEnd) return 'before-first';
        return 'between';
    };

    const ascending: HeardTimelineEntry[] = [];
    gaps.forEach((groups, gap) => {
        if (gap > 0) {
            const visit = chrono[gap - 1];
            ascending.push({ kind: 'visit', visit, matchedCalls: matched.get(visit.visit_id) ?? 0 });
        }
        if (groups.length) ascending.push({ kind: 'band', band: band(groups, position(gap)) });
    });
    return sort === 'newest' ? ascending.reverse() : ascending;
}

/**
 * The span of calls a page owns. Each page owns the gap on its leading edge in display order,
 * and only the last page owns the gap on its trailing edge, so no band shows on two pages.
 * An unbounded end (no date filter, oldest page) has no trailing band: "everything before the
 * first visit" is not a window anyone asked for.
 */
export function heardWindow(input: {
    visits: DetectionVisit[];
    sort: 'newest' | 'oldest';
    previous: DetectionVisit | null;
    hasNextPage: boolean;
    rangeStart: Date | null;
    rangeEnd: Date | null;
    now: Date;
}): { start: Date; end: Date } | null {
    if (!input.visits.length) return null;
    const starts = input.visits.map((visit) => time(visit.start_time));
    const ends = input.visits.map((visit) => time(visit.end_time));
    const oldest = new Date(Math.min(...starts));
    const newest = new Date(Math.max(...ends));
    const rangeEnd = input.rangeEnd && input.rangeEnd < input.now ? input.rangeEnd : input.now;
    if (input.sort === 'newest') {
        const end = input.previous ? new Date(time(input.previous.start_time)) : rangeEnd;
        const start = input.hasNextPage || !input.rangeStart ? oldest : input.rangeStart;
        return { start, end };
    }
    const start = input.previous ? new Date(time(input.previous.end_time)) : (input.rangeStart ?? oldest);
    const end = input.hasNextPage ? newest : rangeEnd;
    return { start, end };
}
