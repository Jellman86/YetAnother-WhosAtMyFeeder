import { fetchVisitCaptures, type DetectionVisit, type VisitOptions } from '../api/visits';
import type { Detection } from '../api';
import { detectionsStore } from '../stores/detections.svelte';
import { PagedCaptures } from './paged-captures.svelte';

/**
 * One bird visit's original captures, paged by the shared engine.
 *
 * The visit's membership, the window and the shared bird history are this list's key terms.
 * Captures stay deep state: the record mutates the capture it was opened with (for example
 * `is_favorite`), and the row it came from must follow.
 */
export class VisitCaptureList extends PagedCaptures<Detection> {
    constructor(source: () => { visit: DetectionVisit; window: VisitOptions }) {
        super({
            key: () => {
                const { visit, window } = source();
                return JSON.stringify([
                    visit.visit_id, visit.capture_count, visit.end_time, visit.representative.display_name,
                    window.startDate, window.endDate, window.startTime, window.endTime, window.onlyHidden,
                    detectionsStore.publicHistoryVersion, detectionsStore.mutationVersion
                ]);
            },
            readPage: async ({ offset, limit, signal }) => {
                const { visit, window } = source();
                const response = await fetchVisitCaptures(visit.visit_id, { ...window, limit, offset, signal });
                return { items: response.captures, total: response.total };
            },
            items: 'deep'
        });
    }
}
