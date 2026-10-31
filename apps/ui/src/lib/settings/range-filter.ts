import type { RangeFilterStatus } from '../api/range-filter';

/** The word the status chip shows; colour only repeats it. */
type RangeStatusTone = 'filtering' | 'off' | 'not_filtering' | 'waiting';

/** The one next step a status points at, if any. */
type RangeStatusAction = 'location' | 'ebird_key' | 'refresh' | null;

export type RangeStatusSummary = {
    tone: RangeStatusTone;
    /** Amber is reserved for this: something only the owner can fix while the filter is meant to be on. */
    needsPerson: boolean;
    action: RangeStatusAction;
};

export type RangeAge = { unit: 'just_now' | 'minutes' | 'hours' | 'days'; count: number };

export type RangeProblemKey =
    | 'ebird_key_rejected'
    | 'ebird_unreachable'
    | 'ebird_error'
    | 'region_not_found'
    | 'taxonomy_unavailable'
    | 'response_too_large'
    | 'invalid_response'
    | 'list_problem'
    | 'refresh_failed';

export type RangeRegionNote = 'county_too_short' | 'approximate' | 'country_only' | null;

const KNOWN_PROBLEMS = new Set<RangeProblemKey>([
    'ebird_key_rejected',
    'ebird_unreachable',
    'ebird_error',
    'region_not_found',
    'taxonomy_unavailable',
    'response_too_large',
    'invalid_response',
    'refresh_failed'
]);

/**
 * Turn the server's single reason into what the status panel says: a word, whether a person must
 * act, and the one action that helps. The panel never claims to filter unless the server says so.
 */
export function summarizeRangeStatus(status: RangeFilterStatus): RangeStatusSummary {
    const enabled = status.enabled;
    switch (status.reason) {
        case 'active':
            return { tone: status.filtering ? 'filtering' : 'not_filtering', needsPerson: false, action: null };
        case 'ready':
            return { tone: 'off', needsPerson: false, action: 'refresh' };
        case 'needs_location':
            return { tone: enabled ? 'not_filtering' : 'off', needsPerson: enabled, action: 'location' };
        case 'needs_ebird_key':
            return { tone: enabled ? 'not_filtering' : 'off', needsPerson: enabled, action: 'ebird_key' };
        case 'waiting_for_list':
            return { tone: enabled ? 'waiting' : 'off', needsPerson: false, action: status.refreshing ? null : 'refresh' };
        case 'location_changed':
            return { tone: enabled ? 'waiting' : 'off', needsPerson: false, action: status.refreshing ? null : 'refresh' };
        case 'lookup_failed':
        case 'list_stale':
        case 'list_unusable':
            return {
                tone: enabled ? 'not_filtering' : 'off',
                needsPerson: enabled,
                action: status.problem === 'ebird_key_rejected' ? 'ebird_key' : 'refresh'
            };
        default:
            return { tone: enabled ? 'not_filtering' : 'off', needsPerson: false, action: null };
    }
}

/** How long ago a server timestamp was, in the largest whole unit. */
export function rangeAge(iso: string | null | undefined, now: Date = new Date()): RangeAge | null {
    if (!iso) return null;
    const then = Date.parse(iso);
    if (Number.isNaN(then)) return null;
    const minutes = Math.max(0, Math.floor((now.getTime() - then) / 60_000));
    if (minutes < 1) return { unit: 'just_now', count: 0 };
    if (minutes < 60) return { unit: 'minutes', count: minutes };
    const hours = Math.floor(minutes / 60);
    if (hours < 48) return { unit: 'hours', count: hours };
    return { unit: 'days', count: Math.floor(hours / 24) };
}

/** A server problem code mapped onto the sentence that explains it; list checks share one sentence. */
export function rangeProblemKey(problem: string | null | undefined): RangeProblemKey | null {
    if (!problem) return null;
    if (problem.startsWith('list_') || ['empty_list', 'too_large', 'poorly_mapped', 'inconsistent', 'invalid_region', 'future_timestamp'].includes(problem)) {
        return 'list_problem';
    }
    return KNOWN_PROBLEMS.has(problem as RangeProblemKey) ? (problem as RangeProblemKey) : 'refresh_failed';
}

/** Why the region used is coarser than the setting asked for, when it is. */
export function rangeRegionNote(status: RangeFilterStatus): RangeRegionNote {
    if (status.region?.note === 'county_list_too_short') return 'county_too_short';
    if (status.location_precision === 'country_only') return 'country_only';
    if (status.location_precision === 'approximate' && status.region_level_setting === 'county') return 'approximate';
    return null;
}

/** Neighbouring counties combined with the nearest one near a border. */
export function rangeNeighbourCount(status: RangeFilterStatus): number {
    return Math.max(0, (status.region?.codes.length ?? 1) - 1);
}
