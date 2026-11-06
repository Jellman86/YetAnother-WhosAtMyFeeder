/**
 * What the Explorer's results pane shows. A failed or unfinished read must never look like an
 * empty history (#301), so the decision lives here, once, rather than in each template branch.
 */
type ExplorerResultsState = 'idle' | 'first-load' | 'error' | 'empty' | 'empty-filtered' | 'results';

/** `pending`: no count measured yet. `unavailable`: the last read failed, so no count stands. */
type ExplorerCountState = 'pending' | 'unavailable' | 'measured';

export interface ExplorerPaneInput {
    /** A read is in flight. */
    loading: boolean;
    /** The latest read failed. */
    failed: boolean;
    /** At least one read has finished since the page last cleared its results. */
    measured: boolean;
    /** Entries the pane would list now: visits, captures, heard bands and Garden entries. */
    entries: number;
    /** A filter or day narrows the results, so an empty page describes the filters. */
    filtered: boolean;
}

export interface ExplorerPane {
    state: ExplorerResultsState;
    /** The results on screen answer an earlier request: a newer read is running or has failed. */
    stale: boolean;
    count: ExplorerCountState;
}

export function explorerPane({ loading, failed, measured, entries, filtered }: ExplorerPaneInput): ExplorerPane {
    const count: ExplorerCountState = failed ? 'unavailable' : measured ? 'measured' : 'pending';
    if (entries > 0) return { state: 'results', stale: loading || failed, count };
    if (failed) return { state: 'error', stale: false, count };
    if (loading) return { state: 'first-load', stale: false, count };
    if (!measured) return { state: 'idle', stale: false, count };
    return { state: filtered ? 'empty-filtered' : 'empty', stale: false, count };
}
