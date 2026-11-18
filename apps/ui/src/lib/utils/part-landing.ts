/** Starts reporting to `onReport` and returns the stop. */
type Listen = (onReport: () => void) => () => void;

/** Reports every size change of any of `elements`, through one ResizeObserver. */
export function watchElementSizes(...elements: Element[]): Listen {
    return (onResize) => {
        const observer = new ResizeObserver(() => onResize());
        for (const element of elements) observer.observe(element);
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
 * Keeps a part where a landing put it while the page around it is still filling in, and returns the
 * stop. Whenever `watch` reports a change, the part's top (`position`) is compared with where it landed
 * and the page is scrolled by the difference, so whatever moved it (a part above it growing, the shell's
 * jobs strip appearing above the section) is undone before the frame is drawn. Safari keeps no reader's
 * place by itself; Chromium's scroll anchoring usually leaves nothing to undo. The hold ends when the
 * reader acts, when the caller stops it (a newer address, leaving the page), when the part is gone, or
 * after `maxMs`.
 */
export function holdInPlace({ watch, listenForIntent, position, scrollBy, maxMs = 3000 }: {
    watch: Listen;
    listenForIntent: Listen;
    position: () => number | null;
    scrollBy: (by: number) => void;
    maxMs?: number;
}): () => void {
    let held = true;
    const landed = position();
    const stopWatching = watch(() => {
        if (!held) return;
        const now = position();
        if (now === null || landed === null) {
            release();
            return;
        }
        if (Math.abs(now - landed) >= 1) scrollBy(now - landed);
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
