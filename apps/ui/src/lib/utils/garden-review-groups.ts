import type { GardenCapture } from '../api/garden';

export interface GardenReviewGroup {
    id: string;
    items: GardenCapture[];
}

function box(item: GardenCapture): readonly number[] | null {
    const value = item.motion_source?.box_xywh;
    if (item.status !== 'pending' || item.source_kind !== 'motion' || !value ||
        !value.every(Number.isFinite) || value[0] < 0 || value[1] < 0 ||
        value[2] <= 0 || value[3] <= 0 || value[0] + value[2] > 1 || value[1] + value[3] > 1) return null;
    return value;
}

function sameArea(left: GardenCapture, right: GardenCapture): boolean {
    const a = box(left), b = box(right);
    if (!a || !b || left.camera !== right.camera ||
        left.motion_source?.detector_sha256 !== right.motion_source?.detector_sha256) return false;
    const overlapWidth = Math.max(0, Math.min(a[0] + a[2], b[0] + b[2]) - Math.max(a[0], b[0]));
    const overlapHeight = Math.max(0, Math.min(a[1] + a[3], b[1] + b[3]) - Math.max(a[1], b[1]));
    const intersection = overlapWidth * overlapHeight;
    if (intersection / (a[2] * a[3] + b[2] * b[3] - intersection) >= 0.75) return true;

    const smallerWidth = Math.min(a[2], b[2]), smallerHeight = Math.min(a[3], b[3]);
    // A fixed feeder can alternate between a short, wide box and a tall, narrow
    // one. Bound extent changes and corner drift rather than widening the area.
    return Math.max(a[2], b[2]) <= 2 * smallerWidth &&
        Math.max(a[3], b[3]) <= 2 * smallerHeight &&
        Math.abs(a[0] - b[0]) <= 0.15 * smallerWidth &&
        Math.abs(a[1] - b[1]) <= 0.15 * smallerHeight &&
        overlapWidth >= 0.8 * smallerWidth && overlapHeight >= 0.8 * smallerHeight;
}

export function groupGardenReview(items: readonly GardenCapture[]): GardenReviewGroup[] {
    const groups: GardenReviewGroup[] = [];
    for (const item of items) {
        // Compare to the fixed first photo, never chain drifting boxes into one group.
        const group = groups.find(candidate => sameArea(candidate.items[0], item));
        if (group) group.items.push(item);
        else groups.push({ id: item.id, items: [item] });
    }
    return groups;
}
