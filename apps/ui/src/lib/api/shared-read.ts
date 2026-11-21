/**
 * How long a status reading is handed to other callers: long enough to join the views that mount
 * together on one load, far shorter than any of those readings changes on its own.
 */
export const STATUS_SHARE_MS = 5_000;

export interface SharedRead<T> {
    /** The current reading. A caller's own signal only stops that caller waiting. */
    read(signal?: AbortSignal): Promise<T>;
    /** Something said the reading changed: the next caller asks the server again. */
    invalidate(): void;
    /**
     * Call as a direct request starts. Settling it with the answer makes that the shared reading, but
     * only if nothing changed meanwhile: an answer read in another session or language, or before an
     * invalidation, is dropped rather than shared.
     */
    begin(): { settle(value: T): void };
}

function abortError(): DOMException {
    return new DOMException('The read was aborted.', 'AbortError');
}

function waitFor<T>(reading: Promise<T>, signal: AbortSignal | undefined): Promise<T> {
    if (!signal) return reading;
    if (signal.aborted) return Promise.reject(abortError());
    return new Promise<T>((resolve, reject) => {
        const stop = (): void => reject(abortError());
        signal.addEventListener('abort', stop, { once: true });
        reading.then(
            (value) => {
                signal.removeEventListener('abort', stop);
                resolve(value);
            },
            (error: unknown) => {
                signal.removeEventListener('abort', stop);
                reject(error);
            }
        );
    });
}

/**
 * One reading of a status endpoint for every part of the page that asks for it at the same moment.
 *
 * The shell, the page and its cards each show some of the same status (cameras, version, updates),
 * and they mount together, so each asking for itself sent the same request two or three times on
 * every load. Callers that ask while a request is in flight share it, and a caller that asks within
 * `shareForMs` of a reading arriving is handed that reading. A failure is never kept, and
 * `invalidate()` drops a reading the moment something says it changed, so the window only ever
 * joins callers asking about the same moment; it is not a cache that outlives a change.
 */
export function createSharedRead<T>(
    read: () => Promise<T>,
    options: {
        shareForMs: number;
        /**
         * Who is asking and in which language. A reading is only ever handed to callers in the scope
         * it was read in, so a guest and an owner, or two languages, never share one.
         */
        scope?: () => string;
        now?: () => number;
    }
): SharedRead<T> {
    const now = options.now ?? (() => Date.now());
    const scopeNow = options.scope ?? (() => '');
    let generation = 0;
    let readScope = '';
    let inFlight: Promise<T> | null = null;
    let kept: { at: number; value: T } | null = null;

    function forget(): void {
        generation += 1;
        inFlight = null;
        kept = null;
    }

    function start(): Promise<T> {
        const startedIn = generation;
        const request = read().then((value) => {
            if (startedIn === generation) kept = { at: now(), value };
            return value;
        });
        inFlight = request;
        const clear = (): void => {
            if (inFlight === request) inFlight = null;
        };
        request.then(clear, clear);
        return request;
    }

    return {
        read(signal?: AbortSignal): Promise<T> {
            if (signal?.aborted) return Promise.reject(abortError());
            const scope = scopeNow();
            if (scope !== readScope) {
                forget();
                readScope = scope;
            }
            if (kept && now() - kept.at < options.shareForMs) return Promise.resolve(kept.value);
            return waitFor(inFlight ?? start(), signal);
        },
        invalidate: forget,
        begin(): { settle(value: T): void } {
            const startedIn = generation;
            const askedIn = scopeNow();
            return {
                settle(value: T): void {
                    if (generation !== startedIn || scopeNow() !== askedIn) return;
                    forget();
                    readScope = askedIn;
                    kept = { at: now(), value };
                }
            };
        }
    };
}
