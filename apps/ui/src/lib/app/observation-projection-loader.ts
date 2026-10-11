/** Independent observation-derived views use latest-request wins and explicit invalidation. */
export function createObservationProjectionLoader<T>(options: {
    fetch: (signal: AbortSignal) => Promise<T>;
    apply: (value: T) => void;
    clear: () => void;
    fail: (error: unknown) => void;
    settled?: () => void;
}) {
    let generation = 0;
    let controller: AbortController | null = null;
    return {
        async load(): Promise<boolean> {
            controller?.abort();
            const currentController = new AbortController();
            controller = currentController;
            const requestGeneration = ++generation;
            try {
                const value = await options.fetch(currentController.signal);
                if (requestGeneration !== generation || currentController.signal.aborted) return false;
                options.apply(value);
                return true;
            } catch (error) {
                if (requestGeneration !== generation || currentController.signal.aborted) return false;
                options.fail(error);
                return false;
            } finally {
                if (requestGeneration === generation) {
                    controller = null;
                    options.settled?.();
                }
            }
        },
        invalidate() { generation += 1; controller?.abort(); controller = null; options.clear(); },
        dispose() { generation += 1; controller?.abort(); controller = null; }
    };
}
