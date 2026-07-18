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
