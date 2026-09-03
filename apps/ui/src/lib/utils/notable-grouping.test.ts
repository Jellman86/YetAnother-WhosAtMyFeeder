import { describe, expect, it } from 'vitest';
import { groupNotableObservations } from './notable-grouping';

const shrike = (observed_at: string, location_name = 'The Avenue Country Park DWT NR', extra = {}) => ({
    common_name: 'Red-backed Shrike',
    scientific_name: 'Lanius collurio',
    observed_at,
    location_name,
    thumbnail_url: null as string | null,
    ...extra
});

describe('groupNotableObservations', () => {
    it('folds four reports of one bird into one card that says four saw it', () => {
        const groups = groupNotableObservations([
            shrike('2026-09-03 09:10'),
            shrike('2026-09-03 08:40'),
            shrike('2026-09-03 11:05', 'Carsington Water'),
            shrike('2026-09-03 07:55')
        ]);
        expect(groups).toHaveLength(1);
        const [group] = groups;
        expect(group.reports).toBe(4);
        expect(group.locations).toEqual(['The Avenue Country Park DWT NR', 'Carsington Water']);
        // The most recent report fronts the card, whatever order eBird sent them in.
        expect(group.latest.observed_at).toBe('2026-09-03 11:05');
    });

    it('keeps different species apart and in the order they arrived', () => {
        const groups = groupNotableObservations([
            shrike('2026-09-03 09:10'),
            { common_name: 'Hoopoe', scientific_name: 'Upupa epops', observed_at: '2026-09-02 15:00', location_name: 'Ogston' },
            shrike('2026-09-03 08:40')
        ]);
        expect(groups.map((g) => g.latest.common_name)).toEqual(['Red-backed Shrike', 'Hoopoe']);
        expect(groups.map((g) => g.reports)).toEqual([2, 1]);
    });

    it('groups on the scientific name, and falls back to the common name when there is none', () => {
        const groups = groupNotableObservations([
            { common_name: 'Shrike', scientific_name: 'Lanius collurio', observed_at: '2026-09-03 09:00' },
            { common_name: 'Red-backed Shrike', scientific_name: 'LANIUS COLLURIO ', observed_at: '2026-09-03 08:00' },
            { common_name: 'Mystery bird', scientific_name: null, observed_at: '2026-09-03 07:00' },
            { common_name: 'mystery bird', scientific_name: null, observed_at: '2026-09-03 06:00' }
        ]);
        expect(groups.map((g) => g.reports)).toEqual([2, 2]);
    });

    it('takes a thumbnail from any report that has one', () => {
        const groups = groupNotableObservations([
            shrike('2026-09-03 09:10'),
            shrike('2026-09-03 08:40', undefined, { thumbnail_url: 'https://img/shrike.jpg' })
        ]);
        expect(groups[0].thumbnail_url).toBe('https://img/shrike.jpg');
    });
});
