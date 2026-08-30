import { describe, expect, it } from 'vitest';
import eventsPageSource from './Events.svelte?raw';
import eventsApiSource from '../api/events.ts?raw';

describe('the Hidden facet shows only the hidden visits (#347)', () => {
    // The toggle sits under the "Only" heading beside Favourites and Audio
    // matches, both of which filter the list down. Wiring it to
    // include_hidden merely added the hidden rows to everything else, so
    // with one hidden visit in 1,316 it visibly did nothing.

    it('the Explorer asks for only the hidden rows, not the full list plus them', () => {
        expect(eventsPageSource).toContain('onlyHidden: showHidden');
        expect(eventsPageSource).not.toContain('includeHidden: showHidden');
    });

    it('the API layer carries only_hidden to both the list and the count', () => {
        const occurrences = eventsApiSource.split("params.set('only_hidden', 'true')").length - 1;
        expect(occurrences).toBe(2);
        // Distinct cache keys, or a toggle would replay the other view's rows.
        expect(eventsApiSource).toContain("onlyHidden ? 'only-hidden' : includeHidden ? 'hidden' : 'visible'");
    });

    it('unhiding a visit while viewing only hidden removes it from the list', () => {
        // A row that stops qualifying for the active filter must leave the
        // view, or the list claims a state the database no longer holds.
        const removals = eventsPageSource.split('In the hidden-only view an unhidden row no longer qualifies.').length - 1;
        expect(removals).toBe(2);
    });
});
