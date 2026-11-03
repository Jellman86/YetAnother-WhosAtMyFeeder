import { describe, expect, it } from 'vitest';
import type { ExplorerSearchResponse, ExplorerSearchTaxon } from '../api/explorer';
import {
    classifyExplorerQuery,
    explorerDateWords,
    explorerSearchChoice,
    explorerSearchGroups,
    normalizeSearchText,
    parseSearchDate,
    recordIdKind,
    taxonAppliesTo,
    type SearchFacetSpecies
} from './explorer-search';

// A Monday afternoon, local time.
const NOW = new Date(2026, 10, 2, 15, 30);
const english = explorerDateWords('en', { today: 'today', yesterday: 'yesterday' });
const french = explorerDateWords('fr', { today: "aujourd'hui", yesterday: 'hier' });

function taxon(partial: Partial<ExplorerSearchTaxon> & Pick<ExplorerSearchTaxon, 'taxon_id' | 'rank' | 'scientific_name'>): ExplorerSearchTaxon {
    return { name: null, bird_species: 1, bird_detections: 3, garden_species: 0, garden_captures: 0, ...partial };
}

const dunnock: SearchFacetSpecies = { value: 'taxa:145', display_name: 'Dunnock', common_name: 'Dunnock', scientific_name: 'Prunella modularis', count: 12 };
const robin: SearchFacetSpecies = { value: 'Erithacus rubecula', display_name: 'European Robin', common_name: 'European Robin', scientific_name: 'Erithacus rubecula', count: 8 };
const unplaced: SearchFacetSpecies = { value: 'Mystery finch', display_name: 'Mystery finch', common_name: null, scientific_name: null, count: 2 };

describe('normalizeSearchText', () => {
    it('sets aside case, accents and separators', () => {
        expect(normalizeSearchText('  Mésange-CHARBONNIÈRE ')).toBe('mesange charbonniere');
        expect(normalizeSearchText('Great  tit')).toBe('great tit');
    });
});

describe('recordIdKind', () => {
    it('recognises a Frigate event id and a Garden capture id by shape', () => {
        expect(recordIdKind(' 1793624285.74056-6j3htl ')).toBe('detection');
        expect(recordIdKind('a'.repeat(32))).toBe('garden');
    });

    it('treats words, numbers and near misses as text', () => {
        expect(recordIdKind('dunnock')).toBeNull();
        expect(recordIdKind('1793624285')).toBeNull();
        expect(recordIdKind('a'.repeat(31))).toBeNull();
        expect(recordIdKind('../1793624285.74056-6j3htl')).toBeNull();
    });
});

describe('parseSearchDate', () => {
    it('reads today and yesterday in the reader language and in English', () => {
        expect(parseSearchDate('Today', NOW, english)).toBe('2026-11-02');
        expect(parseSearchDate('hier', NOW, french)).toBe('2026-11-01');
        expect(parseSearchDate('yesterday', NOW, french)).toBe('2026-11-01');
        expect(parseSearchDate("aujourd'hui", NOW, french)).toBe('2026-11-02');
    });

    it('reads a day and month either way round, taking the latest such day that has passed', () => {
        expect(parseSearchDate('2 Nov', NOW, english)).toBe('2026-11-02');
        expect(parseSearchDate('November 1', NOW, english)).toBe('2026-11-01');
        expect(parseSearchDate('25 dec', NOW, english)).toBe('2025-12-25');
        expect(parseSearchDate('3 sept', NOW, english)).toBe('2026-09-03');
        expect(parseSearchDate('2 novembre', NOW, french)).toBe('2026-11-02');
        expect(parseSearchDate('14 févr.', NOW, french)).toBe('2026-02-14');
        expect(parseSearchDate('29 Feb', NOW, english)).toBe('2024-02-29');
    });

    it('reads an ISO date and an explicit year, but never a future day', () => {
        expect(parseSearchDate('2026-10-31', NOW, english)).toBe('2026-10-31');
        expect(parseSearchDate('2 Nov 2025', NOW, english)).toBe('2025-11-02');
        expect(parseSearchDate('2026-12-01', NOW, english)).toBeNull();
        expect(parseSearchDate('30 February', NOW, english)).toBeNull();
    });

    it('leaves numeric day-month orders and ordinary words alone', () => {
        expect(parseSearchDate('2/11', NOW, english)).toBeNull();
        expect(parseSearchDate('ma', NOW, english)).toBeNull();
        expect(parseSearchDate('dunnock', NOW, english)).toBeNull();
        expect(parseSearchDate('2 ju', NOW, english)).toBeNull();
    });
});

describe('classifyExplorerQuery', () => {
    it('tells an id, a date and words apart', () => {
        expect(classifyExplorerQuery('1793624285.74056-6j3htl', NOW, english)).toMatchObject({ record: 'detection', date: null, askServer: true });
        expect(classifyExplorerQuery('yesterday', NOW, english)).toMatchObject({ record: null, date: '2026-11-01', askServer: true });
        expect(classifyExplorerQuery('Dunnock', NOW, english)).toEqual({ text: 'dunnock', record: null, date: null, askServer: true });
    });

    it('does not ask the server about a single letter', () => {
        expect(classifyExplorerQuery('d', NOW, english).askServer).toBe(false);
        expect(classifyExplorerQuery('   ', NOW, english)).toMatchObject({ text: '', askServer: false });
    });
});

describe('explorerSearchGroups', () => {
    const response = (partial: Partial<ExplorerSearchResponse> = {}): ExplorerSearchResponse => ({ taxa: [], truncated: false, record: null, ...partial });

    it('groups species and taxa, cameras and dates, and links a species to its facet value', () => {
        const query = classifyExplorerQuery('nov', NOW, english);
        const groups = explorerSearchGroups({
            query,
            response: response({ taxa: [taxon({ taxon_id: 1, rank: 'species', scientific_name: 'Prunella modularis', name: 'Dunnock' })] }),
            facetSpecies: [dunnock, robin],
            cameras: ['november-cam', 'birdcam'],
            cameraCounts: { 'november-cam': 4 }
        });
        expect(groups.map((group) => group.key)).toEqual(['species', 'cameras']);
        expect(groups[0].options[0]).toMatchObject({ kind: 'taxon', facetValue: 'taxa:145' });
        expect(groups[1].options).toEqual([{ kind: 'camera', key: 'camera:november-cam', camera: 'november-cam', count: 4 }]);
    });

    it('adds facet species the catalogue does not place, without repeating placed ones', () => {
        const query = classifyExplorerQuery('in', NOW, english);
        const placed = response({ taxa: [taxon({ taxon_id: 7, rank: 'species', scientific_name: 'Erithacus rubecula', name: 'European Robin' })] });
        const groups = explorerSearchGroups({ query, response: placed, facetSpecies: [dunnock, robin, unplaced], cameras: [], cameraCounts: null });
        expect(groups).toHaveLength(1);
        expect(groups[0].options.map((option) => option.key)).toEqual(['taxon:7', 'species:Mystery finch']);
        expect(groups[0].options[0]).toMatchObject({ facetValue: 'Erithacus rubecula' });
    });

    it('offers a date for a recognisable day', () => {
        const groups = explorerSearchGroups({ query: classifyExplorerQuery('yesterday', NOW, english), response: response(), facetSpecies: [], cameras: [], cameraCounts: null });
        expect(groups).toEqual([{ key: 'dates', options: [{ kind: 'date', key: 'date:2026-11-01', day: '2026-11-01' }] }]);
    });

    it('offers only the record for a pasted id, and nothing when the reader cannot see it', () => {
        const query = classifyExplorerQuery('1793624285.74056-6j3htl', NOW, english);
        const record = { kind: 'detection' as const, id: '1793624285.74056-6j3htl', observed_at: '2026-11-02T08:00:00Z', hidden: false };
        expect(explorerSearchGroups({ query, response: response({ record }), facetSpecies: [dunnock], cameras: ['1793624285.74056-6j3htl'], cameraCounts: null }).map((group) => group.key)).toEqual(['records']);
        expect(explorerSearchGroups({ query, response: response(), facetSpecies: [], cameras: [], cameraCounts: null })).toEqual([]);
    });
});

describe('explorerSearchChoice', () => {
    const context = { subjects: 'birds' as const, gardenAvailable: true, today: '2026-11-02' };

    it('applies the species facet for a bird species it lists', () => {
        const option = { kind: 'taxon' as const, key: 'taxon:1', facetValue: 'taxa:145', taxon: taxon({ taxon_id: 1, rank: 'species', scientific_name: 'Prunella modularis' }) };
        expect(explorerSearchChoice(option, context)).toEqual({ kind: 'filter', subjects: undefined, speciesFilter: 'taxa:145', taxon: null });
        // From the Garden view a bird species brings the birds back.
        expect(explorerSearchChoice(option, { ...context, subjects: 'garden' })).toMatchObject({ subjects: 'birds' });
    });

    it('applies the taxon filter for a group, and shows Garden animals when the group holds them', () => {
        const family = { kind: 'taxon' as const, key: 'taxon:9', facetValue: null, taxon: taxon({ taxon_id: 9, rank: 'family', scientific_name: 'Columbidae', name: 'Pigeons', garden_species: 1, garden_captures: 2 }) };
        expect(explorerSearchChoice(family, context)).toEqual({
            kind: 'filter', subjects: 'all', speciesFilter: '', taxon: { id: 9, rank: 'family', name: 'Pigeons', scientificName: 'Columbidae', birdSpecies: 1, gardenSpecies: 1 }
        });
        const animal = { ...family, taxon: { ...family.taxon, bird_species: 0, bird_detections: 0 } };
        expect(explorerSearchChoice(animal, context)).toMatchObject({ subjects: 'garden' });
        expect(explorerSearchChoice(animal, { ...context, subjects: 'all' })).toMatchObject({ subjects: undefined });
        expect(explorerSearchChoice(animal, { ...context, gardenAvailable: false })).toMatchObject({ subjects: undefined });
    });

    it('applies a camera, a day or today, and opens a record', () => {
        expect(explorerSearchChoice({ kind: 'camera', key: 'camera:birdcam', camera: 'birdcam', count: null }, context)).toEqual({ kind: 'filter', cameraFilter: 'birdcam' });
        expect(explorerSearchChoice({ kind: 'date', key: 'date:2026-11-02', day: '2026-11-02' }, context)).toEqual({ kind: 'filter', datePreset: 'today' });
        expect(explorerSearchChoice({ kind: 'date', key: 'date:2026-11-01', day: '2026-11-01' }, context)).toEqual({
            kind: 'filter', datePreset: 'custom', customStartDate: '2026-11-01', customEndDate: '2026-11-01'
        });
        const record = { kind: 'garden' as const, id: 'a'.repeat(32), observed_at: '2026-11-02T08:00:00Z', hidden: false };
        expect(explorerSearchChoice({ kind: 'record', key: 'record', record }, context)).toEqual({ kind: 'open', record });
    });
});

describe('taxonAppliesTo', () => {
    const garden = { id: 9, rank: 'order', name: null, scientificName: 'Rodentia', birdSpecies: 0, gardenSpecies: 2 };
    const birds = { ...garden, scientificName: 'Passeriformes', birdSpecies: 5, gardenSpecies: 0 };

    it('holds only while a view shows visitors the group has', () => {
        expect(taxonAppliesTo(garden, 'garden')).toBe(true);
        expect(taxonAppliesTo(garden, 'all')).toBe(true);
        expect(taxonAppliesTo(garden, 'birds')).toBe(false);
        expect(taxonAppliesTo(birds, 'birds')).toBe(true);
        expect(taxonAppliesTo(birds, 'garden')).toBe(false);
    });

    it('is kept when the group came from a link and its visitors are not known', () => {
        expect(taxonAppliesTo({ id: 9, rank: 'order', name: null, scientificName: 'Rodentia' }, 'birds')).toBe(true);
    });
});
