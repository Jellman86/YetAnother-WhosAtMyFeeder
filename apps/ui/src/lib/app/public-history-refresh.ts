/** Fixed windows bound public refetches without starving under continuous SSE.
 * One trailing refresh retains changes received while a request is in flight.
 */
export function createPublicHistoryRefresh(refresh: () => Promise<void>, delayMs: number | (() => number) = 2000, maxRetries = 2) {
    let timer: ReturnType<typeof setTimeout> | null = null;
    let running = false;
    let dirty = false;
    let disposed = false;
    let failures = 0;

    function schedule() {
        if (disposed || running || timer !== null || !dirty) return;
        timer = setTimeout(async () => {
            timer = null;
            if (disposed) return;
            dirty = false;
            running = true;
            try {
                await refresh();
                failures = 0;
            } catch {
                // The caller reports the error. Retain one bounded retry instead
                // of dropping the invalidation or rejecting the timer callback.
                failures += 1;
                if (failures <= maxRetries) dirty = true;
            } finally {
                running = false;
                schedule();
            }
        }, (typeof delayMs === 'function' ? delayMs() : delayMs) * 2 ** failures);
    }

    return {
        notify() { failures = 0; dirty = true; schedule(); },
        dispose() {
            disposed = true;
            dirty = false;
            if (timer !== null) clearTimeout(timer);
            timer = null;
        }
    };
}
