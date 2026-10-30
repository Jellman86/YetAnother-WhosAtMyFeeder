import { describe, expect, it } from 'vitest';
import { explorerPane, type ExplorerPaneInput } from './explorer-results';

const base: ExplorerPaneInput = { loading: false, failed: false, measured: true, entries: 0, filtered: false };

describe('explorerPane', () => {
    it('shows placeholders, not an empty history, until the first read finishes', () => {
        expect(explorerPane({ ...base, loading: true, measured: false })).toEqual({ state: 'first-load', stale: false, count: 'pending' });
    });

    it('states a failed first read as a failure, never as an empty history or a count of zero', () => {
        expect(explorerPane({ ...base, failed: true, measured: false })).toEqual({ state: 'error', stale: false, count: 'unavailable' });
        // A failure after an earlier success still has nothing to show for this request.
        expect(explorerPane({ ...base, failed: true, filtered: true })).toEqual({ state: 'error', stale: false, count: 'unavailable' });
    });

    it('keeps earlier results on a failed refresh, marked stale, with the count unavailable', () => {
        expect(explorerPane({ ...base, failed: true, entries: 4 })).toEqual({ state: 'results', stale: true, count: 'unavailable' });
    });

    it('marks results stale while a newer read is in flight', () => {
        expect(explorerPane({ ...base, loading: true, entries: 4 })).toEqual({ state: 'results', stale: true, count: 'measured' });
        expect(explorerPane({ ...base, entries: 4 })).toEqual({ state: 'results', stale: false, count: 'measured' });
    });

    it('shows placeholders again when a refresh starts with nothing on screen', () => {
        expect(explorerPane({ ...base, loading: true })).toEqual({ state: 'first-load', stale: false, count: 'measured' });
    });

    it('separates an empty history from filters that match nothing', () => {
        expect(explorerPane(base)).toEqual({ state: 'empty', stale: false, count: 'measured' });
        expect(explorerPane({ ...base, filtered: true })).toEqual({ state: 'empty-filtered', stale: false, count: 'measured' });
    });

    it('claims nothing when no read was asked for, as when a shared clip opens the page', () => {
        expect(explorerPane({ ...base, measured: false })).toEqual({ state: 'idle', stale: false, count: 'pending' });
    });
});
