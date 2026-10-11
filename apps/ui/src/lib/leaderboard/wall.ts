import type { Detection } from '../api';
import { groupDetectionsIntoVisits } from '../utils/visit-grouping';
import type { ShowcaseRow } from './showcase';

/** Fewer visits than this make a patch, not a wall. */
export const WALL_MINIMUM = 8;

/** Most visits of the leading species drawn large, and how many visits each large tile needs the wall to hold. */
const WALL_FEATURED = 4;
const VISITS_PER_FEATURED = 8;

const UNRESOLVED_LABEL = 'unknown bird';

/** One visit on the wall: the photograph that best shows it, and what a pop-out says about it. */
export interface WallTile {
    key: string;
    frigateEvent: string;
    name: string;
    /** The ranked species this visit belongs to, or null when the rankings do not name it. */
    speciesKey: string | null;
    subName: string | null;
    rank: number | null;
    score: number;
    at: string;
    camera: string;
    captures: number;
    hasClip: boolean;
    /** A few silent seconds of the visit are made, so the pop-out can play them. */
    film: boolean;
    /** Drawn four times the area: the leading species' strongest visits. */
    featured: boolean;
}

export interface WallOptions {
    reviewThreshold: number | null;
    /** Visits whose film is made, from the portraits route. */
    filmEvents: ReadonlySet<string>;
    featured?: number;
}

/**
 * Fold a newest-first capture list into visits (the shared visit rule, so the wall and the rankings
 * agree) and describe each as a tile. A species the
 * rankings flag as probably misidentified never takes a place on the wall, a capture without a
 * stored photograph has nothing to show, and the leading species' best visits are drawn large.
 */
export function wallTiles(detections: readonly Detection[], rows: readonly ShowcaseRow[], options: WallOptions): WallTile[] {
    const lower = (value: string | null | undefined): string => (value ?? '').trim().toLowerCase();
    // A capture carries the classifier's label; the row's name follows the owner's naming mode (common,
    // scientific, renamed). So a capture is matched by the row's own key first, then by any of its
    // names, then by taxon or scientific name, the way the portraits are.
    const byKey = new Map(rows.map((row) => [lower(row.key), row]));
    const byName = new Map(rows.map((row) => [lower(row.displayName), row]));
    const byScientific = new Map(rows.filter((row) => row.scientificName).map((row) => [lower(row.scientificName), row]));
    const byTaxon = new Map(rows.filter((row) => row.taxaId).map((row) => [row.taxaId, row]));
    const rowFor = (label: string, scientific: string | null | undefined, taxon: number | null | undefined): ShowcaseRow | null =>
        byKey.get(lower(label)) ??
        byName.get(lower(label)) ??
        (taxon ? byTaxon.get(taxon) : undefined) ??
        (scientific ? byScientific.get(lower(scientific)) : undefined) ??
        null;
    const shown = detections.filter(
        (detection) =>
            !detection.is_hidden &&
            detection.has_snapshot !== false &&
            detection.display_name.trim().toLowerCase() !== UNRESOLVED_LABEL
    );
    const visits = groupDetectionsIntoVisits(shown, { reviewThreshold: options.reviewThreshold });

    const tiles = visits.flatMap((visit): WallTile[] => {
        const best = visit.best;
        const row = rowFor(visit.species, best.scientific_name, best.taxa_id);
        if (row?.flagged) return [];
        return [
            {
                key: visit.key,
                frigateEvent: best.frigate_event,
                name: row?.displayName ?? visit.species,
                speciesKey: row?.key ?? null,
                subName: row?.subName ?? null,
                rank: row?.rank ?? null,
                score: best.score ?? 0,
                at: visit.endTime,
                camera: visit.camera,
                captures: visit.captureCount ?? visit.frames.length,
                hasClip: visit.frames.some((frame) => frame.has_clip === true),
                film: options.filmEvents.has(best.frigate_event),
                featured: false
            }
        ];
    });

    const leader = rows.find((row) => !row.flagged);
    if (!leader) return tiles;
    const strongest = tiles
        .filter((tile) => tile.speciesKey === leader.key)
        .sort((a, b) => b.score - a.score || Date.parse(b.at) - Date.parse(a.at))
        .slice(0, options.featured ?? Math.min(WALL_FEATURED, Math.floor(tiles.length / VISITS_PER_FEATURED)));
    const featured = new Set(strongest.map((tile) => tile.key));
    return tiles.map((tile) => (featured.has(tile.key) ? { ...tile, featured: true } : tile));
}

/**
 * The tiles that fill a grid `columns` wide and at most `maxRows` tall, in order, laid out the
 * way CSS dense auto-placement lays them out (each tile takes the first free spot, scanning row
 * by row, so a small tile fills a hole a large one left). A large tile that cannot fit is
 * skipped. Placement of a tile depends only on the tiles before it, so one pass lays out every
 * prefix, and the wall is the longest prefix with no hole in it: a wall that ends in a ragged row
 * reads as unfinished. Large tiles make the area awkward (each is four squares), so the layout is
 * also tried with the last few large tiles drawn small, and the better wall wins. When no
 * prefix is whole (a handful of visits) every placed tile is kept. Pure, so the wall and its tests
 * agree on exactly what is drawn.
 */
export function packTiles(tiles: readonly WallTile[], columns: number, maxRows: number): WallTile[] {
    if (columns < 1 || maxRows < 1) return [];
    const largeAt = tiles.flatMap((tile, index) => (tile.featured && columns >= 4 ? [index] : []));
    // With enough visits to fill the grid the fullest wall wins and the large tiles stay; with fewer,
    // the wall that shows the most visits does, so no visit is dropped just to keep a large tile.
    const crowded = tiles.length + 3 * largeAt.length >= columns * maxRows;
    let best: { tiles: WallTile[]; cells: number } | null = null;
    for (let demoted = 0; demoted <= Math.min(largeAt.length, 4); demoted += 1) {
        const small = new Set(largeAt.slice(largeAt.length - demoted));
        const candidate = layout(
            tiles.map((tile, index) => (small.has(index) ? { ...tile, featured: false } : tile)),
            columns,
            maxRows
        );
        if (best === null || (crowded ? candidate.cells > best.cells : candidate.tiles.length > best.tiles.length)) best = candidate;
    }
    return best?.tiles ?? [];
}

function layout(tiles: readonly WallTile[], columns: number, maxRows: number): { tiles: WallTile[]; cells: number } {
    const occupied: boolean[][] = Array.from({ length: maxRows }, () => Array<boolean>(columns).fill(false));
    const free = (row: number, column: number, size: number): boolean => {
        for (let r = row; r < row + size; r += 1) for (let c = column; c < column + size; c += 1) if (occupied[r][c]) return false;
        return true;
    };
    const placed: { tile: WallTile; filled: number; whole: boolean }[] = [];
    let filled = 0;
    let bottom = 0;
    for (const tile of tiles) {
        if (filled >= columns * maxRows) break;
        const size = tile.featured && columns >= 4 ? 2 : 1;
        let spot: [number, number] | null = null;
        for (let row = 0; row + size <= maxRows && spot === null; row += 1) {
            for (let column = 0; column + size <= columns; column += 1) {
                if (free(row, column, size)) {
                    spot = [row, column];
                    break;
                }
            }
        }
        if (spot === null) continue;
        for (let r = spot[0]; r < spot[0] + size; r += 1) for (let c = spot[1]; c < spot[1] + size; c += 1) occupied[r][c] = true;
        filled += size * size;
        bottom = Math.max(bottom, spot[0] + size);
        placed.push({ tile, filled, whole: filled === bottom * columns });
    }
    for (let length = placed.length; length > 0; length -= 1) {
        const entry = placed[length - 1];
        if (entry.whole) return { tiles: placed.slice(0, length).map((item) => item.tile), cells: entry.filled };
    }
    return { tiles: placed.map((entry) => entry.tile), cells: filled };
}

/** The ink that reads best on a colour: near-black or white, whichever has the higher WCAG contrast. */
export function readableInk(hex: string): string {
    const channel = (value: number): number => {
        const unit = value / 255;
        return unit <= 0.03928 ? unit / 12.92 : ((unit + 0.055) / 1.055) ** 2.4;
    };
    const digits = hex.replace('#', '');
    const expanded = digits.length === 3 ? [...digits].map((digit) => digit + digit).join('') : digits;
    const [red, green, blue] = [0, 2, 4].map((offset) => channel(parseInt(expanded.slice(offset, offset + 2), 16)));
    const luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue;
    const againstDark = (luminance + 0.05) / (0.0087 + 0.05);
    const againstLight = 1.05 / (luminance + 0.05);
    return againstDark >= againstLight ? '#020617' : '#ffffff';
}
