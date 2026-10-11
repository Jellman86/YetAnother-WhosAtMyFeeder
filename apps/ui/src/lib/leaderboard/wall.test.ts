import { describe, expect, it } from 'vitest';
import type { Detection } from '../api';
import type { ShowcaseRow } from './showcase';
import { packTiles, readableInk, wallTiles, WALL_MINIMUM } from './wall';

const MINUTE = 60_000;
const SECOND = 1_000;
const base = Date.parse('2026-09-27T09:00:00Z');

const capture = (event: string, name: string, minutesAgo: number, extra: Partial<Detection> = {}, secondsAgo = 0): Detection => ({
    frigate_event: event,
    display_name: name,
    score: 0.8,
    detection_time: new Date(base - minutesAgo * MINUTE - secondsAgo * SECOND).toISOString(),
    camera_name: 'feeder',
    has_snapshot: true,
    ...extra
});

const row = (displayName: string, rank: number, extra: Partial<ShowcaseRow> = {}): ShowcaseRow => ({
    key: displayName,
    rank,
    displayName,
    subName: null,
    count: 10,
    photo: null,
    scientificName: null,
    taxaId: null,
    reference: null,
    flagged: false,
    ...extra
});

const options = { reviewThreshold: 0.4, filmEvents: new Set<string>() };

describe('the leaderboard wall', () => {
    it('folds frames of one approach into a single visit shown by its strongest frame', () => {
        const tiles = wallTiles(
            [capture('a3', 'Dunnock', 0, { score: 0.6 }), capture('a2', 'Dunnock', 0, { score: 0.95 }, 20), capture('a1', 'Dunnock', 0, {}, 40)],
            [row('Dunnock', 1)],
            options
        );
        expect(tiles).toHaveLength(1);
        expect(tiles[0]).toMatchObject({ frigateEvent: 'a2', score: 0.95, captures: 3, rank: 1, speciesKey: 'Dunnock' });
    });

    it('keeps visits more than a minute apart separate, newest first', () => {
        const tiles = wallTiles([capture('b2', 'Dunnock', 0), capture('b1', 'Dunnock', 30)], [row('Dunnock', 1)], options);
        expect(tiles.map((tile) => tile.frigateEvent)).toEqual(['b2', 'b1']);
    });

    it('leaves out hidden captures, ones with no stored photograph and unresolved birds', () => {
        const tiles = wallTiles(
            [
                capture('h', 'Dunnock', 0, { is_hidden: true }),
                capture('n', 'Dunnock', 20, { has_snapshot: false }),
                capture('u', 'Unknown Bird', 40),
                capture('ok', 'Dunnock', 60)
            ],
            [row('Dunnock', 1)],
            options
        );
        expect(tiles.map((tile) => tile.frigateEvent)).toEqual(['ok']);
    });

    it('never puts a species the rankings flag as probably misidentified on the wall', () => {
        const tiles = wallTiles(
            [capture('s', 'Eastern Gray Squirrel', 0), capture('d', 'Dunnock', 30)],
            [row('Dunnock', 1), row('Eastern Gray Squirrel', 5, { flagged: true })],
            options
        );
        expect(tiles.map((tile) => tile.name)).toEqual(['Dunnock']);
    });

    it('still shows a visit of a species the rankings do not name, with no species to open', () => {
        const [tile] = wallTiles([capture('x', 'Coal Tit', 0)], [row('Dunnock', 1)], options);
        expect(tile).toMatchObject({ name: 'Coal Tit', speciesKey: null, rank: null });
    });

    it('draws the leading species strongest visits large and nobody else', () => {
        const detections = [
            ...Array.from({ length: 33 }, (_unused, index) => capture(`d${index}`, 'Dunnock', index * 30, { score: (50 + index) / 100 })),
            capture('r0', 'European Robin', 15, { score: 0.99 })
        ];
        const tiles = wallTiles(detections, [row('Dunnock', 1), row('European Robin', 2)], options);
        const featured = tiles.filter((tile) => tile.featured);
        expect(featured).toHaveLength(4);
        expect(featured.every((tile) => tile.speciesKey === 'Dunnock')).toBe(true);
        expect(featured.map((tile) => Math.round(tile.score * 100)).sort()).toEqual([79, 80, 81, 82]);
    });

    it('draws fewer large tiles on a small wall, and none when there is too little to frame', () => {
        const few = (count: number) =>
            wallTiles(
                Array.from({ length: count }, (_unused, index) => capture(`s${index}`, 'Dunnock', index * 30)),
                [row('Dunnock', 1)],
                options
            ).filter((tile) => tile.featured).length;
        expect(few(7)).toBe(0);
        expect(few(16)).toBe(2);
        expect(few(40)).toBe(4);
    });

    it('marks a visit whose film is made and one that has a clip', () => {
        const [tile] = wallTiles([capture('f', 'Dunnock', 0, { has_clip: true })], [row('Dunnock', 1)], {
            ...options,
            filmEvents: new Set(['f'])
        });
        expect(tile).toMatchObject({ film: true, hasClip: true });
    });

    it('matches a capture to its species whatever the naming mode, by key, taxon or scientific name', () => {
        // The owner reads scientific names: the row's display name is Latin, the capture's label is not.
        const latin = row('Prunella modularis', 1, { key: 'Dunnock', subName: 'Dunnock', scientificName: 'Prunella modularis', taxaId: 13988 });
        const byKey = wallTiles([capture('k', 'Dunnock', 0)], [latin], options);
        expect(byKey[0]).toMatchObject({ speciesKey: 'Dunnock', rank: 1 });
        const byTaxon = wallTiles([capture('t', 'Hedge Accentor', 0, { taxa_id: 13988 })], [latin], options);
        expect(byTaxon[0]).toMatchObject({ speciesKey: 'Dunnock' });
        const byScientific = wallTiles([capture('s', 'Hedge Accentor', 0, { scientific_name: 'Prunella modularis' })], [latin], options);
        expect(byScientific[0]).toMatchObject({ speciesKey: 'Dunnock' });
    });

    it('keeps a flagged species off the wall even when only its taxon matches', () => {
        const flagged = row('Squirrel', 4, { scientificName: 'Sciurus carolinensis', flagged: true });
        const tiles = wallTiles([capture('f', 'Gray Squirrel', 0, { scientific_name: 'Sciurus carolinensis' })], [row('Dunnock', 1), flagged], options);
        expect(tiles).toEqual([]);
    });

    it('packs tiles into whole rows, a large tile taking a two by two block', () => {
        const tiles = wallTiles(
            Array.from({ length: 60 }, (_unused, index) => capture(`e${index}`, 'Dunnock', index * 30)),
            [row('Dunnock', 1)],
            { ...options, featured: 2 }
        );
        const packed = packTiles(tiles, 8, 5);
        const cells = packed.reduce((sum, tile) => sum + (tile.featured ? 4 : 1), 0);
        // Five rows of eight, nothing ragged and nothing over.
        expect(cells).toBe(40);
        expect(packed.filter((tile) => tile.featured)).toHaveLength(2);
        expect(packTiles(tiles, 8, 0)).toEqual([]);
    });

    it('never collapses a wall to a few tiles: every layout is whole or keeps what fits', () => {
        // A deterministic sweep of the shapes a feeder produces: wall widths, row counts, visit
        // counts and where the large tiles fall among them.
        let seed = 11;
        const next = (limit: number): number => {
            seed = (seed * 16807) % 2147483647;
            return seed % limit;
        };
        for (let run = 0; run < 400; run += 1) {
            const columns = 4 + next(11);
            const rows = 2 + next(8);
            const count = 6 + next(columns * rows * 2);
            const large = new Set(Array.from({ length: next(5) }, () => next(count)));
            const tiles = Array.from({ length: count }, (_unused, index) => ({ ...wallTiles([capture(`p${index}`, 'Dunnock', index * 30)], [row('Dunnock', 1)], options)[0], featured: large.has(index) }));
            const packed = packTiles(tiles, columns, rows);
            const cells = packed.reduce((sum, tile) => sum + (tile.featured ? 4 : 1), 0);
            expect(cells).toBeLessThanOrEqual(columns * rows);
            // Enough tiles to fill the grid at least once over never leaves fewer than a full row.
            if (count * 1 >= columns * rows) expect(cells).toBeGreaterThanOrEqual(columns * Math.max(1, rows - 2));
            // Without large tiles the wall is always whole rows, unless every visit fits in less than that.
            if (large.size === 0) expect(cells % columns === 0 || packed.length === tiles.length).toBe(true);
        }
    });

    it('keeps most of a small wall whichever visits are drawn large', () => {
        for (let first = 0; first < 24; first += 1) {
            const tiles = Array.from({ length: 24 }, (_unused, index) => ({
                ...wallTiles([capture(`q${index}`, 'Dunnock', index * 30)], [row('Dunnock', 1)], options)[0],
                featured: index === first || index === (first + 7) % 24 || index === (first + 15) % 24
            }));
            expect(packTiles(tiles, 8, 6).length).toBeGreaterThanOrEqual(21);
        }
    });

    it('drops a ragged last row instead of drawing a wall that ends in a gap', () => {
        const tiles = wallTiles(
            Array.from({ length: 13 }, (_unused, index) => capture(`g${index}`, 'Dunnock', index * 30)),
            [row('Dunnock', 1)],
            { ...options, featured: 0 }
        );
        expect(packTiles(tiles, 6, 5)).toHaveLength(12);
    });

    it('keeps every visit of a small wall rather than trimming it to nothing', () => {
        const tiles = wallTiles(
            Array.from({ length: 5 }, (_unused, index) => capture(`m${index}`, 'Dunnock', index * 30)),
            [row('Dunnock', 1)],
            { ...options, featured: 0 }
        );
        expect(packTiles(tiles, 10, 5)).toHaveLength(5);
    });

    it('never gives a large tile to a wall too narrow to hold one', () => {
        const tiles = wallTiles(
            Array.from({ length: 40 }, (_unused, index) => capture(`n${index}`, 'Dunnock', index * 30)),
            [row('Dunnock', 1)],
            { ...options, featured: 4 }
        );
        expect(packTiles(tiles, 3, 4)).toHaveLength(12);
    });

    it('reads the best ink on a species colour: dark on light colours, white on dark ones', () => {
        expect(readableInk('#eda100')).toBe('#020617');
        expect(readableInk('#4a3aa7')).toBe('#ffffff');
        expect(readableInk('#1baf7a')).toBe('#020617');
        expect(readableInk('#fff')).toBe('#020617');
    });

    it('needs at least a handful of visits to be a wall', () => {
        expect(WALL_MINIMUM).toBeGreaterThanOrEqual(6);
    });
});
