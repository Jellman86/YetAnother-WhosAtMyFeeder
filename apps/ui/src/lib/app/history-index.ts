/**
 * Each history entry the app writes carries its position, so a navigation that has already moved
 * the address (Back, Forward) can be undone by stepping back exactly as far, instead of pushing a
 * new entry that would cut off the rest of the history.
 */
const KEY = 'yawamfHistoryIndex';

export function historyIndexOf(state: unknown): number | null {
    if (!state || typeof state !== 'object') return null;
    const index = (state as Record<string, unknown>)[KEY];
    return typeof index === 'number' && Number.isInteger(index) ? index : null;
}

/** The entry's state with its position recorded, keeping whatever else the entry already holds. */
export function withHistoryIndex(state: unknown, index: number): Record<string, unknown> {
    const base = state && typeof state === 'object' ? (state as Record<string, unknown>) : {};
    return { ...base, [KEY]: index };
}
