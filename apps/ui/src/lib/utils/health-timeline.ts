import type { DetectionVisit } from './visit-grouping';
import type { FilteredDetection } from './pipeline-health';

/**
 * The Health page shows one thread of what the feeder did: visits it kept and
 * frames the filter rejected, in the order they happened. Both are rendered by
 * `FieldLog`, so this module's only job is deciding what belongs on the thread
 * and in what order.
 */

export type HealthTimelineRow =
    | { kind: 'visit'; key: string; at: number; visit: DetectionVisit }
    | { kind: 'filtered'; key: string; at: number; drop: FilteredDetection };

function parse(value: string | null | undefined): number {
    if (typeof value !== 'string') return Number.NaN;
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? Number.NaN : parsed;
}

/**
 * How far back the page's window reaches, measured from when this instance
 * started. Health counters are since-startup, so the visits shown beside them
 * must use the same slice of time rather than a rolling day.
 */
export function instanceWindowMs(
    startupStartedAt: string | null | undefined,
    now: number = Date.now()
): number | null {
    const started = parse(startupStartedAt);
    if (Number.isNaN(started)) return null;
    return Math.max(0, now - started);
}

export interface HealthTimelineInput {
    visits?: readonly DetectionVisit[];
    filtered?: readonly FilteredDetection[];
    limit?: number;
}

/**
 * Merge kept visits and filtered frames into one newest-first thread. Rows
 * whose time cannot be read are kept at the end rather than dropped, so a bad
 * timestamp never silently hides a real event.
 */
export function buildHealthTimeline({
    visits = [],
    filtered = [],
    limit = 12
}: HealthTimelineInput): HealthTimelineRow[] {
    const rows: HealthTimelineRow[] = [];

    for (const visit of visits) {
        rows.push({ kind: 'visit', key: `visit:${visit.key}`, at: parse(visit.endTime), visit });
    }
    for (const drop of filtered) {
        rows.push({ kind: 'filtered', key: `drop:${drop.eventId}`, at: parse(drop.timestamp), drop });
    }

    rows.sort((left, right) => {
        if (Number.isNaN(left.at) && Number.isNaN(right.at)) return 0;
        if (Number.isNaN(left.at)) return 1;
        if (Number.isNaN(right.at)) return -1;
        return right.at - left.at;
    });

    return limit > 0 ? rows.slice(0, limit) : rows;
}

/**
 * Events in the window that the thread does not show. Counted from the
 * pipeline's own totals rather than from the rows, because the detections store
 * holds only the most recent frames and would understate the remainder.
 */
export function hiddenEventCount(
    startedEvents: number,
    shown: number
): number {
    if (!Number.isFinite(startedEvents) || startedEvents <= 0) return 0;
    return Math.max(0, Math.round(startedEvents) - Math.max(0, shown));
}
