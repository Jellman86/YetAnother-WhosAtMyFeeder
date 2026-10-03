import { fetchVisitCaptures, type DetectionVisit, type VisitOptions } from '../api/visits';
import type { Detection } from '../api';
import { authStore } from '../stores/auth.svelte';
import { detectionsStore } from '../stores/detections.svelte';

const PAGE_SIZE = 20;

/**
 * One visit's original captures, read a bounded page at a time and only when asked.
 *
 * Everything that changes which captures a reader may see (the visit's membership, the window,
 * owner access and the shared history) is folded into one key. A page read under an older key is
 * never shown, and a read that finishes after the key moved on is discarded.
 */
export class VisitCaptureList {
    #source: () => { visit: DetectionVisit; window: VisitOptions };
    #controller: AbortController | null = null;
    #result = $state<{ key: string; captures: Detection[]; total: number } | null>(null);
    #pendingKey = $state('');
    #failedKey = $state('');

    constructor(source: () => { visit: DetectionVisit; window: VisitOptions }) {
        this.#source = source;
    }

    readonly key = $derived.by(() => {
        const { visit, window } = this.#source();
        return JSON.stringify([
            visit.visit_id, visit.capture_count, visit.end_time, visit.representative.display_name,
            window.startDate, window.endDate, window.startTime, window.endTime, window.onlyHidden,
            authStore.hasOwnerAccess, detectionsStore.publicHistoryVersion, detectionsStore.mutationVersion
        ]);
    });
    readonly captures = $derived(this.#result?.key === this.key ? this.#result.captures : []);
    readonly total = $derived(this.#result?.key === this.key ? this.#result.total : 0);
    readonly loaded = $derived(this.#result?.key === this.key);
    readonly loading = $derived(this.#pendingKey === this.key);
    readonly failed = $derived(this.#failedKey === this.key);
    readonly hasMore = $derived(this.captures.length > 0 && this.captures.length < this.total);

    /** Reads the first page unless the current one is still valid. */
    ensure(): void {
        if (this.#result?.key !== this.key) void this.load(true);
    }

    async load(reset = false): Promise<void> {
        const key = this.key;
        if (this.#pendingKey === key) return;
        this.#controller?.abort();
        const current = new AbortController();
        this.#controller = current;
        this.#pendingKey = key;
        this.#failedKey = '';
        const previous = !reset && this.#result?.key === key ? this.#result.captures : [];
        const { visit, window } = this.#source();
        try {
            const response = await fetchVisitCaptures(visit.visit_id, {
                ...window, limit: PAGE_SIZE, offset: previous.length, signal: current.signal
            });
            if (current.signal.aborted || key !== this.key) return;
            this.#result = { key, captures: [...previous, ...response.captures], total: response.total };
        } catch (failure) {
            const aborted = current.signal.aborted || (failure instanceof Error && failure.name === 'AbortError');
            if (!aborted && key === this.key) this.#failedKey = key;
        } finally {
            if (this.#controller === current) this.#pendingKey = '';
        }
    }

    dispose(): void {
        this.#controller?.abort();
    }
}
