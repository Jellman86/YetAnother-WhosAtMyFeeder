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

    it('the API layer carries only_hidden to the list, the count and the filter counts', () => {
        const occurrences = eventsApiSource.split("params.set('only_hidden', 'true')").length - 1;
        expect(occurrences).toBe(3);
        expect(eventsApiSource).toContain("if (options.onlyHidden) params.set('only_hidden', 'true');");
        // Distinct cache keys, or a toggle would replay the other view's rows.
        expect(eventsApiSource).toContain("onlyHidden ? 'only-hidden' : includeHidden ? 'hidden' : 'visible'");
    });

    it('unhiding a visit while viewing only hidden removes it from the list', () => {
        // A row that stops qualifying for the active filter must leave the
        // view, or the list claims a state the database no longer holds.
        // The record's hide is the one path that unhides, through the shared opener's callback.
        const removals = eventsPageSource.split('In the hidden-only view an unhidden row no longer qualifies.').length - 1;
        expect(removals).toBe(1);
        const onHide = eventsPageSource.slice(eventsPageSource.indexOf('onHideSuccess={'));
        expect(onHide.indexOf('In the hidden-only view an unhidden row no longer qualifies.')).toBeGreaterThan(-1);
        expect(onHide).toContain('? events.filter((event) => event.frigate_event !== hiddenEventId)');
    });
});
