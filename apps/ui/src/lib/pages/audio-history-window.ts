import type { AudioHistoryParams } from '../api';
import type { AudioHistoryFilters } from './audio-history-filters';

/** The periods Audio history reads, named as every page names them: Today, then the rolling windows. */
export const AUDIO_HISTORY_WINDOWS = ['today', '24h', '7d', '30d', '90d', '1y'] as const;

export type AudioHistoryWindow = (typeof AUDIO_HISTORY_WINDOWS)[number];

const ROLLING_WINDOW_DAYS: Readonly<Record<Exclude<AudioHistoryWindow, 'today'>, number>> = {
    '24h': 1,
    '7d': 7,
    '30d': 30,
    '90d': 90,
    '1y': 365
};

export function isAudioHistoryWindow(value: unknown): value is AudioHistoryWindow {
    return typeof value === 'string' && (AUDIO_HISTORY_WINDOWS as readonly string[]).includes(value);
}

type AudioHistoryAggregateParams = Omit<AudioHistoryParams, 'limit' | 'offset'>;

/** One load's question: the list's page, and the summary's and grids' same window and filters. */
export interface AudioHistoryRequest {
    list: AudioHistoryParams;
    aggregate: AudioHistoryAggregateParams;
    /** Tells two questions apart. Today's end is "now", which moves on every read, so only its day counts. */
    key: string;
}

function windowParams(window: AudioHistoryWindow, now: Date): Pick<AudioHistoryParams, 'days' | 'start_date' | 'end_date'> {
    if (window !== 'today') return { days: ROLLING_WINDOW_DAYS[window] };
    const localMidnight = new Date(now);
    localMidnight.setHours(0, 0, 0, 0);
    return { start_date: localMidnight.toISOString(), end_date: now.toISOString() };
}

/**
 * Settles what one load of the page asks for. Today runs from the viewer's local midnight to `now`,
 * resolved here once, so the list, the summary, the grid and a species' grid all count the same calls.
 */
export function audioHistoryRequest(
    state: { applied: AudioHistoryFilters; search: string; onlyHidden: boolean; offset: number; pageSize: number },
    now: Date
): AudioHistoryRequest {
    const aggregate: AudioHistoryAggregateParams = {
        ...windowParams(state.applied.window, now),
        species: state.applied.species || undefined,
        source: state.applied.source || undefined,
        search: state.search || undefined,
        only_hidden: state.onlyHidden ? true : undefined,
        min_confidence: state.applied.minConfidence
    };
    const list: AudioHistoryParams = { ...aggregate, limit: state.pageSize, offset: state.offset };
    return { list, aggregate, key: JSON.stringify({ ...list, end_date: undefined }) };
}

/** How long until the viewer's next local midnight, when Today becomes another day. */
export function msUntilNextLocalMidnight(now: Date): number {
    const nextMidnight = new Date(now);
    nextMidnight.setHours(24, 0, 0, 0);
    return nextMidnight.getTime() - now.getTime();
}

/**
 * The start the server counted from, when it is later than the one asked for: a guest's history
 * starts where the owner's sharing does, which can cut off the start of the viewer's own day.
 */
export function narrowedWindowStart(requested: string | null | undefined, counted: string | null | undefined): string | null {
    if (!requested || !counted) return null;
    return Date.parse(counted) > Date.parse(requested) ? counted : null;
}
