import type { Detection, ReviewQueueResponse } from '../api';
import { isUnknownBirdLabel } from './count-scene';
import { needsReview } from './visit-grouping';

/** Why a detection is asking for a person: no species at all, a shaky score, or a
 * species this feeder has never confirmed (#310). */
export type ReviewReason = 'unknown_species' | 'low_score' | 'new_species';

export interface ReviewReasonMessage {
    key: string;
    default: string;
    values?: { count: number };
}

/**
 * The reason a queued visit states. The queue's own reason wins. A visit that arrived without one
 * is judged by what it shows: a bird with no species is unknown, never "below the naming
 * threshold", and a named one is waiting on its score.
 */
export function reviewReasonFor(detection: Detection, reasons: ReadonlyMap<string, ReviewReason> | undefined): ReviewReason {
    const given = reasons?.get(detection.frigate_event);
    if (given) return given;
    const name = (detection.display_name ?? '').trim();
    return !name || isUnknownBirdLabel(name) ? 'unknown_species' : 'low_score';
}

/** The sentence the review dialog opens with: why this visit needs a person, and what to do. */
export function reviewReasonNote(
    reason: ReviewReason,
    species: string
): { key: string; default: string; values?: { species: string } } {
    if (reason === 'new_species') {
        return {
            key: 'dashboard.review_session.new_species_note',
            default: 'First {species} recorded here. Confirm it, correct it, or block the species.',
            values: { species }
        };
    }
    if (reason === 'unknown_species') {
        return {
            key: 'dashboard.review_session.unknown_note',
            default: 'The model could not name this bird, so there is no species to confirm. Pick one below.'
        };
    }
    return { key: 'dashboard.review_session.threshold_note', default: 'The model scored this below the naming threshold.' };
}

/** The words a queue row uses to say why it needs a person. */
export function reviewReasonMessage(reason: ReviewReason, sightings: number): ReviewReasonMessage {
    if (reason === 'new_species') {
        return {
            key: 'dashboard.review_queue.new_species_tag',
            default: 'New species · {count, plural, one {# sighting} other {# sightings}}',
            values: { count: sightings }
        };
    }
    if (reason === 'unknown_species') {
        return { key: 'dashboard.review_queue.reason_unknown_species', default: 'No species reached the naming threshold' };
    }
    return { key: 'dashboard.review_queue.reason_low_score', default: 'Below the naming threshold' };
}

/**
 * The species a queued visit can be confirmed as in one step: the model's own name, whenever it
 * gave one. A visit with no species has nothing to confirm, so the owner picks one instead.
 */
export function reviewSuggestion(detection: Detection, reason: ReviewReason): string | null {
    if (reason === 'unknown_species') return null;
    const name = (detection.display_name ?? '').trim();
    if (!name || isUnknownBirdLabel(name)) return null;
    return name;
}

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

const REVIEW_QUEUE_PREVIEW_LIMIT = 4;

export interface QueuedDetection {
    detection: Detection;
    reason: ReviewReason;
    /** How many sightings a new species has; null for any other reason. */
    sightings: number | null;
}

/** What the server says is waiting. The total covers everything, the entries only what was asked for. */
export interface ReviewQueueReading {
    entries: readonly QueuedDetection[];
    total: number;
}

export const EMPTY_REVIEW_QUEUE_READING: ReviewQueueReading = { entries: [], total: 0 };

export function readingFromResponse(response: ReviewQueueResponse): ReviewQueueReading {
    return {
        entries: response.items.map((item) => ({
            detection: item.event as unknown as Detection,
            reason: item.reason,
            sightings: item.species_sightings ?? null
        })),
        total: response.total
    };
}

/** A decision the server has taken: gone from this reading without waiting for the next one. */
export function withoutEvent(reading: ReviewQueueReading, frigateEvent: string): ReviewQueueReading {
    const entries = reading.entries.filter((entry) => entry.detection.frigate_event !== frigateEvent);
    return { entries, total: Math.max(reading.total - (reading.entries.length - entries.length), 0) };
}

export interface ReviewQueueOptions {
    reviewThreshold: number | null;
    limit?: number;
    /** The live record of a queued detection, newer than the reading that listed it. */
    knownDetections?: readonly Detection[];
    /** Explicit saved owner choices can outlive the recent history page. */
    localChoices?: ReadonlyMap<string, Partial<Detection>>;
}

function oldestFirst(left: QueuedDetection, right: QueuedDetection): number {
    const leftAt = Date.parse(left.detection.detection_time);
    const rightAt = Date.parse(right.detection.detection_time);
    if (Number.isNaN(leftAt) && Number.isNaN(rightAt)) return 0;
    if (Number.isNaN(leftAt)) return 1;
    if (Number.isNaN(rightAt)) return -1;
    return leftAt - rightAt;
}

/**
 * The server decides what is waiting. Newer knowledge here can only take a detection away:
 * a saved choice or a live update settles it before the next reading arrives.
 */
export function buildReviewQueue(
    reading: ReviewQueueReading,
    { reviewThreshold, limit = REVIEW_QUEUE_PREVIEW_LIMIT, knownDetections = [], localChoices }: ReviewQueueOptions
): ReviewQueue {
    const known = new Map(knownDetections.map((detection) => [detection.frigate_event, detection]));
    const open: QueuedDetection[] = [];
    for (const entry of reading.entries) {
        const current = known.get(entry.detection.frigate_event) ?? entry.detection;
        const choice = localChoices?.get(current.frigate_event);
        const detection = choice?.manual_tagged === true && choice.classification_input?.source === 'owner_species_choice'
            ? { ...current, ...choice }
            : current;
        if (detection.is_hidden || detection.manual_tagged) continue;
        // Only a better score settles a detection here. A new species waits whatever it scores, and an
        // unknown bird that gains a name clears on the next reading, which that live update triggers.
        if (entry.reason === 'low_score' && reviewThreshold !== null && !needsReview(detection, reviewThreshold)) continue;
        open.push({ ...entry, detection });
    }
    open.sort(oldestFirst);

    const reasons = new Map<string, ReviewReason>();
    const newSpeciesSightings = new Map<string, number>();
    for (const { detection, reason, sightings } of open) {
        reasons.set(detection.frigate_event, reason);
        if (sightings !== null) newSpeciesSightings.set(detection.frigate_event, sightings);
    }

    const total = Math.max(reading.total - (reading.entries.length - open.length), 0);
    const items = open.slice(0, limit).map((entry) => entry.detection);
    return { items, total, remaining: Math.max(total - items.length, 0), oldest: items[0] ?? null, reasons, newSpeciesSightings };
}

/** A guest cannot read the queue, so the day bar's figure comes from the history they can see. */
export function visibleUnresolvedCount(detections: readonly Detection[], reviewThreshold: number | null): number {
    return detections.filter((detection) => !detection.is_hidden && !detection.manual_tagged && needsReview(detection, reviewThreshold)).length;
}
