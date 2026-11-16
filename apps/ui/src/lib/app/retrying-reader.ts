/** The waits before a failed read is tried again; the last repeats, so retries never exceed one per five minutes. */
export const READ_RETRY_MS: readonly number[] = [5_000, 15_000, 60_000, 300_000];

interface RetryingReaderOptions {
    /** One reading; true when it was applied. False or a throw is a failure to retry. */
    read: () => Promise<boolean>;
    /** Whether the reading is still wanted (the page is open, the owner still signed in). */
    active: () => boolean;
}

export interface RetryingReader {
    /** Read now; or, while a read or a retry wait is under way, once more when it ends. */
    request(): void;
    /** Drop any pending retry and ignore the result of a read in flight; later requests start afresh. */
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

    async function run(): Promise<void> {
        const mine = generation;
        reading = true;
        wanted = false;
        let ok: boolean;
        try {
            ok = await read();
        } catch {
            ok = false;
        }
        if (mine !== generation) return;
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
            if (retry !== null) clearTimeout(retry);
            retry = null;
            reading = false;
            wanted = false;
            failures = 0;
        }
    };
}
