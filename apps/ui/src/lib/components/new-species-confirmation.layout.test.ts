import { describe, expect, it } from 'vitest';
import dashboardSource from '../pages/Dashboard.svelte?raw';
import cardSource from './ReviewQueueCard.svelte?raw';
import modalSource from './ReviewQueueModal.svelte?raw';

describe('a new species asks for one human call in the review queue (#310)', () => {
    // A 34% Hadeda Ibis in Ohio should not have to be stumbled over in the
    // Explorer. The existing "Needs your call" queue is the home for it:
    // same card, same modal, one more reason.

    it('the dashboard feeds unconfirmed newcomers into both queue builds', () => {
        expect(dashboardSource).toContain('fetchNewSpeciesQueue');
        const merges = dashboardSource.split('newSpecies: newSpeciesEntries').length - 1;
        expect(merges).toBe(2);
        expect(dashboardSource).toContain('onblock={blockFromQueue}');
    });

    it('the card names the reason in words, not just a score', () => {
        expect(cardSource).toContain("=== 'new_species'");
        expect(cardSource).toContain('dashboard.review_queue.new_species_tag');
    });

    it('the modal offers confirm and block only for a new species', () => {
        expect(modalSource).toContain('data-review-new-species-actions');
        expect(modalSource).toContain('dashboard.review_session.confirm_species');
        expect(modalSource).toContain('dashboard.review_session.block_species');
        // Confirm is the detection's own species through the same identify
        // path, which the backend records as a manual confirmation.
        expect(modalSource).toContain('identify(current.display_name)');
    });

    it('blocking appends to the settings list and refreshes the queue', () => {
        expect(dashboardSource).toContain('blocked_species: [');
        expect(dashboardSource).toContain('...existing');
        const refreshes = dashboardSource.split('void refreshNewSpecies()').length - 1;
        expect(refreshes).toBeGreaterThanOrEqual(3);
    });
});
