/**
 * What Audio history can honestly show (layout-patterns 1.5): a pending read and a failed read are
 * not an empty window, so neither may render zeros or "no activity". A refresh that failed while an
 * earlier reading of the same request is kept is stale, said in words beside that reading.
 */
export type AudioReading = 'loading' | 'failed' | 'stale' | 'empty' | 'ready';

export function audioReading(state: {
    loading: boolean;
    error: string | null;
    stale: boolean;
    /** The measured number of calls in the window, or null when none has been read. */
    total: number | null;
}): AudioReading {
    if (state.error) return state.stale && state.total !== null ? 'stale' : 'failed';
    if (state.loading || state.total === null) return 'loading';
    return state.total === 0 ? 'empty' : 'ready';
}
