/**
 * Tracks whether a data source is stale based on elapsed time since last fetch.
 * Compose this into a store class — do not inherit from it.
 */
export class StaleTracker {
    private lastFetchedAt = 0;

    constructor(private readonly maxAgeMs: number) {
        if (maxAgeMs <= 0) throw new RangeError(`StaleTracker: maxAgeMs must be positive, got ${maxAgeMs}`);
    }

    /** Call after every successful fetch to mark data as fresh. */
    touch(): void {
        this.lastFetchedAt = Date.now();
    }

    /** Returns true if the data has never been fetched or was fetched longer ago than maxAgeMs. */
    isStale(): boolean {
        return Date.now() - this.lastFetchedAt >= this.maxAgeMs;
    }

    /** Force data to be considered stale on the next sweep (e.g. after logout). */
    reset(): void {
        this.lastFetchedAt = 0;
    }
}
