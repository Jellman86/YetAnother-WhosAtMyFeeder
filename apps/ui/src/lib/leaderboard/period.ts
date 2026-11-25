import type { LeaderboardSpan } from '../api';

/** The Leaderboard's periods, shortest first. `day` is the last 24 hours, kept for old links. */
export const LEADERBOARD_SPANS: readonly LeaderboardSpan[] = ['today', 'day', 'week', 'month', 'all'];

type SourceMode = 'seen' | 'heard' | 'both';

/** What one source's ranking said about its window and the window before it. */
export interface WindowReading {
    start: string | null;
    /** A guest's allowance moved the start later than the period asks for. */
    shortened: boolean;
    /** The history covers the whole of the window before. */
    complete: boolean;
    /** The window before covers the same stretch of the clock. */
    comparable: boolean;
}

function counted(mode: SourceMode, seen: WindowReading | null, heard: WindowReading | null): (WindowReading | null)[] {
    if (mode === 'seen') return [seen];
    if (mode === 'heard') return [heard];
    return [seen, heard];
}

/** The start a guest's window was cut to, for the source the ranking counts, or null when it was not. */
export function shortenedWindowStart(
    mode: SourceMode,
    seen: WindowReading | null,
    heard: WindowReading | null
): string | null {
    return counted(mode, seen, heard).find((reading) => reading?.shortened)?.start ?? null;
}

/**
 * Why the ranking shows no trend: the windows were not like for like (a clock change in Today, or
 * a guest's cut), or the history does not reach back far enough. Null when the trend was measured.
 */
export function trendGap(
    mode: SourceMode,
    seen: WindowReading | null,
    heard: WindowReading | null
): 'not_comparable' | 'history' | null {
    const readings = counted(mode, seen, heard);
    if (readings.some((reading) => reading !== null && !reading.comparable)) return 'not_comparable';
    if (readings.every((reading) => reading?.complete)) return null;
    return 'history';
}
