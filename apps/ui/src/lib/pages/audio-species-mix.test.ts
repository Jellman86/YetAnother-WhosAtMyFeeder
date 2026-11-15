import { describe, expect, it } from 'vitest';

import { audioSpeciesMix } from './audio-species-mix';

const species = (count: number, name: string) => ({ species: name, count });

describe('the Audio history species mix', () => {
    it('adds the species it does not name as one slice, so the ring totals the page figure', () => {
        const mix = audioSpeciesMix([species(100, 'Robin'), species(62, 'Wren')], 420, 'Other species', 8);
        expect(mix.map((slice) => slice.count)).toEqual([100, 62, 258]);
        expect(mix.at(-1)).toEqual({ species: 'Other species', count: 258, other: true });
        expect(mix.reduce((sum, slice) => sum + slice.count, 0)).toBe(420);
    });

    it('names at most the given number of species and folds the rest into the other slice', () => {
        const mix = audioSpeciesMix([species(5, 'A'), species(4, 'B'), species(3, 'C')], 12, 'Other species', 2);
        expect(mix.map((slice) => slice.species)).toEqual(['A', 'B', 'Other species']);
        expect(mix.at(-1)?.count).toBe(3);
    });

    it('draws no other slice when the named species are everything that was heard', () => {
        expect(audioSpeciesMix([species(3, 'Robin')], 3, 'Other species', 8)).toEqual([{ species: 'Robin', count: 3, other: false }]);
        // A total that was not measured, or is behind the species list, never invents a negative slice.
        expect(audioSpeciesMix([species(3, 'Robin')], undefined, 'Other species', 8)).toHaveLength(1);
        expect(audioSpeciesMix([species(3, 'Robin')], 2, 'Other species', 8)).toHaveLength(1);
    });
});
