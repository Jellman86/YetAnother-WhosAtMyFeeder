import { describe, expect, it } from 'vitest';
import {
    byRank,
    formatScientificName,
    isItalicRank,
    namingStyle,
    taxonNames
} from './nomenclature';

const text = (rank: string, name: string) => formatScientificName(rank, name).map((part) => part.text).join('');

describe('isItalicRank', () => {
    it('italicises the genus and every rank beneath it', () => {
        for (const rank of ['genus', 'subgenus', 'species', 'subspecies', 'variety', 'form']) {
            expect(isItalicRank(rank)).toBe(true);
        }
    });

    it('leaves the family and every rank above it upright', () => {
        for (const rank of ['kingdom', 'phylum', 'subphylum', 'megaclass', 'class', 'order', 'superfamily', 'family', 'subfamily', 'tribe']) {
            expect(isItalicRank(rank)).toBe(false);
        }
    });

    it('reads the rank without regard to case or stray space', () => {
        expect(isItalicRank(' Species ')).toBe(true);
        expect(isItalicRank('FAMILY')).toBe(false);
    });

    it('leaves a rank it does not know upright rather than guess', () => {
        expect(isItalicRank('clade')).toBe(false);
        expect(isItalicRank('')).toBe(false);
    });
});

describe('formatScientificName', () => {
    it('sets a binomial in italics with the genus capitalised and the epithet in lower case', () => {
        expect(formatScientificName('species', 'prunella MODULARIS')).toEqual([{ text: 'Prunella modularis', italic: true }]);
    });

    it('sets a genus alone in italics', () => {
        expect(formatScientificName('genus', 'prunella')).toEqual([{ text: 'Prunella', italic: true }]);
    });

    it('sets a family, an order and a class upright and capitalised', () => {
        expect(formatScientificName('family', 'prunellidae')).toEqual([{ text: 'Prunellidae', italic: false }]);
        expect(formatScientificName('order', 'PASSERIFORMES')).toEqual([{ text: 'Passeriformes', italic: false }]);
        expect(formatScientificName('class', 'Aves')).toEqual([{ text: 'Aves', italic: false }]);
    });

    it('sets a trinomial in italics', () => {
        expect(text('subspecies', 'Motacilla alba yarrellii')).toBe('Motacilla alba yarrellii');
        expect(formatScientificName('subspecies', 'Motacilla alba yarrellii')[0].italic).toBe(true);
    });

    it('keeps a connecting term such as subsp. or var. upright between italic names', () => {
        expect(formatScientificName('subspecies', 'Ursus arctos subsp. horribilis')).toEqual([
            { text: 'Ursus arctos', italic: true },
            { text: ' subsp.', italic: false },
            { text: ' horribilis', italic: true }
        ]);
    });

    it('keeps a hybrid sign upright', () => {
        expect(formatScientificName('species', 'Anas × platyrhynchos')).toEqual([
            { text: 'Anas', italic: true },
            { text: ' ×', italic: false },
            { text: ' platyrhynchos', italic: true }
        ]);
    });

    it('capitalises a subgenus in brackets', () => {
        expect(text('species', 'larus (chroicocephalus) ridibundus')).toBe('Larus (Chroicocephalus) ridibundus');
    });

    it('keeps an abbreviated genus as written', () => {
        expect(text('species', 'P. modularis')).toBe('P. modularis');
    });

    it('collapses stray space and returns nothing for an empty name', () => {
        expect(text('species', '  Prunella   modularis ')).toBe('Prunella modularis');
        expect(formatScientificName('species', '   ')).toEqual([]);
    });

    it('sets a name of an unknown rank upright, as written apart from its first capital', () => {
        expect(formatScientificName('clade', 'neoaves')).toEqual([{ text: 'Neoaves', italic: false }]);
    });
});

describe('byRank', () => {
    it('orders a lineage from the kingdom down to the species, whatever order it arrives in', () => {
        const ranks = ['species', 'class', 'genus', 'kingdom', 'family', 'phylum', 'order'].map((rank) => ({ rank }));
        expect([...ranks].sort(byRank).map((taxon) => taxon.rank)).toEqual(['kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'species']);
    });

    it('places intermediate ranks between the principal ones', () => {
        const ranks = ['class', 'megaclass', 'subphylum', 'phylum', 'subfamily', 'family'].map((rank) => ({ rank }));
        expect([...ranks].sort(byRank).map((taxon) => taxon.rank)).toEqual(['phylum', 'subphylum', 'megaclass', 'class', 'family', 'subfamily']);
    });

    it('keeps a rank it does not know where it was, after the ranks it does', () => {
        const ranks = [{ rank: 'clade', id: 1 }, { rank: 'family', id: 2 }, { rank: 'order', id: 3 }];
        expect([...ranks].sort(byRank).map((taxon) => taxon.id)).toEqual([3, 2, 1]);
    });
});

describe('namingStyle', () => {
    it('maps the two naming settings onto the three styles', () => {
        expect(namingStyle(true, false)).toBe('standard');
        expect(namingStyle(true, true)).toBe('hobbyist');
        expect(namingStyle(false, false)).toBe('scientific');
        expect(namingStyle(false, true)).toBe('scientific');
    });
});

describe('taxonNames', () => {
    const dunnock = { rank: 'species', scientific_name: 'Prunella modularis', name: 'Dunnock' };
    const accentors = { rank: 'family', scientific_name: 'Prunellidae', name: 'Accentors' };
    const prunella = { rank: 'genus', scientific_name: 'Prunella', name: null };

    it('leads with the common name and gives the scientific name beneath it in the standard style', () => {
        const names = taxonNames(dunnock, 'standard');
        expect(names.primary).toMatchObject({ kind: 'common', text: 'Dunnock', parts: [{ text: 'Dunnock', italic: false }] });
        expect(names.secondary).toMatchObject({ kind: 'scientific', text: 'Prunella modularis', parts: [{ text: 'Prunella modularis', italic: true }] });
    });

    it('leads with the scientific name in the hobbyist style, the common name beneath', () => {
        const names = taxonNames(accentors, 'hobbyist');
        expect(names.primary).toMatchObject({ kind: 'scientific', text: 'Prunellidae', parts: [{ text: 'Prunellidae', italic: false }] });
        expect(names.secondary).toMatchObject({ kind: 'common', text: 'Accentors' });
    });

    it('shows only the scientific name in the strictly scientific style', () => {
        const names = taxonNames(dunnock, 'scientific');
        expect(names.primary.text).toBe('Prunella modularis');
        expect(names.secondary).toBeNull();
    });

    it('falls back to the italic scientific name when a genus has no common name', () => {
        const names = taxonNames(prunella, 'standard');
        expect(names.primary).toMatchObject({ kind: 'scientific', text: 'Prunella', parts: [{ text: 'Prunella', italic: true }] });
        expect(names.secondary).toBeNull();
    });

    it('drops a common name that only repeats the scientific one', () => {
        expect(taxonNames({ rank: 'order', scientific_name: 'Passeriformes', name: 'Passeriformes Order' }, 'standard')).toMatchObject({
            primary: { kind: 'common', text: 'Passeriformes Order' },
            secondary: null
        });
        expect(taxonNames({ rank: 'genus', scientific_name: 'Vulpes', name: 'vulpes' }, 'standard')).toMatchObject({
            primary: { kind: 'scientific', text: 'Vulpes' },
            secondary: null
        });
    });

    it('treats a blank common name as none', () => {
        expect(taxonNames({ ...dunnock, name: '  ' }, 'standard').primary.kind).toBe('scientific');
    });
});
