/**
 * Collapse overlapping triggers onto one active task.
 *
 * Polling can be triggered by timers, visibility changes, and initial startup at
 * nearly the same time. Sharing the active promise prevents duplicate requests
 * without suppressing the next scheduled run after the task settles.
 */
export function createSingleFlightRunner<T>(task: () => Promise<T>): () => Promise<T> {
    let inFlight: Promise<T> | null = null;

    return (): Promise<T> => {
        if (inFlight) return inFlight;

        let taskPromise: Promise<T>;
        try {
            taskPromise = task();
        } catch (error) {
            taskPromise = Promise.reject(error);
        }

        const run = Promise.resolve(taskPromise).finally(() => {
            if (inFlight === run) inFlight = null;
        });
        inFlight = run;
        return run;
    };
}

/**
 * Collapse overlapping triggers and enforce a minimum interval between task
 * starts. This is a defensive polling boundary: even if a lifecycle hook is
 * accidentally retriggered, it cannot turn a successful endpoint into a
 * request storm.
 */
export function createCooldownSingleFlightRunner<T>(
    task: () => Promise<T>,
    cooldownMs: number,
    now: () => number = () => Date.now()
): () => Promise<T | undefined> {
    let inFlight: Promise<T> | null = null;
    let lastStartedAt = Number.NEGATIVE_INFINITY;
    const minimumInterval = Number.isFinite(cooldownMs) ? Math.max(0, cooldownMs) : 0;

    return (): Promise<T | undefined> => {
        if (inFlight) return inFlight;

        const currentTime = now();
        if (currentTime - lastStartedAt < minimumInterval) {
            return Promise.resolve(undefined);
        }
        lastStartedAt = currentTime;

        let taskPromise: Promise<T>;
        try {
            taskPromise = task();
        } catch (error) {
            taskPromise = Promise.reject(error);
        }

        const run = Promise.resolve(taskPromise).finally(() => {
            if (inFlight === run) inFlight = null;
        });
        inFlight = run;
        return run;
    };
}
