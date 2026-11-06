import { describe, expect, it } from 'vitest';
import type { EventFilterSpecies } from '../api';
import { shownExplorerSpecies, sortExplorerSpecies } from './explorer-species';

function species(index: number, count: number): EventFilterSpecies {
    return {
        value: `species-${index}`,
        display_name: `Species ${String(index).padStart(2, '0')}`,
        scientific_name: `Scientific ${index}`,
        count
    };
}

describe('sortExplorerSpecies', () => {
    it('returns every recorded species, most recorded first, instead of truncating the facet', () => {
        const recordedSpecies = Array.from({ length: 18 }, (_, index) => species(index + 1, index + 1));
        const sorted = sortExplorerSpecies(recordedSpecies);
        expect(sorted).toHaveLength(18);
        expect(sorted[0].value).toBe('species-18');
    });

    it('orders equally recorded species by name', () => {
        const recordedSpecies: EventFilterSpecies[] = [
            { value: 'tree-sparrow', display_name: 'Eurasian Tree Sparrow', scientific_name: 'Passer montanus', count: 2 },
            { value: 'dunnock', display_name: 'Dunnock', scientific_name: 'Prunella modularis', count: 2 }
        ];
        expect(sortExplorerSpecies(recordedSpecies).map((item) => item.value)).toEqual(['dunnock', 'tree-sparrow']);
    });
});

describe('shownExplorerSpecies', () => {
    const recorded = Array.from({ length: 20 }, (_, index) => species(index + 1, 20 - index));

    it('shows the most recorded species first and counts the rest behind Show all', () => {
        const shown = shownExplorerSpecies(recorded, { expanded: false, selected: '' });
        expect(shown.items.map((item) => item.value)).toEqual(recorded.slice(0, 8).map((item) => item.value));
        expect(shown.more).toBe(12);
    });

    it('keeps a chosen species beyond the first eight in view', () => {
        const shown = shownExplorerSpecies(recorded, { expanded: false, selected: 'species-15' });
        expect(shown.items.map((item) => item.value)).toContain('species-15');
        expect(shown.items).toHaveLength(9);
        expect(shown.more).toBe(11);
    });

    it('lists every species while expanded', () => {
        const shown = shownExplorerSpecies(recorded, { expanded: true, selected: '' });
        expect(shown.items).toHaveLength(20);
        expect(shown.more).toBe(0);
    });

    it('offers nothing more when the list already fits', () => {
        expect(shownExplorerSpecies(recorded.slice(0, 9), { expanded: false, selected: '' })).toEqual({
            items: recorded.slice(0, 9),
            more: 0
        });
    });
});
