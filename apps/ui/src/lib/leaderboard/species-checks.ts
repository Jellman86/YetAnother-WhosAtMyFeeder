import type { AudioSpeciesLeaderboardItem, LeaderboardSpan, LeaderboardSpeciesResponse } from '../api';
import type { ChecksStatus } from '../utils/needs-your-call';
import { evidenceFor, isUnlikelyHere, type EvidenceContext, type EvidenceRow } from './evidence';

/**
 * The range check, shared by the Species page's "Needs a check" card and the Dashboard's
 * "Needs your call", so the two surfaces always flag the same species for the same window.
 */
export interface CheckableRow extends EvidenceRow {
    /** Whether eBird birders reported it near the feeder recently; null when unknown. */
    reported_nearby?: boolean | null;
}

/** Only the camera backs it and no birder reported it nearby: probably misnamed. */
export function needsSpeciesCheck(row: CheckableRow, context: EvidenceContext): boolean {
    return isUnlikelyHere(evidenceFor(row, context), row.reported_nearby);
}

export type HeardLookup = Map<string, AudioSpeciesLeaderboardItem>;

/** BirdNET's rollups keyed by scientific name (preferred) and by its own species name. */
export function heardLookup(audio: readonly AudioSpeciesLeaderboardItem[]): HeardLookup {
    const map: HeardLookup = new Map();
    for (const item of audio) {
        if (item.scientific_name) map.set(`sci:${item.scientific_name.toLowerCase()}`, item);
        if (item.species) map.set(`nm:${item.species.toLowerCase()}`, item);
    }
    return map;
}

/** What BirdNET heard of a camera species in the same window, matched by identity before name. */
export function heardFor(
    row: { species: string; scientific_name?: string | null },
    lookup: HeardLookup
): AudioSpeciesLeaderboardItem | undefined {
    if (row.scientific_name) {
        const byScientificName = lookup.get(`sci:${row.scientific_name.toLowerCase()}`);
        if (byScientificName) return byScientificName;
    }
    if (row.species) return lookup.get(`nm:${row.species.toLowerCase()}`);
    return undefined;
}

export type WindowSpeciesCheck = LeaderboardSpeciesResponse['species'][number];

/**
 * The flagged species of one leaderboard window. `audio` is BirdNET's rollup for the same window,
 * or null when it is off or did not load, so silence is never read as "not heard".
 */
export function windowSpeciesChecks(
    response: LeaderboardSpeciesResponse,
    audio: readonly AudioSpeciesLeaderboardItem[] | null
): WindowSpeciesCheck[] {
    const lookup = heardLookup(audio ?? []);
    const context = { audioKnown: audio !== null };
    return response.species.filter((item) =>
        needsSpeciesCheck(
            {
                count: item.window_count ?? 0,
                heard_count: heardFor(item, lookup)?.heard_count ?? 0,
                confirmed_count: item.window_confirmed_count ?? null,
                reported_nearby: item.reported_nearby ?? null
            },
            context
        )
    );
}

export interface RangeCheckReading {
    status: ChecksStatus;
    checks: WindowSpeciesCheck[];
    nearbyRadiusKm: number | null;
}

/**
 * The next state of the range check after a leaderboard read. Only a check that ran measures
 * anything: a switched-off check is no pending work, and one that could not run keeps the last
 * measured list, marked unavailable, rather than reading its unknown rows as zero.
 */
export function readRangeCheck(
    previous: RangeCheckReading,
    response: LeaderboardSpeciesResponse,
    audio: readonly AudioSpeciesLeaderboardItem[] | null
): RangeCheckReading {
    if (response.nearby_check === 'checked') {
        return { status: 'ready', checks: windowSpeciesChecks(response, audio), nearbyRadiusKm: response.nearby_radius_km ?? null };
    }
    if (response.nearby_check === 'off') return { status: 'off', checks: [], nearbyRadiusKm: null };
    return { ...previous, status: 'unavailable' };
}

const LINK_SPANS: readonly LeaderboardSpan[] = ['day', 'week', 'month', 'all'];
const CHECKS_ANCHOR = 'checks';

/** The Species page over the Dashboard's 24 hours, opened at its species checks. */
export const SPECIES_CHECKS_LINK = `/species?span=day#${CHECKS_ANCHOR}`;

export interface SpeciesPageLink {
    /** The window the link asks for, or null to keep the page's default. */
    span: LeaderboardSpan | null;
    /** Scroll to and focus the checks card once it is shown. */
    focusChecks: boolean;
}

export function parseSpeciesPageLink(search: string, hash: string): SpeciesPageLink {
    const requested = new URLSearchParams(search).get('span');
    const span = LINK_SPANS.find((candidate) => candidate === requested) ?? null;
    return { span, focusChecks: hash.replace(/^#/, '') === CHECKS_ANCHOR };
}
