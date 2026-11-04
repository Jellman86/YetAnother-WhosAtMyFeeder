import type { BirdScanResponse } from '../api/media';
import type { SourceSize } from './count-scene';

interface CountDisclosure {
    kind: 'legacy' | 'complete' | 'incomplete' | 'unavailable';
    count: number | null;
    unconfirmed: number;
    excluded: number;
}

export function birdCountDisclosure(response: BirdScanResponse | null): CountDisclosure | null {
    if (response?.status !== 'completed') return null;
    const count = response.result_count;
    const unconfirmed = response.unconfirmed_regions?.length ?? 0;
    const excluded = response.excluded_regions?.length ?? 0;
    if (count === null || count === undefined || !Number.isFinite(count) || count < 0 ||
        response.count_status === 'not_measured' || response.count_status === 'ambiguous') {
        return { kind: 'unavailable', count: null, unconfirmed, excluded };
    }
    const kind = unconfirmed > 0 || response.count_status === 'incomplete' ? 'incomplete'
        : response.count_status === 'complete' ? 'complete' : 'legacy';
    return { kind, count, unconfirmed, excluded };
}

// The square crop shows the flagged box with some surrounding scene for context.
const CROP_MARGIN = 1.3;

/** A square evidence crop, only after the exact full scene supplies its natural size. */
export function countRegionImageStyle(box: readonly number[], size: SourceSize | null): string | undefined {
    if (!size || !Number.isFinite(size.width) || !Number.isFinite(size.height) || size.width <= 0 || size.height <= 0 ||
        box.length !== 4 || box.some((value) => !Number.isFinite(value) || value < 0) ||
        box[2] <= box[0] || box[3] <= box[1] || box[2] > size.width || box[3] > size.height) return undefined;
    const [left, top, right, bottom] = box;
    const span = Math.max(right - left, bottom - top) * CROP_MARGIN;
    return `width:${100 * size.width / span}%;height:${100 * size.height / span}%;left:${50 - 50 * (left + right) / span}%;top:${50 - 50 * (top + bottom) / span}%;max-width:none`;
}

/** Where the flagged box sits inside that crop, so the preview marks exactly what was not counted. */
export function countRegionOutlineStyle(box: readonly number[]): string | undefined {
    if (box.length !== 4 || box.some((value) => !Number.isFinite(value)) || box[2] <= box[0] || box[3] <= box[1]) return undefined;
    const width = box[2] - box[0];
    const height = box[3] - box[1];
    const span = Math.max(width, height) * CROP_MARGIN;
    const percent = (value: number): number => Number(value.toFixed(3));
    const widthShare = 100 * width / span;
    const heightShare = 100 * height / span;
    return `left:${percent(50 - widthShare / 2)}%;top:${percent(50 - heightShare / 2)}%;width:${percent(widthShare)}%;height:${percent(heightShare)}%`;
}
