import { describe, expect, it } from 'vitest';
import type { EventFilterSpecies } from '../api';
import { filterExplorerSpecies, shownExplorerSpecies } from './explorer-species';

function species(index: number, count: number): EventFilterSpecies {
    return {
        value: `species-${index}`,
        display_name: `Species ${String(index).padStart(2, '0')}`,
        scientific_name: `Scientific ${index}`,
        count
    };
}

describe('filterExplorerSpecies', () => {
    it('returns every recorded species instead of truncating the unfiltered facet', () => {
        const recordedSpecies = Array.from({ length: 18 }, (_, index) => species(index + 1, 18 - index));

        expect(filterExplorerSpecies(recordedSpecies, '')).toHaveLength(18);
    });

    it('searches common and scientific names before sorting matches by frequency', () => {
        const recordedSpecies: EventFilterSpecies[] = [
            { value: 'dunnock', display_name: 'Dunnock', scientific_name: 'Prunella modularis', count: 4 },
            { value: 'house-sparrow', display_name: 'House Sparrow', scientific_name: 'Passer domesticus', count: 9 },
            { value: 'tree-sparrow', display_name: 'Eurasian Tree Sparrow', scientific_name: 'Passer montanus', count: 2 }
        ];

        expect(filterExplorerSpecies(recordedSpecies, 'passer').map((item) => item.value)).toEqual([
            'house-sparrow',
            'tree-sparrow'
        ]);
    });
});

describe('shownExplorerSpecies', () => {
    const recorded = Array.from({ length: 20 }, (_, index) => species(index + 1, 20 - index));

    it('shows the most recorded species first and counts the rest behind Show all', () => {
        const shown = shownExplorerSpecies(recorded, { expanded: false, searching: false, selected: '' });
        expect(shown.items.map((item) => item.value)).toEqual(recorded.slice(0, 8).map((item) => item.value));
        expect(shown.more).toBe(12);
    });

    it('keeps a chosen species beyond the first eight in view', () => {
        const shown = shownExplorerSpecies(recorded, { expanded: false, searching: false, selected: 'species-15' });
        expect(shown.items.map((item) => item.value)).toContain('species-15');
        expect(shown.items).toHaveLength(9);
        expect(shown.more).toBe(11);
    });

    it('lists every species while expanded or searching', () => {
        for (const state of [{ expanded: true, searching: false }, { expanded: false, searching: true }]) {
            const shown = shownExplorerSpecies(recorded, { ...state, selected: '' });
            expect(shown.items).toHaveLength(20);
            expect(shown.more).toBe(0);
        }
    });

    it('offers nothing more when the list already fits', () => {
        expect(shownExplorerSpecies(recorded.slice(0, 9), { expanded: false, searching: false, selected: '' })).toEqual({
            items: recorded.slice(0, 9),
            more: 0
        });
    });
});
