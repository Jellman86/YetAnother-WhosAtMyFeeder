import { fetchGardenVisitCaptures, type GardenCapture } from '../api/garden';
import { gardenHistory } from '../stores/garden_history.svelte';
import type { GardenVisit } from './garden-explorer';
import type { GardenCaptureScope } from './garden-visit-viewer.svelte';
import { PagedCaptures } from './paged-captures.svelte';

/**
 * One Garden visit's captures, paged by the shared engine as a bird visit's are.
 *
 * Membership, the view scope and any Garden review (which can rename or regroup the lead
 * capture) are this list's key terms. Pages are raw snapshots; nothing mutates them in place.
 */
export class GardenVisitCaptureList extends PagedCaptures<GardenCapture> {
    constructor(source: () => { visit: GardenVisit; scope: GardenCaptureScope }) {
        super({
            key: () => {
                const { visit, scope } = source();
                const lead = visit.items[0];
                return JSON.stringify([
                    visit.id, visit.captureCount, lead?.id, lead?.status, lead?.identification?.review, lead?.identification?.name,
                    scope.start, scope.end, scope.camera, scope.status, gardenHistory.version
                ]);
            },
            readPage: async ({ offset, limit, signal }) => {
                const { visit, scope } = source();
                const page = await fetchGardenVisitCaptures(visit.id, scope, offset, { limit, signal });
                return { items: page.items, total: page.total };
            },
            items: 'raw'
        });
    }
}
