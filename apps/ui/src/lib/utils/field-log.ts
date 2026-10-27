import type { GardenServerVisit } from '../api/garden';
import type { HealthTimelineRow } from './health-timeline';
import type { DetectionVisit } from './visit-grouping';

/**
 * One line on the field log: a bird visit, an expected filter drop, or a Garden animal's visit.
 * Operational fault history belongs to HealthActivityTimeline instead.
 */
export type FieldLogRow =
    | Exclude<HealthTimelineRow, { kind: 'fault' }>
    | { kind: 'garden'; key: string; at: number; visit: GardenServerVisit };

/**
 * A camera name tells rows apart only when the log holds more than one camera. On a one-camera
 * feeder the same chip on every row is repetition; the record and the preview still name it.
 */
export function namesCameras(visits: readonly { camera: string }[]): boolean {
    return new Set(visits.map((visit) => visit.camera)).size > 1;
}

/**
 * The day as one thread: Garden visits placed between bird visits by their most recent activity,
 * newest first, capped at `limit` rows. Bird visits keep the order the server gave them, and a
 * Garden visit only goes ahead of a bird visit it is strictly newer than, so neither list is
 * reordered and animals stay a separate record that no bird total counts.
 */
export function mergeFieldLog(
    birds: readonly DetectionVisit[],
    garden: readonly GardenServerVisit[],
    limit: number
): FieldLogRow[] {
    const rows: FieldLogRow[] = [];
    const gardenRows = garden
        .map((visit) => ({ kind: 'garden' as const, key: `garden:${visit.id}`, at: Date.parse(visit.end_time), visit }))
        .sort((a, b) => b.at - a.at);
    let next = 0;
    for (const visit of birds) {
        // The server orders bird visits by their latest capture, so that is the time they hold.
        const at = Date.parse(visit.lead.detection_time);
        while (next < gardenRows.length && gardenRows[next].at > at) rows.push(gardenRows[next++]);
        rows.push({ kind: 'visit', key: `visit:${visit.key}`, at, visit });
    }
    rows.push(...gardenRows.slice(next));
    return rows.slice(0, limit);
}
