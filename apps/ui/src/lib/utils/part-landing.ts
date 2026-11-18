/** Starts reporting to `onReport` and returns the stop. */
type Listen = (onReport: () => void) => () => void;

/** Reports every size change of `element`, through a ResizeObserver. */
export function watchElementSize(element: Element): Listen {
    return (onResize) => {
        const observer = new ResizeObserver(() => onResize());
        observer.observe(element);
        return () => observer.disconnect();
    };
}

/** Reports the reader acting on the page: a wheel or trackpad scroll, a touch, a key or a press. */
export function listenForReaderIntent(onIntent: () => void): () => void {
    const events = ['wheel', 'touchstart', 'keydown', 'pointerdown'] as const;
    for (const type of events) document.addEventListener(type, onIntent, { capture: true, passive: true });
    return () => {
        for (const type of events) document.removeEventListener(type, onIntent, { capture: true });
    };
}

/**
 * Resolves `true` once the section is ready to be scrolled through: it has kept its size for `quietMs`
 * with no request in flight. A part waiting on a slow read changes nothing until the answer comes, so
 * quiet alone does not mean ready; after the answer, the section is given `quietMs` again to draw it.
 * At `maxMs` it is ready however things stand. Resolves `false` if `signal` calls the landing off.
 */
export function whenSectionReady({ watch, requestsIdle, quietMs = 150, maxMs = 4000, signal }: { watch: Listen; requestsIdle: Listen; quietMs?: number; maxMs?: number; signal?: AbortSignal }): Promise<boolean> {
    return new Promise((resolve) => {
        let done = false;
        let quiet: ReturnType<typeof setTimeout> | null = null;
        let stopWaitingForIdle: (() => void) | null = null;
        let stopWatching: (() => void) | null = null;
        const longest = setTimeout(() => finish(true), maxMs);
        const callOff = (): void => finish(false);
        function finish(ready: boolean): void {
            if (done) return;
            done = true;
            if (quiet !== null) clearTimeout(quiet);
            clearTimeout(longest);
            stopWaitingForIdle?.();
            stopWatching?.();
            signal?.removeEventListener('abort', callOff);
            resolve(ready);
        }
        function restart(): void {
            if (done) return;
            if (quiet !== null) clearTimeout(quiet);
            stopWaitingForIdle?.();
            stopWaitingForIdle = null;
            quiet = setTimeout(checkRequests, quietMs);
        }
        function checkRequests(): void {
            let answeredAtOnce = false;
            let waiting = true;
            stopWaitingForIdle = requestsIdle(() => {
                if (waiting) answeredAtOnce = true;
                else restart();
            });
            waiting = false;
            if (answeredAtOnce) finish(true);
        }
        if (signal?.aborted) {
            finish(false);
            return;
        }
        signal?.addEventListener('abort', callOff, { once: true });
        stopWatching = watch(restart);
        restart();
    });
}

/**
 * Keeps a part where a landing put it while the content around it is still filling in, and returns the
 * stop. Every size change puts it back (`place`) before the frame is drawn; the hold ends when the
 * reader acts, when the caller stops it (a newer address, leaving the page), or after `maxMs`.
 *
 * A Settings part further down its section is landed on before the parts above it have their data (the
 * model list, Hardware once the list answers, More options' own parts). Waiting for the page to go quiet
 * failed whenever the backend was slow; holding the part follows the content however late it comes.
 */
export function holdInPlace({ watch, listenForIntent, place, maxMs = 3000 }: { watch: Listen; listenForIntent: Listen; place: () => void; maxMs?: number }): () => void {
    let held = true;
    const stopWatching = watch(() => {
        if (held) place();
    });
    const stopListening = listenForIntent(() => release());
    const longest = setTimeout(() => release(), maxMs);
    function release(): void {
        if (!held) return;
        held = false;
        clearTimeout(longest);
        stopWatching();
        stopListening();
    }
    return release;
}
