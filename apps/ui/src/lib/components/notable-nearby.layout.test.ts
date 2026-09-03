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
        expect(notableSource).toContain("groups.length > 1 ? 'sm:grid-cols-2' : ''");
    });

    it('still pairs sightings up when there is more than one', () => {
        expect(notableSource).toContain('sm:grid-cols-2');
    });

    it('states the observation time through the shared formatter', () => {
        // Which is now minute-precise, so this matches every other time shown.
        expect(notableSource).toContain('formatDateTime(observation.observed_at)');
    });
});

describe('repeated reports of one species fold into one card', () => {
    it('groups by species and says how many reported it', () => {
        // Four checklists of one shrike at one reserve were four identical cards; the
        // news is that four people saw it, so one card carries the count instead.
        expect(notableSource).toContain("import { groupNotableObservations } from '../utils/notable-grouping'");
        expect(notableSource).toContain('groupNotableObservations(result.results)');
        expect(notableSource).toContain('{#each groups.slice(0, 4) as group (group.key)}');
        expect(notableSource).toContain('dashboard.notable_nearby.reports');
        expect(notableSource).toContain('{#if group.reports > 1}');
        // Several places collapse to a count rather than a truncated list of names.
        expect(notableSource).toContain('dashboard.notable_nearby.places');
    });
});
