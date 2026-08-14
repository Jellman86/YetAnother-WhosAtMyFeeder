import { describe, expect, it } from 'vitest';
import type { EventFilterSpecies } from '../api';
import { filterExplorerSpecies } from './explorer-species';

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
