/**
 * A ticket for one read. It stays current until a newer read begins or the reads are
 * superseded, and only a current ticket may apply its result or clear the loading state.
 */
interface RequestTicket {
    isCurrent(): boolean;
}

/**
 * Only the newest read may apply its result.
 *
 * Responses can resolve in any order, and a request that was not aborted still resolves.
 * `begin()` supersedes every earlier ticket. `supersede()` does the same without starting a
 * read, for when what may be shown has changed (for example the public history moved on for a
 * visitor) and the rows already in flight must not land before the replacement read begins.
 */
export interface LatestRequest {
    begin(): RequestTicket;
    supersede(): void;
}

export function createLatestRequest(): LatestRequest {
    let generation = 0;
    return {
        begin(): RequestTicket {
            const ticket = ++generation;
            return { isCurrent: () => ticket === generation };
        },
        supersede(): void {
            generation += 1;
        }
    };
}

/** One read in a run where only the newest counts: its signal, and whether it is still the newest. */
interface SupersedingTicket {
    readonly signal: AbortSignal;
    isCurrent(): boolean;
}

/**
 * Reads where a newer one makes the older pointless (the same helper data asked for again after a
 * save). `begin()` cancels the read before it, so its request stops, and only the newest ticket
 * may apply its result: an older answer that still arrives is dropped. The caller's signal (a tab
 * closing) cancels the read too, without making it stale, so it can still clear its own loading state.
 */
export interface SupersedingRead {
    begin(callerSignal?: AbortSignal): SupersedingTicket;
}

export function createSupersedingRead(): SupersedingRead {
    let newest: AbortController | null = null;
    return {
        begin(callerSignal?: AbortSignal): SupersedingTicket {
            newest?.abort();
            const controller = new AbortController();
            newest = controller;
            if (callerSignal?.aborted) controller.abort(callerSignal.reason);
            else callerSignal?.addEventListener('abort', () => controller.abort(callerSignal.reason), { once: true });
            return { signal: controller.signal, isCurrent: () => newest === controller };
        }
    };
}
