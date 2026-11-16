/**
 * How current a page's reading is, changed only when a read settles. Starting a read changes nothing,
 * so data kept from before a failure stays marked stale until a read succeeds; a success clears an
 * earlier failure; and a response that settles after a newer read already did is ignored.
 */
export interface ReadSettled {
    /** The latest settled read's failure, or null when it succeeded. */
    error: string | null;
    /** When the latest successful read settled. */
    readAt: number | null;
    /** The token of the newest read that has settled. */
    token: number;
}

export const INITIAL_READ: ReadSettled = { error: null, readAt: null, token: 0 };

export function settleRead(
    state: ReadSettled,
    token: number,
    outcome: { ok: true; at: number } | { ok: false; error: string }
): ReadSettled {
    if (token < state.token) return state;
    return outcome.ok
        ? { error: null, readAt: outcome.at, token }
        : { error: outcome.error, readAt: state.readAt, token };
}

export function readFreshness(hasReading: boolean, state: ReadSettled): 'reading' | 'read' | 'stale' | 'failed' {
    if (!hasReading) return state.error ? 'failed' : 'reading';
    return state.error ? 'stale' : 'read';
}
