import { describe, expect, it } from 'vitest';
import { buildShowcaseRows, portraitFor, shareSegments, spotlightGroups } from './showcase';

const portraits = [
    { species: 'Dunnock', scientific_name: 'Prunella modularis', taxa_id: 13988, frigate_event: 'd1', image_url: '/api/about/showcase/d1.jpg', film_url: '/api/about/showcase/d1.webm' },
    { species: 'Erithacus rubecula', scientific_name: 'Erithacus rubecula', taxa_id: null, frigate_event: 'r1', image_url: '/api/about/showcase/r1.jpg' }
];

const row = (species: string, extra: Record<string, unknown> = {}) => ({
    species,
    displayName: species,
    subName: null,
    count: 10,
    prev_count: 4,
    delta: 6,
    percent: 150,
    heard_count: 0,
    heard_delta: null,
    heard_percent: null,
    heard_avg: null,
    heard_last: null,
    last_seen: '2026-09-12T07:00:00Z',
    avg_confidence: 0.83,
    audio_only: false,
    ...extra
});

describe('the leaderboard showcase rows', () => {
    it('matches a species to its own photograph by taxon first, then by any of its names', () => {
        expect(portraitFor(row('Dunnock', { taxa_id: 13988 }), portraits)?.image_url).toBe('/api/about/showcase/d1.jpg');
        expect(portraitFor(row('European Robin', { scientific_name: 'Erithacus rubecula' }), portraits)?.image_url).toBe('/api/about/showcase/r1.jpg');
        expect(portraitFor(row('Coal Tit'), portraits)).toBeNull();
    });

    it('carries a reference image only as a labelled stand-in', () => {
        const rows = buildShowcaseRows([row('Coal Tit'), row('Dunnock', { taxa_id: 13988 })], {
            sourceMode: 'seen',
            portraits,
            referenceFor: (species) => (species === 'Coal Tit' ? { url: 'https://ref/coal.jpg', source: 'wikipedia' } : { url: null, source: null })
        });
        expect(rows[0]).toMatchObject({ key: 'Coal Tit', photo: null, reference: 'https://ref/coal.jpg' });
        expect(rows[1]).toMatchObject({ key: 'Dunnock', photo: '/api/about/showcase/d1.jpg', scientificName: null, taxaId: 13988, reference: null });
    });

    it('keeps every ranked species with its table rank', () => {
        const many = Array.from({ length: 20 }, (_, i) => row(`Species ${i}`, i === 1 ? { scientific_name: 'Parus major' } : {}));
        const rows = buildShowcaseRows(many, { sourceMode: 'seen', portraits: [], referenceFor: () => ({ url: null, source: null }) });
        expect(rows).toHaveLength(20);
        expect(rows[0]).toMatchObject({ key: 'Species 0', rank: 1, count: 10 });
        expect(rows[1]).toMatchObject({ rank: 2 });
    });
});

describe('the showcase flag', () => {
    it('carries the page\'s misidentification flag onto the tiles, and nothing when there is no rule', () => {
        const rows = buildShowcaseRows([row('Dunnock'), row('Golden-crowned Sparrow')], {
            sourceMode: 'seen',
            portraits: [],
            referenceFor: () => ({ url: null, source: null }),
            isFlagged: (candidate) => candidate.species === 'Golden-crowned Sparrow'
        });
        expect(rows.map((item) => item.flagged)).toEqual([false, true]);
        const unflagged = buildShowcaseRows([row('Dunnock')], { sourceMode: 'seen', portraits: [], referenceFor: () => ({ url: null, source: null }) });
        expect(unflagged[0].flagged).toBe(false);
    });
});

const ranked = (counts: Array<[string, number, boolean?]>) =>
    buildShowcaseRows(
        counts.map(([species, count]) => row(species, { count })),
        {
            sourceMode: 'seen',
            portraits: [],
            referenceFor: () => ({ url: null, source: null }),
            isFlagged: (candidate) => counts.find(([species]) => species === candidate.species)?.[2] === true
        }
    );

describe('the spotlight groups and share bar', () => {
    const rows = ranked([
        ['Dunnock', 251],
        ['European Robin', 32],
        ['Great Tit', 6],
        ['Golden-crowned Sparrow', 4, true],
        ['Goldcrest', 3],
        ['Eurasian Wren', 1]
    ]);

    it('keeps flagged species out of the tour and the list, and sums the rest instead of dropping them', () => {
        const groups = spotlightGroups(rows, 3);
        expect(groups.list.map((item) => item.key)).toEqual(['Dunnock', 'European Robin', 'Great Tit']);
        // Ranks stay the table's: the flagged fourth does not renumber the fifth.
        expect(groups.list.map((item) => item.rank)).toEqual([1, 2, 3]);
        expect(groups.others).toMatchObject({ species: 2, count: 4 });
        expect(groups.others.members).toHaveLength(2);
        expect(groups.checks.map((item) => item.key)).toEqual(['Golden-crowned Sparrow']);
    });

    it('fills the bar exactly: listed species, everyone else, then what needs a check', () => {
        const segments = shareSegments(rows, 3);
        expect(segments.map((segment) => [segment.key, segment.kind, segment.count])).toEqual([
            ['Dunnock', 'species', 251],
            ['European Robin', 'species', 32],
            ['Great Tit', 'species', 6],
            ['others', 'others', 4],
            ['checks', 'checks', 4]
        ]);
        expect(segments.reduce((sum, segment) => sum + segment.percent, 0)).toBeCloseTo(100, 6);
        expect(segments[0].percent).toBeCloseTo((251 / 297) * 100, 6);
    });

    it('draws nothing for an empty window', () => {
        expect(shareSegments(ranked([['Dunnock', 0]]))).toEqual([]);
    });
});
