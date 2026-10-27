import { fetchGardenVisitCaptures, type GardenCapture, type GardenServerVisit, type GardenTimelineQuery } from '../api/garden';
import { gardenBelongs, gardenEntryView, type GardenReview, type GardenVisit } from './garden-explorer';

const CAPTURE_PAGE_SIZE = 128;

export type GardenCaptureScope = Pick<GardenTimelineQuery, 'start' | 'end' | 'camera'> & { status: GardenReview };

/**
 * One Garden visit opened in the capture record: its photos, read a page at a time, and where the
 * record goes after a review. A read that finishes after the person moved on is discarded.
 */
export class GardenVisitViewer {
    capture = $state.raw<GardenCapture | null>(null);
    group = $state.raw<GardenVisit | null>(null);
    offset = $state(0);
    loading = $state(false);
    error = $state<string | null>(null);

    #scope: () => GardenCaptureScope;
    #failure: () => string;
    #generation = 0;

    constructor(scope: () => GardenCaptureScope, failure: () => string) {
        this.#scope = scope;
        this.#failure = failure;
    }

    open(visit: GardenServerVisit): void {
        this.#generation++;
        this.capture = visit.representative;
        this.group = { id: visit.id, kind: visit.kind, captureCount: visit.capture_count, items: [visit.representative] };
        this.offset = 0;
        this.loading = false;
        this.error = null;
        if (visit.capture_count > 1) void this.page(0, false);
    }

    async page(index: number, selectCapture = true): Promise<void> {
        const group = this.group;
        if (!group) return;
        const generation = ++this.#generation;
        const selectedId = this.capture?.id;
        const offset = Math.floor(index / CAPTURE_PAGE_SIZE) * CAPTURE_PAGE_SIZE;
        this.loading = true;
        this.error = null;
        try {
            const page = await fetchGardenVisitCaptures(group.id, this.#scope(), offset);
            if (generation !== this.#generation || this.capture?.id !== selectedId) return;
            this.group = { ...group, captureCount: page.total, items: page.items };
            this.offset = offset;
            this.capture = selectCapture
                ? page.items[index - offset] ?? page.items[0] ?? null
                : page.items.find((item) => item.id === selectedId) ?? page.items[0] ?? null;
        } catch (failure) {
            if (generation !== this.#generation) return;
            this.error = failure instanceof Error ? failure.message : this.#failure();
        } finally {
            if (generation === this.#generation) this.loading = false;
        }
    }

    /** A capture after a review: kept while it still belongs to the log, otherwise the next photo opens. */
    changed(next: GardenCapture): void {
        this.#generation++;
        this.loading = false;
        this.error = null;
        const group = this.group;
        if (gardenBelongs(next, this.#scope().status)) {
            this.capture = next;
            if (!group) return;
            const previous = group.items.find((item) => item.id === next.id);
            // A changed state or name no longer belongs to the stack it was opened from.
            if (!previous || previous.status !== next.status || gardenEntryView(previous).name !== gardenEntryView(next).name) {
                this.group = { id: next.id, kind: 'visit', captureCount: 1, items: [next] };
                this.offset = 0;
            } else {
                this.group = { ...group, items: group.items.map((item) => (item.id === next.id ? next : item)) };
            }
            return;
        }
        const items = group?.items ?? [];
        const at = items.findIndex((item) => item.id === next.id);
        this.capture = items[at + 1] ?? items[at - 1] ?? null;
        if (group) {
            const remaining = items.filter((item) => item.id !== next.id);
            this.group = { ...group, items: remaining, captureCount: Math.max(0, (group.captureCount ?? items.length) - 1) };
        }
    }

    close(): void {
        this.#generation++;
        this.capture = null;
        this.group = null;
        this.offset = 0;
        this.loading = false;
        this.error = null;
    }
}
