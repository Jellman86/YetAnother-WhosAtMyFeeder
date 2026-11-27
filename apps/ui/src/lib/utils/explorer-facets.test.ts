import { describe, expect, it } from 'vitest';
import {
    explorerFacetCounts,
    explorerFacetKey,
    explorerFacetOptions,
    explorerFacetReadNeeded,
    explorerFacetWindowKey,
    type ExplorerFacetChoice,
    type ExplorerFacetRead
} from './explorer-facets';

const choice: ExplorerFacetChoice = {
    datePreset: 'all',
    customStartDate: '',
    customEndDate: '',
    visits: true,
    species: '',
    taxon: null,
    camera: '',
    favoritesOnly: false,
    audioConfirmedOnly: false,
    multipleSpeciesOnly: false,
    ownerConfirmedOnly: false,
    onlyHidden: false
};

describe('explorer facet counts (#1097)', () => {
    it('asks for the counts over the window the results were read with, in visits or captures', () => {
        expect(explorerFacetOptions({ ...choice, datePreset: 'today' }, { startDate: '2033-10-03', endDate: '2033-10-03' })).toMatchObject({
            unit: 'visits',
            startDate: '2033-10-03',
            endDate: '2033-10-03'
        });
        expect(explorerFacetOptions({ ...choice, visits: false }, {}).unit).toBe('captures');
    });

    it('passes on every filter, leaving the server to keep each facet out of its own count', () => {
        const options = explorerFacetOptions(
            { ...choice, species: 'taxa:12716', taxon: 3, camera: 'patio', favoritesOnly: true, audioConfirmedOnly: true, onlyHidden: true },
            {}
        );
        expect(options).toMatchObject({ species: 'taxa:12716', taxon: 3, camera: 'patio', favoritesOnly: true, audioConfirmedOnly: true, onlyHidden: true });
        expect(explorerFacetOptions(choice, {})).toMatchObject({ species: undefined, taxon: undefined, camera: undefined });
    });

    it('names a new set of counts for each period, unit and filter, but not for a page or sort', () => {
        const keys = new Set([
            explorerFacetKey(choice),
            explorerFacetKey({ ...choice, datePreset: 'today' }),
            explorerFacetKey({ ...choice, visits: false }),
            explorerFacetKey({ ...choice, camera: 'patio' }),
            explorerFacetKey({ ...choice, species: 'taxa:1' }),
            explorerFacetKey({ ...choice, onlyHidden: true })
        ]);
        expect(keys.size).toBe(6);
        // Custom dates name the window only when Custom is chosen.
        expect(explorerFacetKey({ ...choice, customStartDate: '2033-10-01' })).toBe(explorerFacetKey(choice));
        expect(explorerFacetKey({ ...choice, datePreset: 'custom', customStartDate: '2033-10-01' })).not.toBe(
            explorerFacetKey({ ...choice, datePreset: 'custom' })
        );
    });

    it('calls counts current only when the newest read, for the results on screen, has answered', () => {
        const read = (status: ExplorerFacetRead['status'], choice = 'today'): ExplorerFacetRead => ({ generation: 1, choice, window: 'w', visits: true, status });
        expect(explorerFacetCounts('today', read('current'))).toBe('current');
        // Other results on screen, or none read yet: the counts wait.
        expect(explorerFacetCounts('today', read('current', 'all'))).toBe('pending');
        expect(explorerFacetCounts(null, read('current'))).toBe('pending');
        expect(explorerFacetCounts('today', null)).toBe('pending');
        // A retry or refresh of the same filters waits too, rather than showing the old answer or failure.
        expect(explorerFacetCounts('today', read('pending'))).toBe('pending');
        expect(explorerFacetCounts('today', read('failed'))).toBe('unavailable');
        // The same filters read again keep their last counts in view, as updating.
        expect(explorerFacetCounts('today', read('updating'))).toBe('updating');
    });

    it('reads the counts again for other filters or another window, never for the same ones', () => {
        const window = explorerFacetWindowKey({ startTime: '2033-10-03T11:00:00.000Z', endTime: '2033-10-04T11:00:00.000Z' });
        const read: ExplorerFacetRead = { generation: 1, choice: 'k', window, visits: true, status: 'current' };
        expect(explorerFacetReadNeeded(null, 'k', window)).toBe(true);
        expect(explorerFacetReadNeeded(read, 'k', window)).toBe(false);
        expect(explorerFacetReadNeeded(read, 'other', window)).toBe(true);
        // The last 24 hours read a moment later is another window, so its counts are read with it.
        expect(explorerFacetReadNeeded(read, 'k', explorerFacetWindowKey({ startTime: '2033-10-03T11:00:01.000Z', endTime: '2033-10-04T11:00:01.000Z' }))).toBe(true);
        expect(explorerFacetWindowKey({ startDate: '2033-10-03', endDate: '2033-10-03' })).not.toBe(explorerFacetWindowKey({ startDate: '2033-10-04', endDate: '2033-10-04' }));
    });
});
