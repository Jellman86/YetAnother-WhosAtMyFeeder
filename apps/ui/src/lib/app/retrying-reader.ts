/** The waits before a failed read is tried again; the last repeats, so retries never exceed one per five minutes. */
export const READ_RETRY_MS: readonly number[] = [5_000, 15_000, 60_000, 300_000];

interface RetryingReaderOptions {
    /** One reading; true when it was applied. False or a throw is a failure to retry. */
    read: () => Promise<boolean>;
    /** Whether the reading is still wanted (the page is open, the owner still signed in). */
    active: () => boolean;
}

export interface RetryingReader {
    /** Read now, or once more after a read already in flight. */
    request(): void;
    /** Drop any pending retry and ignore the result of a read in flight; later requests start afresh. */
    cancel(): void;
}

/**
 * A reading that is retried after a failure with a growing, capped wait, for as long as it is
 * still wanted. Shared by every read that follows a pushed revision, so none of them can stop at
 * one failed attempt and none can retry past a logout or an unmounted page.
 */
export function createRetryingReader({ read, active }: RetryingReaderOptions): RetryingReader {
    let generation = 0;
    let reading = false;
    let again = false;
    let failures = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;

    function clearTimer(): void {
        if (timer !== null) clearTimeout(timer);
        timer = null;
    }

    async function run(): Promise<void> {
        if (reading) {
            again = true;
            return;
        }
        clearTimer();
        const mine = generation;
        reading = true;
        let ok = false;
        try {
            ok = await read();
        } catch {
            ok = false;
        }
        if (mine !== generation) return;
        reading = false;
        if (again) {
            again = false;
            void run();
            return;
        }
        if (ok) {
            failures = 0;
            return;
        }
        if (!active()) return;
        const wait = READ_RETRY_MS[Math.min(failures, READ_RETRY_MS.length - 1)];
        failures += 1;
        timer = setTimeout(() => {
            timer = null;
            if (mine === generation && active()) void run();
        }, wait);
    }

    return {
        request: () => void run(),
        cancel(): void {
            generation += 1;
            clearTimer();
            reading = false;
            again = false;
            failures = 0;
        }
    };
}
