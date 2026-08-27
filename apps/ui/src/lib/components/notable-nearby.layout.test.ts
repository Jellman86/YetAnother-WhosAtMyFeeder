import { describe, expect, it } from 'vitest';
import notableSource from './NotableNearby.svelte?raw';

/**
 * Notable nearby was reported as possibly broken. It was not: it fetched, it
 * rendered, it showed the one notable bird within the search radius. But one
 * sighting sat in a two-column grid with half the row empty, which reads as a
 * load that failed, and the timestamp carried seconds where nothing else in
 * the app does.
 */
describe('notable nearby', () => {
    it('gives a lone sighting the full width', () => {
        expect(notableSource).toContain("result.results.length > 1 ? 'sm:grid-cols-2' : ''");
    });

    it('still pairs sightings up when there is more than one', () => {
        expect(notableSource).toContain('sm:grid-cols-2');
    });

    it('states the observation time through the shared formatter', () => {
        // Which is now minute-precise, so this matches every other time shown.
        expect(notableSource).toContain('formatDateTime(observation.observed_at)');
    });
});
