import type { Detection } from '../api';

/**
 * A visit is one bird at one camera over a short window. Frigate emits several frames
 * for a single approach, and the dashboard used to print one card per frame, so a
 * blackbird that landed once could appear four times.
 */
export interface DetectionVisit {
    /** Stable across re-renders: the newest frame owns the visit. */
    key: string;
    species: string;
    camera: string;
    /** Newest frame first, matching the order the store hands detections out. */
    frames: Detection[];
    /** The newest frame, which titles the row. */
    lead: Detection;
    /** The highest-scoring frame, the one worth showing a picture of. */
    best: Detection;
    startTime: string;
    endTime: string;
    needsReview: boolean;
}

/** Frames further apart than this are separate approaches, not one visit. */
export const VISIT_GAP_MS = 10 * 60 * 1000;

/** The dashboard is a "today" surface; Explorer holds the longer history. */
export const DESK_WINDOW_MS = 24 * 60 * 60 * 1000;

const UNRESOLVED_LABEL = 'unknown bird';

export interface VisitGroupingOptions {
    /** The saved classifier naming threshold. Null means it has not been loaded. */
    reviewThreshold: number | null;
    gapMs?: number;
}

function timestamp(detection: Detection): number {
    const parsed = Date.parse(detection.detection_time);
    return Number.isNaN(parsed) ? Number.NaN : parsed;
}

export function needsReview(detection: Detection, reviewThreshold: number | null): boolean {
    const label = (detection.display_name ?? '').trim().toLowerCase();
    if (!label || label === UNRESOLVED_LABEL) return true;
    if (reviewThreshold === null || !Number.isFinite(reviewThreshold)) return false;
    return (detection.score ?? 0) < reviewThreshold;
}

function belongsToVisit(previous: Detection, candidate: Detection, gapMs: number): boolean {
    if (previous.display_name !== candidate.display_name) return false;
    if (previous.camera_name !== candidate.camera_name) return false;

    const previousAt = timestamp(previous);
    const candidateAt = timestamp(candidate);
    // An unparseable timestamp cannot be shown to be within the window, so it starts
    // its own visit rather than being folded into an unrelated one.
    if (Number.isNaN(previousAt) || Number.isNaN(candidateAt)) return false;

    return Math.abs(previousAt - candidateAt) <= gapMs;
}

function toVisit(frames: Detection[], reviewThreshold: number | null): DetectionVisit {
    const lead = frames[0];
    const best = frames.reduce(
        (strongest, frame) => ((frame.score ?? 0) > (strongest.score ?? 0) ? frame : strongest),
        lead
    );
    const oldest = frames[frames.length - 1];

    return {
        key: lead.frigate_event,
        species: lead.display_name,
        camera: lead.camera_name,
        frames,
        lead,
        best,
        startTime: oldest.detection_time,
        endTime: lead.detection_time,
        needsReview: frames.every((frame) => needsReview(frame, reviewThreshold))
    };
}

/**
 * The slice of a detection list the desk describes. Everything on the dashboard (the log,
 * the queue, the camera counts, the sensor comparison) must agree on one window, or the
 * numbers contradict each other.
 */
export function withinDeskWindow(
    detections: readonly Detection[],
    now: number = Date.now(),
    windowMs: number = DESK_WINDOW_MS
): Detection[] {
    return detections.filter((detection) => {
        const at = timestamp(detection);
        // Keep anything we cannot place rather than silently dropping a real detection.
        if (Number.isNaN(at)) return true;
        return now - at <= windowMs;
    });
}

/**
 * Fold a newest-first detection list into visits. Pure: the input array is left alone.
 */
export function groupDetectionsIntoVisits(
    detections: readonly Detection[],
    { reviewThreshold, gapMs = VISIT_GAP_MS }: VisitGroupingOptions
): DetectionVisit[] {
    if (detections.length === 0) return [];

    const ordered = [...detections].sort((left, right) => {
        const leftAt = timestamp(left);
        const rightAt = timestamp(right);
        if (Number.isNaN(leftAt) && Number.isNaN(rightAt)) return 0;
        if (Number.isNaN(leftAt)) return 1;
        if (Number.isNaN(rightAt)) return -1;
        return rightAt - leftAt;
    });

    const visits: Detection[][] = [];
    for (const detection of ordered) {
        const current = visits[visits.length - 1];
        // Compare against the nearest frame so a long, steady visit is not split by the
        // distance back to where it started.
        if (current && belongsToVisit(current[current.length - 1], detection, gapMs)) {
            current.push(detection);
        } else {
            visits.push([detection]);
        }
    }

    return visits.map((frames) => toVisit(frames, reviewThreshold));
}
