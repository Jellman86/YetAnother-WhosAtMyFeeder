/** The waits before a failed read is tried again; the last repeats, so retries never exceed one per five minutes. */
export const READ_RETRY_MS: readonly number[] = [5_000, 15_000, 60_000, 300_000];

/**
 * The longest one reading may take, however its requests are chained; past it the read is aborted
 * and counted as a failure. Each request has its own shorter deadline; this bounds the whole.
 */
export const READ_DEADLINE_MS = 60_000;

import type { Guarded } from '../api/core';

interface RetryingReaderOptions {
    /**
     * One reading; true when it was applied, false or a rejection is a failure to retry. It must be
     * a guarded read (`apiFetchJson` and the combinators in `api/core`), so its timeout and cancel
     * cover the body: a read that stalls after its headers would otherwise hold this reader for ever.
     */
    read: (signal: AbortSignal) => Guarded<boolean>;
    /** Whether the reading is still wanted (the page is open, the owner still signed in). */
    active: () => boolean;
}

export interface RetryingReader {
    /** Read now; or, while a read or a retry wait is under way, once more when it ends. */
    request(): void;
    /** Abort a read in flight and drop any pending retry; later requests start afresh. */
    cancel(): void;
}

/**
 * A reading retried after a failure with a growing, capped wait for as long as it is still wanted.
 * At most one read is in flight. A request made meanwhile is folded into one more read: right
 * after a read that succeeded, or at the retry deadline after one that failed, so a burst of new
 * revisions can never bring a retry forward.
 */
export function createRetryingReader({ read, active }: RetryingReaderOptions): RetryingReader {
    let generation = 0;
    let reading = false;
    let wanted = false;
    let failures = 0;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let inFlight: AbortController | null = null;

    async function run(): Promise<void> {
        const mine = generation;
        const controller = new AbortController();
        inFlight = controller;
        reading = true;
        wanted = false;
        const deadline = setTimeout(() => controller.abort(new DOMException('The reading took too long', 'TimeoutError')), READ_DEADLINE_MS);
        const abandoned = new Promise<false>((resolve) => controller.signal.addEventListener('abort', () => resolve(false), { once: true }));
        let ok: boolean;
        try {
            ok = await Promise.race([read(controller.signal), abandoned]);
        } catch {
            ok = false;
        } finally {
            clearTimeout(deadline);
        }
        if (mine !== generation) return;
        inFlight = null;
        reading = false;
        if (ok) {
            failures = 0;
            if (wanted) void run();
            return;
        }
        if (!active()) {
            wanted = false;
            return;
        }
        const wait = READ_RETRY_MS[Math.min(failures, READ_RETRY_MS.length - 1)];
        failures += 1;
        retry = setTimeout(() => {
            retry = null;
            if (mine === generation && active()) void run();
        }, wait);
    }

    return {
        request(): void {
            if (reading || retry !== null) {
                wanted = true;
                return;
            }
            void run();
        },
        cancel(): void {
            generation += 1;
            // Aborted, not merely ignored: a cancelled read must not keep a request open beside the next.
            inFlight?.abort();
            inFlight = null;
            if (retry !== null) clearTimeout(retry);
            retry = null;
            reading = false;
            wanted = false;
            failures = 0;
        }
    };
}
