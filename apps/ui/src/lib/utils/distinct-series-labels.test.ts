import { describe, expect, it } from 'vitest';
import { distinctSeriesLabels } from './distinct-series-labels';

describe('distinctSeriesLabels', () => {
    it('leaves names that are already unique alone', () => {
        expect(
            distinctSeriesLabels([
                { name: 'Robin', qualifier: 'Erithacus rubecula' },
                { name: 'Wren', qualifier: 'Troglodytes troglodytes' }
            ])
        ).toEqual(['Robin', 'Wren']);
    });

    it('names both taxa when two translate to the same word', () => {
        expect(
            distinctSeriesLabels([
                { name: 'Kleiber', qualifier: 'Sitta europaea' },
                { name: 'Kleiber', qualifier: 'Sittidae' },
                { name: 'Dohle', qualifier: 'Coloeus monedula' }
            ])
        ).toEqual(['Kleiber (Sitta europaea)', 'Kleiber (Sittidae)', 'Dohle']);
    });

    it('stays unique when the names cannot be told apart by a qualifier', () => {
        expect(distinctSeriesLabels([{ name: 'Other' }, { name: 'Other', qualifier: null }, { name: 'Other', qualifier: 'Other' }])).toEqual([
            'Other',
            'Other 2',
            'Other 3'
        ]);
    });

    it('stays unique when a numbered name is already in use', () => {
        const labels = distinctSeriesLabels([{ name: 'Finch 2' }, { name: 'Finch' }, { name: 'Finch' }]);
        expect(labels).toEqual(['Finch 2', 'Finch', 'Finch 3']);
    });

    it('stays unique when one taxon appears twice', () => {
        expect(
            distinctSeriesLabels([
                { name: 'Kleiber', qualifier: 'Sittidae' },
                { name: 'Kleiber', qualifier: 'Sittidae' }
            ])
        ).toEqual(['Kleiber (Sittidae)', 'Kleiber (Sittidae) 2']);
    });
});
