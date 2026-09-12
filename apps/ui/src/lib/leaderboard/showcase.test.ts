import { describe, expect, it } from 'vitest';
import { buildShowcaseRows, portraitFor, SHOWCASE_TILES } from './showcase';

const portraits = [
    { species: 'Dunnock', scientific_name: 'Prunella modularis', taxa_id: 13988, frigate_event: 'd1', image_url: '/api/about/showcase/d1.jpg' },
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
        expect(portraitFor(row('Dunnock', { taxa_id: 13988 }), portraits)).toBe('/api/about/showcase/d1.jpg');
        expect(portraitFor(row('European Robin', { scientific_name: 'Erithacus rubecula' }), portraits)).toBe('/api/about/showcase/r1.jpg');
        expect(portraitFor(row('Coal Tit'), portraits)).toBeNull();
    });

    it('carries a reference image only as a labelled stand-in, and no trend for the all-time span', () => {
        const rows = buildShowcaseRows([row('Coal Tit'), row('Dunnock', { taxa_id: 13988 })], {
            span: 'all',
            sourceMode: 'seen',
            portraits,
            referenceFor: (species) => (species === 'Coal Tit' ? { url: 'https://ref/coal.jpg', source: 'wikipedia' } : { url: null, source: null })
        });
        expect(rows[0]).toMatchObject({ key: 'Coal Tit', photo: null, reference: 'https://ref/coal.jpg', referenceSource: 'wikipedia', trend: null, delta: null });
        expect(rows[1]).toMatchObject({ key: 'Dunnock', photo: '/api/about/showcase/d1.jpg', reference: null });
    });

    it('takes the leader plus one tile per slot, in rank order', () => {
        const many = Array.from({ length: 20 }, (_, i) => row(`Species ${i}`));
        const rows = buildShowcaseRows(many, { span: 'month', sourceMode: 'seen', portraits: [], referenceFor: () => ({ url: null, source: null }) });
        expect(rows).toHaveLength(SHOWCASE_TILES + 1);
        expect(rows[0].key).toBe('Species 0');
        expect(rows[0].trend).toBe('+6');
    });
});
