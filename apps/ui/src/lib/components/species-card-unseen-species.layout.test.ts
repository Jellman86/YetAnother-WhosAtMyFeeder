import { describe, expect, it } from 'vitest';
import modalSource from './SpeciesDetailModal.svelte?raw';
import coreSource from '../api/core.ts?raw';

describe('the species card for a bird never seen at this feeder', () => {
    // A notable sighting nearby is, by definition, a bird the cameras have
    // probably never recorded. The stats endpoint answers 404 for it, and the
    // card used to surface that as "Detection not found" instead of opening.

    it('treats a stats 404 as an empty record, not a failure', () => {
        expect(modalSource).toContain('e instanceof ApiRequestError && e.status === 404');
        expect(modalSource).toContain('stats = null;');
    });

    it('the API layer keeps the HTTP status on a failed response', () => {
        expect(coreSource).toContain('class ApiRequestError extends Error');
        expect(coreSource).toContain('throw new ApiRequestError(error, response.status)');
    });

    it('says honestly that the feeder has no record, and where the rest comes from', () => {
        expect(modalSource).toContain('data-species-no-local-visits');
        expect(modalSource).toContain('species_detail.no_local_visits_title');
        expect(modalSource).toContain('species_detail.no_local_visits_body');
    });

    it('still shows the reference hero image without local stats', () => {
        // The hero image needs enrichment info, not detection history.
        expect(modalSource).not.toContain('{#if summaryEnabled && stats}');
    });
});
