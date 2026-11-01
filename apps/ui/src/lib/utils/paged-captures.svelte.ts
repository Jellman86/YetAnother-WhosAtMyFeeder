import { authStore } from '../stores/auth.svelte';

const PAGE_SIZE = 20;

interface CapturePage<T> {
    items: T[];
    total: number;
}

interface CapturePageRequest {
    offset: number;
    limit: number;
    signal: AbortSignal;
}

export interface PagedCapturesSource<T> {
    /**
     * Everything that changes which captures belong (membership, window, scope, history). Owner
     * access is added by the engine, so no adapter can forget it.
     */
    key: () => string;
    readPage: (request: CapturePageRequest) => Promise<CapturePage<T>>;
    /**
     * `deep` when a record mutates the shared capture in place (a bird record sets `is_favorite`
     * on the capture it opened) and the row must follow; `raw` for snapshots nothing mutates.
     */
    items: 'deep' | 'raw';
}

interface HeldPage<T> {
    key: string;
    captures: T[];
    total: number;
}

/**
 * One visit's captures, read a bounded page at a time and only when asked.
 *
 * Everything that changes which captures a reader may see is folded into one key. A page read
 * under an older key is never shown, a read that finishes after the key moved on is discarded,
 * and a failed read stays distinguishable from an empty one.
 */
export class PagedCaptures<T> {
    #source: PagedCapturesSource<T>;
    #controller: AbortController | null = null;
    // Only one of these holds the page; `items` decides which, once, at construction.
    #deep = $state<HeldPage<T> | null>(null);
    #raw = $state.raw<HeldPage<T> | null>(null);
    #pendingKey = $state('');
    #failedKey = $state('');

    constructor(source: PagedCapturesSource<T>) {
        this.#source = source;
    }

    get #result(): HeldPage<T> | null {
        return this.#source.items === 'deep' ? this.#deep : this.#raw;
    }

    set #result(page: HeldPage<T> | null) {
        if (this.#source.items === 'deep') this.#deep = page;
        else this.#raw = page;
    }

    readonly key = $derived.by(() => JSON.stringify([this.#source.key(), authStore.hasOwnerAccess]));
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
        try {
            const page = await this.#source.readPage({ offset: previous.length, limit: PAGE_SIZE, signal: current.signal });
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
