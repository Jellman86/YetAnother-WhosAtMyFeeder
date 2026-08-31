import type { Detection } from '../api';
import { needsReview } from './visit-grouping';

/** Why a detection is asking for a person: a shaky score, or a species this
 * feeder has never confirmed (#310). */
export type ReviewReason = 'low_score' | 'new_species';

export interface ReviewQueue {
    /** Longest-waiting first, capped by the caller's limit. */
    items: Detection[];
    /** Every detection needing a decision, not just the previewed ones. */
    total: number;
    /** How many are not in `items`. */
    remaining: number;
    oldest: Detection | null;
    /** Reason per frigate_event, for every queued detection. */
    reasons: Map<string, ReviewReason>;
    /** Sighting count per frigate_event for new-species entries. */
    newSpeciesSightings: Map<string, number>;
}

export const REVIEW_QUEUE_PREVIEW_LIMIT = 4;

export interface NewSpeciesEntry {
    detection: Detection;
    sightings: number;
}

export interface ReviewQueueOptions {
    reviewThreshold: number | null;
    limit?: number;
    /** Latest sightings of species with no confirmed history here. */
    newSpecies?: readonly NewSpeciesEntry[];
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
 * The detections still waiting on a person, oldest first. Pure over the lists
 * it is given: recent low-score detections, plus each unconfirmed new
 * species' latest sighting — deduplicated, with the more specific reason
 * winning when one detection qualifies both ways.
 */
export function buildReviewQueue(
    detections: readonly Detection[],
    { reviewThreshold, limit = REVIEW_QUEUE_PREVIEW_LIMIT, newSpecies = [] }: ReviewQueueOptions
): ReviewQueue {
    const open = detections.filter((detection) => isOpen(detection, reviewThreshold)).sort(oldestFirst);

    const reasons = new Map<string, ReviewReason>();
    const newSpeciesSightings = new Map<string, number>();
    for (const detection of open) reasons.set(detection.frigate_event, 'low_score');

    const seen = new Set(open.map((detection) => detection.frigate_event));
    const newcomers: Detection[] = [];
    for (const { detection, sightings } of newSpecies) {
        if (detection.is_hidden || detection.manual_tagged) continue;
        // "First of its kind here" is the sharper question than "shaky score".
        reasons.set(detection.frigate_event, 'new_species');
        newSpeciesSightings.set(detection.frigate_event, sightings);
        if (seen.has(detection.frigate_event)) continue;
        seen.add(detection.frigate_event);
        newcomers.push(detection);
    }

    const all = [...open, ...newcomers].sort(oldestFirst);

    return {
        items: all.slice(0, limit),
        total: all.length,
        remaining: Math.max(all.length - limit, 0),
        oldest: all[0] ?? null,
        reasons,
        newSpeciesSightings
    };
}
