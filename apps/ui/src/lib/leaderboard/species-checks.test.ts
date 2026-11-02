import { describe, expect, it } from 'vitest';
import type { AudioSpeciesLeaderboardItem, LeaderboardSpeciesResponse } from '../api';
import {
    heardFor,
    heardLookup,
    needsSpeciesCheck,
    parseSpeciesPageLink,
    SPECIES_CHECKS_LINK,
    windowSpeciesChecks
} from './species-checks';

type WindowSpecies = LeaderboardSpeciesResponse['species'][number];

function species(name: string, overrides: Partial<WindowSpecies> = {}): WindowSpecies {
    return {
        species: name,
        scientific_name: null,
        common_name: name,
        taxa_id: null,
        window_count: 3,
        window_prev_count: 0,
        window_delta: 3,
        window_percent: 0,
        window_confirmed_count: 0,
        window_visit_count: 1,
        window_prev_visit_count: 0,
        reported_nearby: false,
        ...overrides
    } as WindowSpecies;
}

function response(rows: WindowSpecies[]): LeaderboardSpeciesResponse {
    return { span: 'day', window_start: '2026-11-01T12:00:00Z', window_end: '2026-11-02T12:00:00Z', species: rows } as LeaderboardSpeciesResponse;
}

function heard(name: string, scientificName: string | null, count: number): AudioSpeciesLeaderboardItem {
    return { species: name, scientific_name: scientificName, heard_count: count } as AudioSpeciesLeaderboardItem;
}

describe('needsSpeciesCheck', () => {
    it('flags a species only the camera backs that nobody reported nearby', () => {
        expect(needsSpeciesCheck({ count: 4, heard_count: 0, confirmed_count: 0, reported_nearby: false }, { audioKnown: true })).toBe(true);
    });

    it('never flags a species a person confirmed or BirdNET heard', () => {
        expect(needsSpeciesCheck({ count: 4, heard_count: 0, confirmed_count: 1, reported_nearby: false }, { audioKnown: true })).toBe(false);
        expect(needsSpeciesCheck({ count: 4, heard_count: 2, confirmed_count: 0, reported_nearby: false }, { audioKnown: true })).toBe(false);
    });

    it('never flags when the nearby reports are unknown or include it', () => {
        expect(needsSpeciesCheck({ count: 4, heard_count: 0, confirmed_count: 0, reported_nearby: null }, { audioKnown: true })).toBe(false);
        expect(needsSpeciesCheck({ count: 4, heard_count: 0, confirmed_count: 0, reported_nearby: true }, { audioKnown: true })).toBe(false);
    });

    it('does not count an unheard call as absence when BirdNET did not load', () => {
        expect(needsSpeciesCheck({ count: 4, heard_count: 3, confirmed_count: 0, reported_nearby: false }, { audioKnown: false })).toBe(true);
    });
});

describe('heardFor', () => {
    it('matches a call by scientific name before the localised name', () => {
        const lookup = heardLookup([heard('Bankivahuhn', 'Gallus gallus', 5), heard('Red Junglefowl', null, 1)]);
        expect(heardFor({ species: 'Red Junglefowl', scientific_name: 'Gallus gallus' }, lookup)?.heard_count).toBe(5);
        expect(heardFor({ species: 'red junglefowl', scientific_name: null }, lookup)?.heard_count).toBe(1);
        expect(heardFor({ species: 'Dunnock', scientific_name: 'Prunella modularis' }, lookup)).toBeUndefined();
    });
});

describe('windowSpeciesChecks', () => {
    it('returns the flagged species of the window with their identity', () => {
        const checks = windowSpeciesChecks(
            response([
                species('Red Junglefowl', { scientific_name: 'Gallus gallus', taxa_id: 1 }),
                species('Dunnock', { reported_nearby: true }),
                species('European Robin', { window_confirmed_count: 2 })
            ]),
            []
        );
        expect(checks.map((check) => [check.species, check.scientific_name, check.taxa_id])).toEqual([['Red Junglefowl', 'Gallus gallus', 1]]);
    });

    it('clears a species BirdNET heard in the window, as the Species page does', () => {
        const rows = response([species('Red Junglefowl', { scientific_name: 'Gallus gallus' })]);
        expect(windowSpeciesChecks(rows, [heard('Red Junglefowl', 'Gallus gallus', 2)])).toEqual([]);
        expect(windowSpeciesChecks(rows, null)).toHaveLength(1);
    });

    it('never flags the unidentified row, which the visit queue already holds', () => {
        expect(windowSpeciesChecks(response([species('Unknown Bird', { reported_nearby: null })]), [])).toEqual([]);
    });
});

describe('the link to the Species page checks', () => {
    it('opens the 24 hour window at the checks', () => {
        expect(SPECIES_CHECKS_LINK).toBe('/species?span=day#checks');
        expect(parseSpeciesPageLink('?span=day', '#checks')).toEqual({ span: 'day', focusChecks: true });
    });

    it('keeps the page default for a missing or unknown span', () => {
        expect(parseSpeciesPageLink('', '')).toEqual({ span: null, focusChecks: false });
        expect(parseSpeciesPageLink('?span=decade', '#other')).toEqual({ span: null, focusChecks: false });
        expect(parseSpeciesPageLink('?span=all', '')).toEqual({ span: 'all', focusChecks: false });
    });
});
