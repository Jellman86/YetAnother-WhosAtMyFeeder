import { describe, expect, it } from 'vitest';
import type { SearchResult } from '../api';
import { speciesPickerNames, withoutCurrentSpecies } from './species-picker';

const result = (overrides: Partial<SearchResult>): SearchResult => ({
    id: 'Prunella modularis',
    display_name: 'Prunella modularis',
    scientific_name: 'Prunella modularis',
    common_name: 'Dunnock',
    ...overrides
});

describe('species picker rows', () => {
    it('leads with the common name and keeps the scientific name beneath', () => {
        expect(speciesPickerNames(result({}))).toEqual({ primary: 'Dunnock', secondary: 'Prunella modularis' });
    });

    it('falls back to the label when taxonomy has not resolved', () => {
        expect(
            speciesPickerNames(result({ common_name: null, scientific_name: null, display_name: 'Odd label' }))
        ).toEqual({ primary: 'Odd label', secondary: null });
    });
});

describe('choosing a different species', () => {
    const dunnock = result({});
    const goldcrest = result({
        id: 'Regulus regulus',
        display_name: 'Regulus regulus',
        scientific_name: 'Regulus regulus',
        common_name: 'Goldcrest'
    });

    it('drops the species the record already carries, whichever name it is stored under', () => {
        expect(withoutCurrentSpecies([dunnock, goldcrest], { display_name: 'Dunnock' })).toEqual([goldcrest]);
        expect(withoutCurrentSpecies([dunnock, goldcrest], { scientific_name: 'regulus regulus' })).toEqual([dunnock]);
    });

    it('keeps every row when the record has no name to compare', () => {
        expect(withoutCurrentSpecies([dunnock, goldcrest], null)).toEqual([dunnock, goldcrest]);
    });
});
