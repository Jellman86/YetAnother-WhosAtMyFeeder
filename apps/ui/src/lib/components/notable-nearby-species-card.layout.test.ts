import { describe, expect, it } from 'vitest';
import notableNearbySource from './NotableNearby.svelte?raw';
import dashboardSource from '../pages/Dashboard.svelte?raw';

describe('Notable nearby opens the species card', () => {
    it('each sighting is a real button that hands the species up', () => {
        expect(notableNearbySource).toContain('onselectspecies?: (species: string) => void');
        expect(notableNearbySource).toContain('onselectspecies?.(observationName)');
        // A row without a handler or a name is honestly inert, not silently dead.
        expect(notableNearbySource).toContain('disabled={!onselectspecies || !observationName}');
        // Keyboard-visible focus per the accessibility floor.
        expect(notableNearbySource).toContain('focus-visible:ring-2');
        expect(notableNearbySource).toContain('open_species');
    });

    it('the dashboard routes it into its existing species modal', () => {
        expect(dashboardSource).toContain('onselectspecies={(species) => (selectedSpecies = species)}');
        expect(dashboardSource).toContain('<SpeciesDetailModal speciesName={selectedSpecies}');
    });
});
