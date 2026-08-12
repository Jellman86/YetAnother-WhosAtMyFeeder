import type { Detection } from '../api';
import { needsReview } from './visit-grouping';

export interface ReviewQueue {
    /** Longest-waiting first, capped by the caller's limit. */
    items: Detection[];
    /** Every detection needing a decision, not just the previewed ones. */
    total: number;
    /** How many are not in `items`. */
    remaining: number;
    oldest: Detection | null;
}

export const REVIEW_QUEUE_PREVIEW_LIMIT = 4;

export interface ReviewQueueOptions {
    reviewThreshold: number | null;
    limit?: number;
}

function isOpen(detection: Detection, reviewThreshold: number | null): boolean {
    if (detection.is_hidden) return false;
    // A manual tag is the human decision this queue is asking for.
    if (detection.manual_tagged) return false;
    return needsReview(detection, reviewThreshold);
}

function oldestFirst(left: Detection, right: Detection): number {
    const leftAt = Date.parse(left.detection_time);
    const rightAt = Date.parse(right.detection_time);
    if (Number.isNaN(leftAt) && Number.isNaN(rightAt)) return 0;
    if (Number.isNaN(leftAt)) return 1;
    if (Number.isNaN(rightAt)) return -1;
    return leftAt - rightAt;
}

/**
 * The detections still waiting on a person, oldest first. Pure over the list it is given.
 */
export function buildReviewQueue(
    detections: readonly Detection[],
    { reviewThreshold, limit = REVIEW_QUEUE_PREVIEW_LIMIT }: ReviewQueueOptions
): ReviewQueue {
    const open = detections.filter((detection) => isOpen(detection, reviewThreshold)).sort(oldestFirst);

    return {
        items: open.slice(0, limit),
        total: open.length,
        remaining: Math.max(open.length - limit, 0),
        oldest: open[0] ?? null
    };
}
