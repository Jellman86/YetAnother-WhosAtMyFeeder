import type { LeaderboardSpan, LeaderboardSpeciesResponse } from '../api';

/** The Leaderboard's periods, shortest first. `day` is the last 24 hours, kept for old links. */
export const LEADERBOARD_SPANS: readonly LeaderboardSpan[] = ['today', 'day', 'week', 'month', 'all'];

type SourceMode = 'seen' | 'heard' | 'both';

/** Why the window before is no fair comparison, as the server measured it. */
export type WindowMismatch = NonNullable<LeaderboardSpeciesResponse['previous_window_mismatch']>;

/** What one source's ranking said about its window and the window before it. */
export interface WindowReading {
    start: string | null;
    /** A guest's allowance moved the start later than the period asks for. */
    shortened: boolean;
    /** The history covers the whole of the window before. */
    complete: boolean;
    /** Why the window before cannot be compared whatever the history holds, or null when it can. */
    mismatch: WindowMismatch | null;
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
 * Why the ranking shows no trend: the reason the server gave for the windows not being like for
 * like, or a history that does not reach back far enough. Null when the trend was measured.
 */
export function trendGap(
    mode: SourceMode,
    seen: WindowReading | null,
    heard: WindowReading | null
): WindowMismatch | 'history' | null {
    const readings = counted(mode, seen, heard);
    const mismatch = readings.find((reading) => reading?.mismatch)?.mismatch;
    if (mismatch) return mismatch;
    if (readings.every((reading) => reading?.complete)) return null;
    return 'history';
}

/**
 * Whether every answer of one load counted from the same start. Requests sent either side of
 * midnight resolve two different Todays, which must never be shown, or summed, as one.
 */
export function windowsAgree(starts: readonly (string | null | undefined)[]): boolean {
    const instants = new Set(starts.filter((start): start is string => Boolean(start)).map((start) => Date.parse(start)));
    return instants.size <= 1;
}
