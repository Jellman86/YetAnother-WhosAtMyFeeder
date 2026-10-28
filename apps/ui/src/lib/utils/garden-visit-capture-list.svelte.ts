import { fetchGardenVisitCaptures, type GardenCapture } from '../api/garden';
import { authStore } from '../stores/auth.svelte';
import { gardenHistory } from '../stores/garden_history.svelte';
import type { GardenVisit } from './garden-explorer';
import type { GardenCaptureScope } from './garden-visit-viewer.svelte';

const PAGE_SIZE = 20;

/**
 * One Garden visit's captures, read a bounded page at a time and only when asked, as a bird
 * visit's are. Everything that changes which captures belong (membership, scope and any Garden
 * review) is folded into one key, and a read under an older key is never shown.
 */
export class GardenVisitCaptureList {
    #source: () => { visit: GardenVisit; scope: GardenCaptureScope };
    #controller: AbortController | null = null;
    #result = $state.raw<{ key: string; captures: GardenCapture[]; total: number } | null>(null);
    #pendingKey = $state('');
    #failedKey = $state('');

    constructor(source: () => { visit: GardenVisit; scope: GardenCaptureScope }) {
        this.#source = source;
    }

    readonly key = $derived.by(() => {
        const { visit, scope } = this.#source();
        const lead = visit.items[0];
        return JSON.stringify([
            visit.id, visit.captureCount, lead?.id, lead?.status, lead?.identification?.review, lead?.identification?.name,
            scope.start, scope.end, scope.camera, scope.status, authStore.hasOwnerAccess, gardenHistory.version
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
        const { visit, scope } = this.#source();
        try {
            const page = await fetchGardenVisitCaptures(visit.id, scope, previous.length, { limit: PAGE_SIZE, signal: current.signal });
            if (current.signal.aborted || key !== this.key) return;
            this.#result = { key, captures: [...previous, ...page.items], total: page.total };
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
