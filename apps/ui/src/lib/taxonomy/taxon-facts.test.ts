import { describe, expect, it } from 'vitest';
import type { TaxonFacts } from '../api/taxonomy';
import {
    authorityText,
    factsBatches,
    groupOtherNames,
    heardCount,
    iucnCategory,
    languageLabel,
    ownPhoto,
    visitsView,
    type FactEntry
} from './taxon-facts';

const facts = (overrides: Partial<TaxonFacts> = {}): TaxonFacts => ({
    taxon_id: 50,
    rank: 'species',
    visits: 3,
    species_seen: 1,
    first_seen: '2025-03-14T07:12:00Z',
    last_seen: '2026-11-02T08:41:00Z',
    heard: 12,
    last_heard: '2026-11-02T08:41:00Z',
    sources: ['camera'],
    photo: null,
    ...overrides
});
const ready = (overrides: Partial<TaxonFacts> = {}): FactEntry => ({ state: 'ready', facts: facts(overrides) });

describe('facts are asked for in batches of taxa not already known', () => {
    it('skips what is loaded or on its way, asks each once, and splits at the route limit', () => {
        const entries = new Map<number, FactEntry>([
            [1, ready()],
            [2, { state: 'loading' }],
            [3, { state: 'failed' }],
            [4, { state: 'absent' }]
        ]);
        expect(factsBatches([1, 2, 3, 4, 5, 5, 6, 7], entries, { limit: 2 })).toEqual([[5, 6], [7]]);
    });

    it('retries a failed taxon only when asked to', () => {
        const entries = new Map<number, FactEntry>([[3, { state: 'failed' }]]);
        expect(factsBatches([3], entries)).toEqual([]);
        expect(factsBatches([3], entries, { retryFailed: true })).toEqual([[3]]);
    });
});

describe('what a card says about visits', () => {
    const sameDay = (a: string, b: string) => a.slice(0, 10) === b.slice(0, 10);

    it('is loading until the facts arrive, and says so when they fail', () => {
        expect(visitsView(undefined, sameDay)).toEqual({ kind: 'loading' });
        expect(visitsView({ state: 'loading' }, sameDay)).toEqual({ kind: 'loading' });
        expect(visitsView({ state: 'failed' }, sameDay)).toEqual({ kind: 'failed' });
    });

    it('hides the fact when the catalogue does not hold the taxon', () => {
        expect(visitsView({ state: 'absent' }, sameDay)).toEqual({ kind: 'unknown' });
    });

    it('states no visits in words rather than a zero', () => {
        expect(visitsView(ready({ visits: 0, species_seen: 0, first_seen: null, last_seen: null }), sameDay)).toEqual({ kind: 'none' });
    });

    it('gives the visits and the span, and folds a single day into one date', () => {
        expect(visitsView(ready(), sameDay)).toEqual({
            kind: 'seen',
            visits: 3,
            speciesSeen: 1,
            firstSeen: '2025-03-14T07:12:00Z',
            lastSeen: '2026-11-02T08:41:00Z',
            sameDay: false
        });
        const oneDay = visitsView(ready({ first_seen: '2026-11-02T07:00:00Z', sources: ['garden'] }), sameDay);
        expect(oneDay).toMatchObject({ kind: 'seen', sameDay: true });
    });
});

describe('the heard badge and the photograph', () => {
    it('shows calls only when BirdNET recorded some and audio is shared', () => {
        expect(heardCount(ready())).toBe(12);
        expect(heardCount(ready({ heard: 0 }))).toBeNull();
        expect(heardCount(ready({ heard: null }))).toBeNull();
        expect(heardCount({ state: 'loading' })).toBeNull();
    });

    it("is this install's photo only once the facts say there is one", () => {
        const photo = { url: '/api/about/showcase/a.jpg', kind: 'camera' as const, species_id: 50, scientific_name: 'Prunella modularis', taken_at: '2026-11-02T08:41:00Z' };
        expect(ownPhoto(ready({ photo }))).toEqual(photo);
        expect(ownPhoto(ready())).toBeNull();
        expect(ownPhoto({ state: 'failed' })).toBeNull();
    });
});

describe('an authority is shown exactly as the catalogue stores it', () => {
    it('keeps parentheses the source wrote and never adds them', () => {
        expect(authorityText('(Linnaeus, 1758)')).toBe('(Linnaeus, 1758)');
        expect(authorityText('Vigors, 1831')).toBe('Vigors, 1831');
    });

    it('tidies whitespace and treats a blank one as unknown', () => {
        expect(authorityText('  Linnaeus,   1758 ')).toBe('Linnaeus, 1758');
        expect(authorityText('   ')).toBeNull();
        expect(authorityText(null)).toBeNull();
        expect(authorityText(undefined)).toBeNull();
    });
});

describe('other names are grouped by language', () => {
    it('names each language in the reader’s language, sorted by that name, preferred name first', () => {
        const groups = groupOtherNames(
            [
                { language: 'fr', name: 'Accenteur mouchet', preferred: true },
                { language: 'fr', name: 'Mouchet', preferred: false },
                { language: 'de', name: 'Heckenbraunelle', preferred: true }
            ],
            (tag) => languageLabel(tag, 'en')
        );
        expect(groups).toEqual([
            { language: 'fr', label: 'French', names: ['Accenteur mouchet', 'Mouchet'] },
            { language: 'de', label: 'German', names: ['Heckenbraunelle'] }
        ]);
    });

    it('labels a language the browser cannot name by its tag', () => {
        expect(languageLabel('de', 'fr')).toBe('Allemand');
        expect(languageLabel('zz-invalid-', 'en')).toBe('zz-invalid-');
    });
});

describe('a conservation status is one of the IUCN categories or nothing', () => {
    it('accepts the eight categories and nothing else', () => {
        expect(['DD', 'LC', 'NT', 'VU', 'EN', 'CR', 'EW', 'EX'].map(iucnCategory)).toEqual(['DD', 'LC', 'NT', 'VU', 'EN', 'CR', 'EW', 'EX']);
        expect(iucnCategory('lc')).toBe('LC');
        expect(iucnCategory('secure')).toBeNull();
        expect(iucnCategory(null)).toBeNull();
    });
});
