/** Starts reporting size changes to `onResize` and returns the stop. */
export type SizeWatcher = (onResize: () => void) => () => void;

/** Watches an element's size with a ResizeObserver. */
export function watchElementSize(element: Element): SizeWatcher {
    return (onResize) => {
        const observer = new ResizeObserver(() => onResize());
        observer.observe(element);
        return () => observer.disconnect();
    };
}

/**
 * Resolves once what `watch` reports has kept its size for `quietMs`, and at the latest after
 * `maxMs`. A page that lands on a part further down waits for this before it scrolls: the parts above
 * still fill in their data (the model list, then Hardware beneath it), and scrolling before they do
 * left the reader's place moving under them.
 */
export function layoutSettled(watch: SizeWatcher, { quietMs = 250, maxMs = 2500 }: { quietMs?: number; maxMs?: number } = {}): Promise<void> {
    return new Promise((resolve) => {
        let quiet: ReturnType<typeof setTimeout> | null = null;
        let stop: (() => void) | null = null;
        let done = false;
        const finish = (): void => {
            if (done) return;
            done = true;
            if (quiet !== null) clearTimeout(quiet);
            clearTimeout(longest);
            stop?.();
            resolve();
        };
        const restart = (): void => {
            if (quiet !== null) clearTimeout(quiet);
            quiet = setTimeout(finish, quietMs);
        };
        const longest = setTimeout(finish, maxMs);
        stop = watch(restart);
        restart();
    });
}
